"""agent-transfer doctor — atomic system checks.

Each check is a pure function `() -> CheckResult` (or `(home: Path) ->
CheckResult` if it needs filesystem context). Checks NEVER write or
install — they only read state. Both `doctor inspect` (post-init
validator) and `doctor playbook` (pre-init bootstrap generator)
compose these atoms.

The result includes a `fix_hint` field that the playbook stitches
into concrete bootstrap commands per platform.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


CheckStatus = str  # "pass" | "warn" | "fail" | "skip"


@dataclass
class CheckResult:
    """Outcome of one check. Stable schema for the JSON sidecar."""

    id: str                              # short stable id e.g. "python3"
    title: str                           # human-readable title
    status: CheckStatus                  # pass | warn | fail | skip
    detail: str = ""                     # one-line current state
    fix_hint: str = ""                   # one-line remediation (playbook input)
    fix_command_darwin: Optional[str] = None
    fix_command_linux: Optional[str] = None
    severity: str = "info"               # info | warn | error
    raw: dict = field(default_factory=dict)  # tool-specific extras


def _platform_label() -> str:
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform.startswith("linux"):
        return "linux"
    return sys.platform


def _which(cmd: str) -> Optional[str]:
    return shutil.which(cmd)


def _run_capture(cmd: list[str], timeout: float = 3.0) -> tuple[int, str, str]:
    """Run a command with short timeout; never raise. Returns (rc, stdout, stderr)."""
    try:
        rc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return rc.returncode, rc.stdout.strip(), rc.stderr.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        return 127, "", f"{type(exc).__name__}: {exc}"


# --------------------------------------------------------------------- #
# Runtime checks (cross-platform)                                        #
# --------------------------------------------------------------------- #


def check_python3() -> CheckResult:
    """python3 must be on PATH for rollback.sh."""
    found = _which("python3")
    if not found:
        return CheckResult(
            id="python3",
            title="python3 on PATH (rollback.sh dependency)",
            status="fail",
            detail="python3 is not on PATH",
            severity="error",
            fix_hint="Install python3 (3.8+) and ensure it is on PATH.",
            fix_command_darwin="brew install python",
            fix_command_linux="sudo apt-get install -y python3  # or your distro's equivalent",
        )
    rc, out, _ = _run_capture([found, "--version"])
    ver = out or "unknown"
    return CheckResult(
        id="python3",
        title="python3 on PATH",
        status="pass",
        detail=f"{found} ({ver})",
        raw={"path": found, "version": ver},
    )


def check_uv() -> CheckResult:
    """uv is required for any local-uv MCP server install_steps."""
    found = _which("uv")
    if not found:
        return CheckResult(
            id="uv",
            title="uv (for local-uv MCP install)",
            status="warn",
            detail="uv is not on PATH",
            severity="warn",
            fix_hint="Install uv. Required if any bundled MCP server uses `uv run`.",
            fix_command_darwin="brew install uv",
            fix_command_linux="curl -LsSf https://astral.sh/uv/install.sh | sh",
        )
    rc, out, _ = _run_capture([found, "--version"])
    return CheckResult(
        id="uv",
        title="uv on PATH",
        status="pass",
        detail=f"{found} ({out or 'unknown'})",
        raw={"path": found, "version": out},
    )


def check_node() -> CheckResult:
    found = _which("node")
    npm = _which("npm")
    if not found:
        return CheckResult(
            id="node",
            title="node + npm (for local-node MCP install)",
            status="warn",
            detail="node is not on PATH",
            severity="warn",
            fix_hint="Install Node.js. Required if any bundled MCP server uses npx/node.",
            fix_command_darwin="brew install node",
            fix_command_linux="curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt-get install -y nodejs",
        )
    if not npm:
        return CheckResult(
            id="node",
            title="node + npm",
            status="warn",
            detail=f"node OK at {found} but npm missing",
            severity="warn",
            fix_hint="Reinstall node so npm is paired.",
        )
    rc, ver, _ = _run_capture([found, "--version"])
    return CheckResult(
        id="node",
        title="node on PATH",
        status="pass",
        detail=f"{found} ({ver}), npm at {npm}",
        raw={"node": found, "npm": npm, "version": ver},
    )


def check_git() -> CheckResult:
    found = _which("git")
    if not found:
        return CheckResult(
            id="git",
            title="git (for MCP source clone install_steps)",
            status="warn",
            detail="git is not on PATH",
            severity="warn",
            fix_hint="Install git. Many MCP install_steps assume git for clone.",
            fix_command_darwin="brew install git",
            fix_command_linux="sudo apt-get install -y git  # or your distro's equivalent",
        )
    return CheckResult(
        id="git",
        title="git on PATH",
        status="pass",
        detail=found,
        raw={"path": found},
    )


def check_docker() -> CheckResult:
    found = _which("docker")
    if not found:
        return CheckResult(
            id="docker",
            title="docker (for docker-pull MCP install_steps)",
            status="warn",
            detail="docker is not on PATH",
            severity="warn",
            fix_hint="Install Docker. Only required for MCP servers that ship as containers.",
            fix_command_darwin="brew install --cask docker  # then launch Docker.app at least once",
            fix_command_linux="see https://docs.docker.com/engine/install/ for your distro",
        )
    rc, out, _ = _run_capture([found, "--version"])
    return CheckResult(
        id="docker",
        title="docker on PATH",
        status="pass",
        detail=f"{found} ({out or 'unknown'})",
        raw={"path": found, "version": out},
    )


# --------------------------------------------------------------------- #
# Filesystem checks (require home)                                       #
# --------------------------------------------------------------------- #


def check_claude_dir(home: Path) -> CheckResult:
    cd = home / ".claude"
    if not cd.is_dir():
        return CheckResult(
            id="claude_dir",
            title="~/.claude/ directory",
            status="warn",
            detail=f"{cd} does not exist",
            severity="warn",
            fix_hint="agent-transfer import will create this; or `mkdir -p ~/.claude`.",
        )
    return CheckResult(
        id="claude_dir",
        title="~/.claude/ directory",
        status="pass",
        detail=str(cd),
    )


def check_claude_json(home: Path) -> CheckResult:
    cj = home / ".claude.json"
    if not cj.is_file():
        return CheckResult(
            id="claude_json",
            title="~/.claude.json present and parseable",
            status="warn",
            detail=f"{cj} does not exist",
            severity="warn",
            fix_hint="agent-transfer init will create it. No action needed pre-init.",
        )
    try:
        data = json.loads(cj.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return CheckResult(
            id="claude_json",
            title="~/.claude.json well-formed",
            status="fail",
            detail=f"unparseable: {exc}",
            severity="error",
            fix_hint="Restore from the most recent ~/.claude.json.backup.* in your home.",
        )
    n_servers = len((data.get("mcpServers") or {}))
    return CheckResult(
        id="claude_json",
        title="~/.claude.json well-formed",
        status="pass",
        detail=f"{n_servers} MCP server(s)",
        raw={"path": str(cj), "server_count": n_servers},
    )


def check_redacted_tokens(home: Path) -> CheckResult:
    """Post-init: ensure no <REDACTED> placeholders leaked into live config."""
    cj = home / ".claude.json"
    if not cj.is_file():
        return CheckResult(
            id="redacted_tokens",
            title="No <REDACTED> placeholders in live ~/.claude.json",
            status="skip",
            detail="~/.claude.json not present",
        )
    try:
        text = cj.read_text()
    except OSError as exc:
        return CheckResult(
            id="redacted_tokens",
            title="<REDACTED> token scan",
            status="warn",
            detail=str(exc),
        )
    if "<REDACTED>" in text:
        return CheckResult(
            id="redacted_tokens",
            title="No <REDACTED> placeholders in live ~/.claude.json",
            status="fail",
            detail="Found <REDACTED> placeholder(s) — HTTP-transport tokens not filled",
            severity="error",
            fix_hint="Re-run `agent-transfer init` with --tokens-file or interactively.",
        )
    return CheckResult(
        id="redacted_tokens",
        title="No <REDACTED> placeholders in live ~/.claude.json",
        status="pass",
    )


def check_mcp_sources_extracted(home: Path) -> CheckResult:
    """Post-import: ~/.claude-imported/mcp-sources/ should have tarball-extracted dirs."""
    base = home / ".claude-imported" / "mcp-sources"
    if not base.is_dir():
        return CheckResult(
            id="mcp_sources",
            title="MCP source dirs extracted",
            status="skip",
            detail=f"{base} does not exist (run `agent-transfer import` first)",
        )
    dirs = [p for p in base.iterdir() if p.is_dir()]
    return CheckResult(
        id="mcp_sources",
        title="MCP source dirs extracted",
        status="pass",
        detail=f"{len(dirs)} server source dir(s) at {base}",
        raw={"path": str(base), "count": len(dirs)},
    )


# --------------------------------------------------------------------- #
# Platform-specific checks                                               #
# --------------------------------------------------------------------- #


def check_homebrew() -> CheckResult:
    """Mac-only: Homebrew is the canonical install path for runtimes."""
    if sys.platform != "darwin":
        return CheckResult(
            id="homebrew",
            title="Homebrew (macOS only)",
            status="skip",
            detail="Not running on macOS",
        )
    found = _which("brew")
    if not found:
        return CheckResult(
            id="homebrew",
            title="Homebrew installed",
            status="warn",
            detail="brew is not on PATH",
            severity="warn",
            fix_hint="Install Homebrew. Most other fix_commands depend on it.",
            fix_command_darwin='/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"',
        )
    # Apple Silicon should have brew at /opt/homebrew; Intel at /usr/local.
    arch = os.uname().machine
    expected = "/opt/homebrew/bin/brew" if arch == "arm64" else "/usr/local/bin/brew"
    matches = found == expected
    return CheckResult(
        id="homebrew",
        title="Homebrew installed",
        status="pass" if matches else "warn",
        detail=(
            f"{found} (arch={arch})"
            if matches
            else f"{found} but expected {expected} for arch={arch}"
        ),
        severity="info" if matches else "warn",
        raw={"path": found, "arch": arch, "expected": expected},
    )


def check_xcode_clt() -> CheckResult:
    """Mac-only: xcode-select --print-path resolves and Command Line Tools work."""
    if sys.platform != "darwin":
        return CheckResult(
            id="xcode_clt",
            title="Xcode Command Line Tools (macOS only)",
            status="skip",
            detail="Not running on macOS",
        )
    rc, out, err = _run_capture(["xcode-select", "--print-path"])
    if rc != 0 or not out:
        return CheckResult(
            id="xcode_clt",
            title="Xcode Command Line Tools",
            status="warn",
            detail=(err or "xcode-select returned non-zero"),
            severity="warn",
            fix_hint="Install CLT; many uv/pip/npm install steps need a working clang/Make.",
            fix_command_darwin="xcode-select --install",
        )
    return CheckResult(
        id="xcode_clt",
        title="Xcode Command Line Tools",
        status="pass",
        detail=out,
        raw={"path": out},
    )


def check_architecture() -> CheckResult:
    """Identify CPU arch (informational; drives expected Homebrew prefix)."""
    arch = os.uname().machine if hasattr(os, "uname") else "?"
    detail = arch
    if sys.platform == "darwin" and arch == "x86_64":
        # Apple Silicon under Rosetta is x86_64. Mention.
        detail += " (Intel Mac, or Apple Silicon under Rosetta)"
    return CheckResult(
        id="architecture",
        title="CPU architecture",
        status="pass",
        detail=detail,
        raw={"arch": arch, "platform": _platform_label()},
    )


# --------------------------------------------------------------------- #
# Suite assemblies                                                       #
# --------------------------------------------------------------------- #


def runtime_checks(home: Path) -> list[CheckResult]:
    """Cross-platform runtime + filesystem checks shared by inspect/playbook."""
    return [
        check_architecture(),
        check_python3(),
        check_uv(),
        check_node(),
        check_git(),
        check_docker(),
        check_claude_dir(home),
        check_claude_json(home),
    ]


def darwin_specific_checks() -> list[CheckResult]:
    return [
        check_homebrew(),
        check_xcode_clt(),
    ]
