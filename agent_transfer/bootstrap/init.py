"""agent-transfer init — full-config capstone bootstrap.

After `agent-transfer import` has placed bundle artifacts (rules, hooks,
CLAUDE.md, settings, MCP source tarballs, bin scripts) into the
destination home, this module finishes the job:

  1. Locate the bundle's claude-config-export*.json (carries the
     `_classification` block per MCP server).
  2. Validate runtime versions (python / node engines) against the
     destination. Abort with a clear hint on mismatch — better than
     silently failing during `uv sync` later.
  3. For each MCP server with bundled local source: extract was
     already done by the import step (~/.claude-imported/mcp-sources/
     <name>/). Run the classifier-supplied `install_steps` per server
     IN that directory, with confirm-before-run unless --yes.
  4. For HTTP-transport servers: prompt for auth tokens (or read from
     --tokens-file) and substitute into the per-server `headers` map.
  5. Call `rewrite_mcp_servers_for_target_home` to translate paths,
     merge the result into ~/.claude.json (with backup), and write
     CLAUDE.md as `.incoming` if existing differs.

User-approved defaults (PRD Q1/Q5/Q6, 2026-05-02):
  • CLAUDE.md: ALWAYS .incoming, never auto-merge
  • HTTP tokens: interactive prompt OR --tokens-file KEY=VALUE format
  • Doctor: SEPARATE explicit step, NOT inside init
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


# Exit codes — kept stable so CI can react.
EXIT_OK = 0
EXIT_BUNDLE_NOT_FOUND = 10
EXIT_NO_CLASSIFICATION = 11
EXIT_VERSION_MISMATCH = 12
EXIT_TOKENS_REQUIRED = 13
EXIT_INSTALL_STEP_FAILED = 14
EXIT_USER_DECLINED = 15
EXIT_DRY_RUN = 16


@dataclass
class InitResult:
    """Structured outcome of `agent-transfer init`."""

    bundle_dir: Path
    target_home: Path
    classification_path: Optional[Path] = None
    backup_path: Optional[Path] = None
    claude_md_incoming_path: Optional[Path] = None
    servers_installed: list[str] = field(default_factory=list)
    servers_skipped: list[str] = field(default_factory=list)
    install_step_failures: dict[str, str] = field(default_factory=dict)
    http_tokens_filled: list[str] = field(default_factory=list)
    http_tokens_missing: list[str] = field(default_factory=list)
    version_aborts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    exit_code: int = EXIT_OK


def _find_classification_export(bundle_dir: Path) -> Optional[Path]:
    """Locate the claude-config-export*.json carrying _classification."""
    # Common shapes:
    #   bundle_dir/<extracted-bundle>/claude-config-export_*.json
    #   bundle_dir/claude-config-export_*.json
    # We accept either and the first match wins (most recent by mtime).
    candidates: list[Path] = []
    for pattern in ("claude-config-export*.json", "*/claude-config-export*.json"):
        candidates.extend(bundle_dir.glob(pattern))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _load_classifications(export_path: Path) -> Optional[dict[str, dict[str, Any]]]:
    """Return the per-server classification dict, or None on shape error."""
    try:
        data = json.loads(export_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    cls = data.get("_classification") or {}
    servers = cls.get("servers")
    if not isinstance(servers, dict):
        return None
    return servers


def _load_mcp_sources_manifest(bundle_dir: Path) -> Optional[dict[str, Any]]:
    """Read mcp-sources-manifest.json — carries python_version/node_engines."""
    for pattern in ("mcp-sources-manifest.json", "*/mcp-sources-manifest.json"):
        for p in bundle_dir.glob(pattern):
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
    return None


def _read_source_servers(export_path: Path) -> dict[str, dict]:
    """Return the source-side `mcpServers` dict from the export JSON."""
    try:
        data = json.loads(export_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    servers = data.get("mcpServers")
    return servers if isinstance(servers, dict) else {}


def _source_home_hint(export_path: Path) -> Optional[str]:
    try:
        data = json.loads(export_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    meta = data.get("_metadata") or {}
    h = meta.get("source_home")
    return h if isinstance(h, str) else None


def _parse_python_version_spec(spec: str) -> Optional[tuple[int, int, int]]:
    """Best-effort parse of a Python version requirement.

    Handles: ">=3.10,<4", "^3.11", "==3.12.1", "3.13", "3.12".
    Returns the LOWER bound as a tuple, or None on unparseable.
    """
    if not spec:
        return None
    s = spec.strip()
    # Tolerate poetry-style caret/tilde at the front
    s = re.sub(r"^[\^~=]+", "", s)
    # First comma-separated clause that has a numeric version
    for clause in (s.split(",") if "," in s else [s]):
        m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", clause)
        if m:
            major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
            return major, minor, patch
    return None


def _current_python_version() -> tuple[int, int, int]:
    return sys.version_info[0], sys.version_info[1], sys.version_info[2]


def _check_runtime_versions(
    classifications: dict[str, dict[str, Any]],
    mcp_manifest: Optional[dict[str, Any]],
) -> list[tuple[str, str, str]]:
    """Return list of (server_name, runtime, reason) aborts.

    Each entry indicates the destination cannot satisfy the source's
    runtime requirement. Empty list means all good (or no requirements
    were captured — which is fine, we don't fail-closed when we have
    nothing to check against).
    """
    aborts: list[tuple[str, str, str]] = []
    if not mcp_manifest:
        return aborts
    bundled = mcp_manifest.get("bundled") or []
    py_now = _current_python_version()

    for b in bundled:
        name = b.get("name", "?")
        py_required = b.get("python_version")
        if py_required:
            req = _parse_python_version_spec(py_required)
            if req is not None:
                # Compare on (major, minor)
                if (py_now[0], py_now[1]) < (req[0], req[1]):
                    aborts.append((
                        name,
                        "python",
                        f"requires Python >= {req[0]}.{req[1]} "
                        f"but destination has {py_now[0]}.{py_now[1]}",
                    ))
        # Node version check is advisory: we can't easily get the
        # destination's node version without exec — and `npm install`
        # will fail with a clear engines error anyway. Surface as a
        # warning only, not an abort.
    return aborts


def _read_tokens_file(path: Path) -> dict[str, str]:
    """Read KEY=VALUE per line; ignore blanks and # comments."""
    out: dict[str, str] = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


