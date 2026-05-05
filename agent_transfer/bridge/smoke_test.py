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


def run(manifest: ManifestModel, *, home: Path | None = None) -> SmokeTestResult:
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

    # Check 3 — compose self-interrogation prompt for the caller to use.
    result.self_interrogation_prompt = SELF_INTERROGATION_PROMPT.format(
        capability_name=manifest.capability.name
    )

    return result
