"""
MCP server classifier.

Reads ~/.claude.json (or any path), inspects each entry under `mcpServers`,
and returns a classification + capture/rewrite plan. This validates the
CLASSIFY → CAPTURE → REWRITE → EMIT-MANIFEST pipeline from ARCHITECTURE.md
against real-world configs before any export code is written.

Usage (programmatic):
    from agent_transfer.utils.mcp_classifier import classify_all
    report = classify_all(Path.home() / ".claude.json")

Usage (CLI):
    python -m agent_transfer.utils.mcp_classifier [path]
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


# Classes correspond to ARCHITECTURE.md "MCP runtime capture" table.
CLASS_REGISTRY_NPM = "registry-npm"            # npx / bunx — package resolved at runtime
CLASS_REGISTRY_PYTHON = "registry-python"      # uvx — package resolved at runtime
CLASS_LOCAL_PYTHON = "local-python"            # python script in a local repo (often with venv)
CLASS_LOCAL_NODE = "local-node"                # node script in a local repo
CLASS_LOCAL_UV = "local-uv"                    # uv run --directory <local-path>
CLASS_DOCKER = "docker"                        # docker run ...
CLASS_HTTP = "http-transport"                  # no command; URL/SSE
CLASS_BINARY = "absolute-path-binary"          # absolute path to an arbitrary binary
CLASS_UNKNOWN = "unknown"

CAPTURE_BUNDLE_SOURCE = "bundle-source"        # tar the local repo into the archive
CAPTURE_RECORD_PACKAGE = "record-package"      # write package name + version to manifest
CAPTURE_RECORD_IMAGE = "record-image"          # write image:tag to manifest
CAPTURE_RECORD_URL = "record-url"              # write URL + redacted headers
CAPTURE_NONE = "none"

REWRITE_HOME = "rewrite-home"                  # /home/<user>/ -> $HOME/
REWRITE_RUNTIME_LOOKUP = "rewrite-runtime-lookup"  # /home/<user>/.nvm/.../npx -> $(which npx)
REWRITE_VENV_REBUILD = "rewrite-venv-rebuild"  # destination must rebuild venv
REWRITE_NONE = "none"


# Token / secret heuristics for redaction warnings (not enforcement here).
SECRET_KEY_HINTS = re.compile(r"(?i)(token|secret|password|api[_-]?key|authorization|bearer)")
SECRET_VALUE_HINTS = re.compile(
    r"(?:Bearer\s+\S+|sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|xox[baprs]-[A-Za-z0-9-]{10,})"
)


@dataclass
class ClassificationResult:
    name: str
    server_class: str
    command: str | None
    args: list[str]
    capture_strategy: str
    rewrite_strategy: str
    install_steps: list[str] = field(default_factory=list)
    config_after_install: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    secrets_detected: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    # AgentBridge MVP (003) — risk tag for the bundle inventory.
    # green  = no auth, no state mutation (rare for MCP servers)
    # yellow = standard server with no detected secrets
    # red    = auth-bearing or secret-detected (must prompt user on ingest)
    risk_tag: str = "yellow"


def _compute_risk_tag(res: "ClassificationResult", cfg: dict[str, Any]) -> str:
    """Decide Green/Yellow/Red per FR-008.

    Default: Yellow (any tool definition with parameters).
    Yellow → Red if: secrets detected, or auth headers present, or
                     config references state-writing runtime hooks.
    Yellow → Green only if: no env, no headers, no secrets, no warnings.
    """
    if res.secrets_detected:
        return "red"
    if cfg.get("headers"):
        return "red"
    env = cfg.get("env") or {}
    if any("AUTH" in k.upper() or "TOKEN" in k.upper() or "KEY" in k.upper() for k in env):
        return "red"
    if not env and not cfg.get("headers") and not res.warnings:
        return "green"
    return "yellow"


def _detect_secrets(cfg: dict[str, Any]) -> list[str]:
    found: list[str] = []
    env = cfg.get("env") or {}
    for k, v in env.items():
        if SECRET_KEY_HINTS.search(k):
            found.append(f"env.{k} (key-name match)")
        if isinstance(v, str) and SECRET_VALUE_HINTS.search(v):
            found.append(f"env.{k} (value pattern match)")
    headers = cfg.get("headers") or {}
    for k, v in headers.items():
        if SECRET_KEY_HINTS.search(k) or (isinstance(v, str) and SECRET_VALUE_HINTS.search(v)):
            found.append(f"headers.{k}")
    for arg in cfg.get("args") or []:
        if isinstance(arg, str) and SECRET_VALUE_HINTS.search(arg):
            found.append("args[*] (token-shaped value)")
            break
    return found


def _path_starts_in_home(s: str, home: str) -> bool:
    return s.startswith(home + "/") or s == home


def _is_runtime_manager_path(p: str) -> bool:
    """Detect runtime-manager-managed binary paths (nvm, bun, pyenv, etc.)."""
    rm_markers = (".nvm/", ".bun/", ".pyenv/", ".rye/", ".asdf/", ".volta/", ".cargo/")
    return any(m in p for m in rm_markers)


def _classify_entry(name: str, cfg: dict[str, Any], home: str) -> ClassificationResult:
    cmd = cfg.get("command")
    args: list[str] = list(cfg.get("args") or [])
    transport = cfg.get("type") or cfg.get("transport")
    url = cfg.get("url") or cfg.get("endpoint")

    res = ClassificationResult(
        name=name,
        server_class=CLASS_UNKNOWN,
        command=cmd,
        args=args,
        capture_strategy=CAPTURE_NONE,
        rewrite_strategy=REWRITE_NONE,
        raw=cfg,
    )
    res.secrets_detected = _detect_secrets(cfg)
    if res.secrets_detected:
        res.warnings.append(
            f"secrets detected ({len(res.secrets_detected)}); will be redacted on export"
        )

    # ---- HTTP / SSE transport (no command at all) ----
    if not cmd and (url or transport in {"sse", "http", "streamable-http", "websocket"}):
        res.server_class = CLASS_HTTP
        res.capture_strategy = CAPTURE_RECORD_URL
        res.rewrite_strategy = REWRITE_NONE
        res.install_steps = []  # nothing to install; importer pastes auth
        res.config_after_install = {k: v for k, v in cfg.items() if k != "headers"}
        if cfg.get("headers"):
            res.warnings.append("HTTP headers present — redact auth keys; importer must repaste")
        return res

    # If still no command and no URL, we can't classify.
    if not cmd:
        res.server_class = CLASS_UNKNOWN
        res.warnings.append("no `command` and no `url` — cannot classify")
        return res

    cmd_path = cmd
    cmd_basename = os.path.basename(cmd)

    # ---- Docker ----
    if cmd_basename == "docker":
        res.server_class = CLASS_DOCKER
        res.capture_strategy = CAPTURE_RECORD_IMAGE
        res.rewrite_strategy = REWRITE_NONE
        # crude image extraction: first non-flag arg after `run`
        image = None
        try:
            run_idx = args.index("run")
            for a in args[run_idx + 1 :]:
                if not a.startswith("-"):
                    image = a
                    break
        except ValueError:
            pass
        if image:
            res.install_steps = [f"docker pull {image}"]
        else:
            res.warnings.append("docker invocation found but image not extractable from args")
        res.config_after_install = {"command": cmd, "args": args}
        return res

    # ---- Registry-installable: npx / bunx / uvx ----
    if cmd_basename in {"npx", "bunx"}:
        res.server_class = CLASS_REGISTRY_NPM
        res.capture_strategy = CAPTURE_RECORD_PACKAGE
        # Path may be /home/user/.nvm/.../npx or /home/user/.bun/bin/bunx — needs lookup-rewrite.
        if cmd != cmd_basename and _is_runtime_manager_path(cmd):
            res.rewrite_strategy = REWRITE_RUNTIME_LOOKUP
            res.warnings.append(
                f"absolute path to runtime-manager-managed binary `{cmd}` — "
                f"on import resolve via `$(which {cmd_basename})`"
            )
        # Package name is usually first non-flag arg
        pkg = next((a for a in args if not a.startswith("-")), None)
        if pkg:
            res.install_steps = [
                f"# {pkg} resolves at runtime via {cmd_basename} -y; ensure {cmd_basename} is on PATH"
            ]
        res.config_after_install = {"command": cmd_basename, "args": args}
        return res

    if cmd_basename == "uvx":
        res.server_class = CLASS_REGISTRY_PYTHON
        res.capture_strategy = CAPTURE_RECORD_PACKAGE
        res.rewrite_strategy = REWRITE_NONE if cmd == cmd_basename else REWRITE_RUNTIME_LOOKUP
        pkg = next((a for a in args if not a.startswith("-")), None)
        if pkg:
            res.install_steps = [f"# {pkg} resolves at runtime via uvx; ensure uv is installed"]
        res.config_after_install = {"command": "uvx", "args": args}
        return res

    # ---- uv run --directory <path> (local-source Python) ----
    if cmd_basename == "uv" and "--directory" in args:
        res.server_class = CLASS_LOCAL_UV
        res.capture_strategy = CAPTURE_BUNDLE_SOURCE
        try:
            dir_idx = args.index("--directory")
            local_dir = args[dir_idx + 1]
        except (ValueError, IndexError):
            local_dir = None
        if local_dir and _path_starts_in_home(local_dir, home):
            res.rewrite_strategy = REWRITE_HOME
            relpath = os.path.relpath(local_dir, home)
            res.install_steps = [
                f"tar -xzf mcp-sources/{name}.tar.gz -C $HOME/{os.path.dirname(relpath)}",
                f"cd $HOME/{relpath} && uv sync",
            ]
            new_args = list(args)
            new_args[dir_idx + 1] = f"$HOME/{relpath}"
            res.config_after_install = {"command": "uv", "args": new_args}
        elif local_dir:
            res.warnings.append(f"--directory `{local_dir}` is outside $HOME — manual review needed")
        else:
            res.warnings.append("uv command found but --directory value missing")
        return res

    # ---- python / node script (local source) ----
    if cmd_basename in {"python", "python3"} or cmd_basename.startswith("python"):
        res.server_class = CLASS_LOCAL_PYTHON
        # Detect: is the python interpreter itself in a local venv?
        venv_python = ".venv/" in cmd or "/venv/" in cmd
        # Args usually have a script path
        script = next((a for a in args if a.endswith(".py") or "/" in a), None)
        if script and _path_starts_in_home(script, home):
            res.capture_strategy = CAPTURE_BUNDLE_SOURCE
            res.rewrite_strategy = REWRITE_VENV_REBUILD if venv_python else REWRITE_HOME
            script_rel = os.path.relpath(script, home)
            project_dir = os.path.dirname(script_rel)
            steps = [f"tar -xzf mcp-sources/{name}.tar.gz -C $HOME/{os.path.dirname(project_dir)}"]
            if venv_python:
                steps.append(
                    f"cd $HOME/{project_dir} && python3 -m venv .venv && "
                    f".venv/bin/pip install -r requirements.txt"
                )
                new_cmd = f"$HOME/{project_dir}/.venv/bin/python"
            else:
                new_cmd = "python3"
            res.install_steps = steps
            new_args = [f"$HOME/{script_rel}" if a == script else a for a in args]
            res.config_after_install = {"command": new_cmd, "args": new_args}
        else:
            res.warnings.append("python script path not in $HOME or not detectable; manual review")
        return res

    if cmd_basename == "node":
        res.server_class = CLASS_LOCAL_NODE
        script = next((a for a in args if a.endswith(".js") or a.endswith(".mjs") or "/" in a), None)
        if script and _path_starts_in_home(script, home):
            res.capture_strategy = CAPTURE_BUNDLE_SOURCE
            res.rewrite_strategy = REWRITE_HOME
            script_rel = os.path.relpath(script, home)
            project_dir = os.path.dirname(script_rel)
            res.install_steps = [
                f"tar -xzf mcp-sources/{name}.tar.gz -C $HOME/{os.path.dirname(project_dir)}",
                f"cd $HOME/{project_dir} && npm install",
            ]
            new_args = [f"$HOME/{script_rel}" if a == script else a for a in args]
            res.config_after_install = {"command": "node", "args": new_args}
        else:
            res.warnings.append("node script path not in $HOME or not detectable; manual review")
        return res

    # ---- Absolute-path binary (catch-all for anything starting with /) ----
    if cmd.startswith("/"):
        res.server_class = CLASS_BINARY
        res.capture_strategy = CAPTURE_NONE
        res.rewrite_strategy = REWRITE_RUNTIME_LOOKUP if _is_runtime_manager_path(cmd) else REWRITE_HOME
        res.warnings.append(
            f"absolute-path binary `{cmd}` — destination machine must have it on PATH "
            f"or at the same absolute location"
        )
        res.config_after_install = {"command": cmd_basename, "args": args}
        return res

    # ---- Fallthrough ----
    res.server_class = CLASS_UNKNOWN
    res.warnings.append(f"unrecognised command shape: `{cmd}`")
    return res


def classify_servers(
    servers: dict[str, dict[str, Any]], home: str | None = None
) -> list[ClassificationResult]:
    """Classify a dict of mcpServers entries. Public entry for in-process use."""
    home = home or os.path.expanduser("~")
    results = [_classify_entry(name, cfg, home) for name, cfg in servers.items()]
    # AgentBridge (003) — populate risk_tag on every result post-classification.
    for r in results:
        r.risk_tag = _compute_risk_tag(r, r.raw)
    return results


def summarize(results: list[ClassificationResult]) -> dict[str, Any]:
    """Build counts-by-class summary from classification results."""
    by_class: dict[str, int] = {}
    by_capture: dict[str, int] = {}
    by_rewrite: dict[str, int] = {}
    secret_count = 0
    for r in results:
        by_class[r.server_class] = by_class.get(r.server_class, 0) + 1
        by_capture[r.capture_strategy] = by_capture.get(r.capture_strategy, 0) + 1
        by_rewrite[r.rewrite_strategy] = by_rewrite.get(r.rewrite_strategy, 0) + 1
        if r.secrets_detected:
            secret_count += 1
    return {
        "total_servers": len(results),
        "by_class": by_class,
        "by_capture_strategy": by_capture,
        "by_rewrite_strategy": by_rewrite,
        "servers_with_secrets": secret_count,
    }


def classify_all(claude_json_path: Path | str | None = None, home: str | None = None) -> dict[str, Any]:
    """Classify every entry under mcpServers in ~/.claude.json. Returns a summary dict."""
    home = home or os.path.expanduser("~")
    path = Path(claude_json_path) if claude_json_path else Path(home) / ".claude.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found")

    with open(path) as f:
        data = json.load(f)

    servers = data.get("mcpServers", {})
    results = classify_servers(servers, home)
    summary = summarize(results)

    return {
        "source_path": str(path),
        **summary,
        "servers": [asdict(r) for r in results],
    }


def _print_report(report: dict[str, Any]) -> None:
    print(f"=== MCP Classification Report ===")
    print(f"Source: {report['source_path']}")
    print(f"Total servers: {report['total_servers']}")
    print(f"Servers with detected secrets: {report['servers_with_secrets']}")
    print()
    print("By class:")
    for k, v in sorted(report["by_class"].items(), key=lambda x: -x[1]):
        print(f"  {k:25s} {v}")
    print()
    print("By capture strategy:")
    for k, v in sorted(report["by_capture_strategy"].items(), key=lambda x: -x[1]):
        print(f"  {k:25s} {v}")
    print()
    print("By rewrite strategy:")
    for k, v in sorted(report["by_rewrite_strategy"].items(), key=lambda x: -x[1]):
        print(f"  {k:25s} {v}")
    print()
    print("Per-server detail:")
    for s in report["servers"]:
        print(f"  - {s['name']}")
        print(f"      class:    {s['server_class']}")
        print(f"      capture:  {s['capture_strategy']}")
        print(f"      rewrite:  {s['rewrite_strategy']}")
        if s["install_steps"]:
            print(f"      steps:    {len(s['install_steps'])}")
        if s["warnings"]:
            for w in s["warnings"]:
                print(f"      ! {w}")
        if s["secrets_detected"]:
            for sd in s["secrets_detected"]:
                print(f"      🔒 {sd}")


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else None
    report = classify_all(src)
    _print_report(report)