def _http_servers_needing_tokens(
    source_servers: dict[str, dict],
    classifications: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    """Return {server_name: [redacted-header-names...]} for HTTP transports."""
    out: dict[str, list[str]] = {}
    for name, src_cfg in source_servers.items():
        # Classifier marks transport via server_class or transport key on cfg
        cls = classifications.get(name) or {}
        server_class = cls.get("server_class") or ""
        transport = (src_cfg.get("transport") or "").lower()
        is_http = transport in ("http", "sse") or "http" in server_class
        if not is_http:
            continue
        headers = src_cfg.get("headers") or {}
        redacted_keys: list[str] = []
        for k, v in headers.items():
            if isinstance(v, str) and "<REDACTED>" in v:
                redacted_keys.append(k)
        if redacted_keys:
            out[name] = redacted_keys
    return out


def _fill_http_tokens(
    rewritten: dict[str, dict],
    needs: dict[str, list[str]],
    tokens_file_values: dict[str, str],
    interactive: bool,
) -> tuple[list[str], list[str]]:
    """Substitute tokens into rewritten[name]['headers'][k].

    Returns (filled_server_names, missing_server_names).
    Lookup priority per (server, header) pair:
      1. tokens_file_values[f"{server}__{header}"]   (uppercase preferred)
      2. tokens_file_values[header]                  (shared token)
      3. interactive prompt (if interactive=True)
    """
    filled: list[str] = []
    missing: list[str] = []

    def _lookup_token(server: str, header: str) -> Optional[str]:
        keys = [
            f"{server}__{header}".upper(),
            f"{server}__{header}",
            header.upper(),
            header,
        ]
        for k in keys:
            if k in tokens_file_values and tokens_file_values[k]:
                return tokens_file_values[k]
        return None

    for server, header_names in needs.items():
        cfg = rewritten.get(server) or {}
        headers = dict(cfg.get("headers") or {})
        any_filled = False
        any_missing = False
        for h in header_names:
            tok = _lookup_token(server, h)
            if tok is None and interactive:
                try:
                    prompt = (
                        f"Token for {server!r} header {h!r} "
                        f"(empty to skip this server): "
                    )
                    tok = input(prompt).strip() or None
                except (KeyboardInterrupt, EOFError):
                    tok = None
            if tok:
                # Preserve any "Bearer " prefix the original used if the
                # source value had structure. Simple substitution: replace
                # the <REDACTED> marker inline.
                src_val = headers.get(h, "<REDACTED>")
                headers[h] = src_val.replace("<REDACTED>", tok) if "<REDACTED>" in src_val else tok
                any_filled = True
            else:
                any_missing = True
        cfg["headers"] = headers
        rewritten[server] = cfg
        if any_filled and not any_missing:
            filled.append(server)
        elif any_missing:
            missing.append(server)
    return filled, missing


def _run_install_steps(
    server_name: str,
    steps: list[str],
    cwd: Path,
    confirm_each: bool,
) -> Optional[str]:
    """Run each step in cwd. Return None on success, str(reason) on failure."""
    for step in steps:
        if step.startswith("#"):
            # Classifier emits "# <hint>" lines for advisory steps.
            continue
        if confirm_each:
            try:
                ans = input(
                    f"  Run for {server_name!r}? `{step}` (in {cwd}) [y/N] "
                ).strip().lower()
            except (KeyboardInterrupt, EOFError):
                return f"declined at step: {step}"
            if ans not in ("y", "yes"):
                return f"declined at step: {step}"
        try:
            rc = subprocess.run(
                step,
                shell=True,
                cwd=str(cwd),
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            return f"OSError running `{step}`: {exc}"
        if rc.returncode != 0:
            tail = (rc.stderr or rc.stdout or "")[-400:].strip()
            return f"exit {rc.returncode} from `{step}`: {tail}"
    return None


def _merge_claude_md(
    bundle_dir: Path, target_home: Path, result: InitResult
) -> None:
    """If bundle has CLAUDE.md and it differs from target's, place .incoming."""
    candidates: list[Path] = []
    for pat in ("CLAUDE.md", "*/CLAUDE.md"):
        candidates.extend(bundle_dir.glob(pat))
    if not candidates:
        return
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    src = candidates[0]
    try:
        src_bytes = src.read_bytes()
    except OSError:
        return
    target = target_home / ".claude" / "CLAUDE.md"
    if target.is_file():
        try:
            if target.read_bytes() == src_bytes:
                return  # identical — no-op
        except OSError:
            pass
    target.parent.mkdir(parents=True, exist_ok=True)
    incoming = target.with_suffix(".md.incoming")
    incoming.write_bytes(src_bytes)
    result.claude_md_incoming_path = incoming


def init(
    bundle_dir: Path,
    *,
    home: Optional[Path] = None,
    auto_yes: bool = False,
    accept_risks: bool = False,
    tokens_file: Optional[Path] = None,
    dry_run: bool = False,
) -> InitResult:
    """Run the init capstone. Returns a structured InitResult.

    Args:
        bundle_dir: A directory containing the extracted bundle (NOT the
            still-compressed .tar.gz). If the user passed a tarball to
            the CLI, the caller is expected to extract it first.
        home: Override of $HOME; defaults to Path.home().
        auto_yes: Skip per-step confirmation. Requires accept_risks=True
            so this can't be tripped accidentally in CI.
        accept_risks: Required to pair with auto_yes. Independent flag
            so the user has to explicitly opt into unattended install.
        tokens_file: Path to a KEY=VALUE file for HTTP-transport tokens.
        dry_run: Plan only; do not run install_steps or touch ~/.claude.json.
    """
    home = home or Path.home()
    bundle_dir = bundle_dir.resolve()
    result = InitResult(bundle_dir=bundle_dir, target_home=home)

    if not bundle_dir.is_dir():
        result.errors.append(f"bundle_dir not found or not a directory: {bundle_dir}")
        result.exit_code = EXIT_BUNDLE_NOT_FOUND
        return result

    if auto_yes and not accept_risks:
        result.errors.append(
            "--yes requires --i-accept-risks to allow unattended install of "
            "MCP server install_steps (each runs `uv sync` / `npm install` / "
            "`docker pull` in subprocess shell)."
        )
        result.exit_code = EXIT_USER_DECLINED
        return result

    export_path = _find_classification_export(bundle_dir)
    if export_path is None:
        result.errors.append(
            f"No claude-config-export*.json found under {bundle_dir}. "
            "Run `agent-transfer export` on the source machine first."
        )
        result.exit_code = EXIT_NO_CLASSIFICATION
        return result
    result.classification_path = export_path

    classifications = _load_classifications(export_path) or {}
    source_servers = _read_source_servers(export_path)
    source_home = _source_home_hint(export_path)
    mcp_manifest = _load_mcp_sources_manifest(bundle_dir)

    # Runtime-version gate (A4).
    aborts = _check_runtime_versions(classifications, mcp_manifest)
    if aborts:
        for server, runtime, reason in aborts:
            result.version_aborts.append(f"{server} ({runtime}): {reason}")
        result.errors.append(
            "Runtime version mismatch for one or more servers. "
            "Either upgrade the destination runtime to match the bundled "
            "requirements, or re-export the bundle with a relaxed pin."
        )
        result.exit_code = EXIT_VERSION_MISMATCH
        return result

    # Back up ~/.claude.json BEFORE any write. Skip on dry-run since
    # we won't write either.
    claude_json = home / ".claude.json"
    if claude_json.is_file() and not dry_run:
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        backup = home / f".claude.json.backup.{ts}"
        try:
            shutil.copy2(claude_json, backup)
            result.backup_path = backup
        except OSError as exc:
            result.warnings.append(f"could not backup ~/.claude.json: {exc}")

    # Run install_steps per server. Source dirs were placed by `import`
    # under ~/.claude-imported/mcp-sources/<name>/<name>/ (the tar
    # arcname re-prefix). We resolve to the inner dir; fall back to the
    # outer dir if the inner doesn't exist.
    base = home / ".claude-imported" / "mcp-sources"
    for name, cls in classifications.items():
        steps: list[str] = cls.get("install_steps") or []
        if not steps:
            continue
        cwd = base / name / name
        if not cwd.is_dir():
            cwd = base / name
        if not cwd.is_dir():
            result.servers_skipped.append(name)
            result.warnings.append(
                f"{name}: no extracted source dir at {base / name} — skipped install_steps"
            )
            continue
        if dry_run:
            result.servers_skipped.append(name)
            continue
        confirm_each = not auto_yes
        fail = _run_install_steps(name, steps, cwd, confirm_each)
        if fail:
            result.install_step_failures[name] = fail
        else:
            result.servers_installed.append(name)

    if result.install_step_failures and not auto_yes:
        # Partial failure: leave ~/.claude.json untouched.
        result.errors.append(
            f"install_steps failed for {len(result.install_step_failures)} server(s); "
            "skipping path-rewrite + MCP merge. Resolve the failures and re-run."
        )
        result.exit_code = EXIT_INSTALL_STEP_FAILED
        return result

    # Rewrite paths for the destination home.
    try:
        from agent_transfer.utils.transfer import rewrite_mcp_servers_for_target_home
    except ImportError as exc:
        result.errors.append(f"rewrite_mcp_servers_for_target_home unavailable: {exc}")
        result.exit_code = EXIT_INSTALL_STEP_FAILED
        return result

    rewritten = rewrite_mcp_servers_for_target_home(
        source_servers,
        classifications,
        target_home=str(home),
        source_home=source_home,
    )

    # HTTP-transport token UX (A3).
    needs = _http_servers_needing_tokens(source_servers, classifications)
    tokens_file_values: dict[str, str] = {}
    if tokens_file is not None:
        tokens_file_values = _read_tokens_file(tokens_file)
    interactive = (not auto_yes) and sys.stdin is not None and sys.stdin.isatty()
    if needs:
        filled, missing = _fill_http_tokens(
            rewritten, needs, tokens_file_values, interactive
        )
        result.http_tokens_filled = filled
        result.http_tokens_missing = missing
        if missing and auto_yes:
            # Unattended mode: missing tokens is an error.
            result.errors.append(
                f"HTTP token(s) missing for: {', '.join(missing)}. "
                f"Provide via --tokens-file (KEY=VALUE) or run without --yes."
            )
            result.exit_code = EXIT_TOKENS_REQUIRED
            return result

    if dry_run:
        result.exit_code = EXIT_DRY_RUN
        return result

    # Merge rewritten mcpServers into ~/.claude.json.
    existing: dict[str, Any] = {}
    if claude_json.is_file():
        try:
            existing = json.loads(claude_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            result.warnings.append(
                f"could not read existing ~/.claude.json ({exc}); creating fresh"
            )
            existing = {}
    existing_servers = existing.get("mcpServers") or {}
    if not isinstance(existing_servers, dict):
        existing_servers = {}
    # Rewritten entries WIN — they carry the post-install config_after_install.
    merged = dict(existing_servers)
    merged.update(rewritten)
    existing["mcpServers"] = merged

    try:
        claude_json.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    except OSError as exc:
        result.errors.append(f"failed to write ~/.claude.json: {exc}")
        result.exit_code = EXIT_INSTALL_STEP_FAILED
        return result

    # CLAUDE.md → .incoming when content differs.
    _merge_claude_md(bundle_dir, home, result)

    result.exit_code = EXIT_OK
    return result
