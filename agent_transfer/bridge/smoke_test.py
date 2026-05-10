"""Post-install smoke test — three checks per research.md §6.

1. Asset presence + permissions: every declared AssetEntry exists at
   dest_path with matching sha256 and mode_bits.
2. Capability-specific functional check (bundle-declared in
   capability.dependencies — not implemented in v1; reserved).
3. Self-interrogation: returns the exact prompt string the receiving
   Claude should answer. Drift check is performed by the caller.

Constitution: R6 (no hardcoded ~/ — paths come from manifest).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from agent_transfer.bridge.models import AssetEntry, ManifestModel


SELF_INTERROGATION_PROMPT = (
    "List the new skills, hooks, and rules currently loaded in your config "
    "that are part of the {capability_name} capability. For each, say what "
    "it does in 1 sentence."
)


@dataclass
class SmokeTestResult:
    passed: bool = True
    failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    self_interrogation_prompt: str = ""

    def fail(self, msg: str) -> None:
        self.passed = False
        self.failures.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def _expand_dest(dest_path: str, home: Path) -> Path:
    if dest_path.startswith("~/"):
        return home / dest_path[2:]
    if dest_path == "~":
        return home
    return Path(dest_path)


def _sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    try:
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def _check_asset(asset: AssetEntry, home: Path, result: SmokeTestResult) -> None:
    dest = _expand_dest(asset.dest_path, home)
    if not dest.exists():
        result.fail(f"Missing: {asset.dest_path}")
        return
    actual_hash = _sha256_of(dest)
    if actual_hash and actual_hash != asset.sha256:
        result.fail(
            f"sha256 mismatch at {asset.dest_path}: "
            f"expected {asset.sha256[:12]}…, got {actual_hash[:12]}…"
        )
    try:
        actual_mode = os.stat(dest).st_mode & 0o7777
    except OSError:
        result.warn(f"Could not stat {asset.dest_path} for mode check")
        return
    if actual_mode != asset.mode_bits:
        result.fail(
            f"mode_bits mismatch at {asset.dest_path}: "
            f"expected {oct(asset.mode_bits)}, got {oct(actual_mode)}"
        )


def _check_dependencies(manifest: ManifestModel, result: SmokeTestResult) -> None:
    for dep in manifest.capability.dependencies:
        if not shutil.which(dep):
            result.fail(f"Required OS dependency not on PATH: {dep!r}")


_SMOKE_COMMAND_TIMEOUT_S = 10

# D (Hunter A F8) — minimal sandboxed PATH for smoke commands.
# Pre-fix: the smoke runner inherited the composer's full PATH, so a
# command like `sio --version` could pass on a developer box (where
# ~/.local/bin is on PATH) and silently fail on a clean receiver. Worse,
# combined with the registry-as-trust-boundary issue (F3), an attacker-
# planted YAML could exec arbitrary tooling from a non-standard PATH.
# Reset PATH to a vetted minimum + the destination's ~/bin and
# ~/.local/bin so capability-declared binaries can still resolve.
_SMOKE_SAFE_PATH_BASE = "/usr/local/bin:/usr/bin:/bin"


def _smoke_env(home: Path) -> dict[str, str]:
    """Build a scrubbed env for sh -c invocation (D — F8)."""
    base = {
        "HOME": str(home),
        "PATH": (
            f"{home}/bin:{home}/.local/bin:{_SMOKE_SAFE_PATH_BASE}"
        ),
        # Locale so command output (used in failure-tail) decodes sanely.
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
        # SHELL — `sh -c` ignores it but downstream subshells may peek.
        "SHELL": "/bin/sh",
    }
    # Some commands genuinely need TERM (less, vi, color decisions).
    if "TERM" in os.environ:
        base["TERM"] = os.environ["TERM"]
    return base


def _check_smoke_commands(
    manifest: ManifestModel,
    home: Path,
    result: SmokeTestResult,
    *,
    skip: bool = False,
) -> None:
    """G6 — run capability-declared smoke commands; each must exit 0.

    Catches partial installs where file-presence checks pass but the
    capability isn't actually functional (e.g. a `sio` skill ships but
    the `sio` binary is missing on PATH; a hook block lands but a parse
    error earlier in the file means it never reaches it).

    D (Hunter A F3+F8) — env is scrubbed: only HOME / PATH (vetted set
    + destination ~/bin) / LANG / LC_ALL / SHELL / TERM are forwarded.
    Inheriting the receiver's full env opens a privilege-escalation
    path through registry-planted smoke_commands.

    Commands are hard-capped at 10 seconds (per-command timeout override
    is not yet a manifest field — defer if needed).

    `skip=True` suppresses execution; the result records a warning so
    the user knows smoke was opt-out'd. Used by the `--no-smoke` CLI
    flag for environments where running arbitrary shell from a bundle
    is itself the threat.
    """
    cmds = list(manifest.capability.smoke_commands)
    if not cmds:
        return
    if skip:
        result.warn(
            f"smoke commands skipped by user opt-out ({len(cmds)} declared)"
        )
        return

    env = _smoke_env(home)

    for cmd in cmds:
        try:
            proc = subprocess.run(
                ["sh", "-c", cmd],
                capture_output=True,
                text=True,
                timeout=_SMOKE_COMMAND_TIMEOUT_S,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired:
            result.fail(
                f"smoke command timed out after {_SMOKE_COMMAND_TIMEOUT_S}s: {cmd!r}"
            )
            continue
        except OSError as e:
            result.fail(f"smoke command could not start: {cmd!r}: {e}")
            continue
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()
            tail_text = " | ".join(tail[-3:])[:400]
            result.fail(
                f"smoke command exited {proc.returncode}: {cmd!r}"
                + (f" — {tail_text}" if tail_text else "")
            )


def run(
    manifest: ManifestModel,
    *,
    home: Path | None = None,
    skip_smoke_commands: bool = False,
) -> SmokeTestResult:
    """Run smoke test against the destination machine.

    The caller (ingest CLI in T035) is responsible for asking the
    self_interrogation_prompt to the receiving Claude session and parsing
    the response. This function just composes the prompt and validates
    deterministic state (file presence, hashes, mode bits, deps).
    """
    home = home or Path.home()
    result = SmokeTestResult()

    if manifest is None:
        result.fail("smoke_test.run() called with manifest=None")
        return result

    # Check 1 — every asset is present, hash-correct, mode-correct.
    for asset in manifest.capability.assets:
        _check_asset(asset, home, result)

    # Check 2 — OS-level deps.
    _check_dependencies(manifest, result)

    # Check 3 — capability-declared smoke commands (G6).
    _check_smoke_commands(manifest, home, result, skip=skip_smoke_commands)

    # Check 4 — compose self-interrogation prompt for the caller to use.
    result.self_interrogation_prompt = SELF_INTERROGATION_PROMPT.format(
        capability_name=manifest.capability.name
    )

    return result
