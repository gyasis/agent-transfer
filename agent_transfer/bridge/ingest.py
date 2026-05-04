"""Destination-side ingestion — read briefing, walk inventory, install per policy.

Implements per-asset conflict resolution (skip / merge / overwrite / ask)
and idempotent merges for ~/.claude.json + settings.json. Calls the
existing rollback generator BEFORE any write so the safety net is in
place.

Constitution:
- R6: paths come from caller / manifest, never hardcoded.
- R7: tarfile extraction goes through safe-extract guard.
- R8: never carry secrets — bundle was already scanned at seal time.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tarfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Mapping, Optional

from agent_transfer.bridge.models import AssetEntry, Capability, ManifestModel
from agent_transfer.bridge.rollback import snapshot as _rollback_snapshot
from agent_transfer.bridge.smoke_test import run as _run_smoke


@dataclass
class IngestResult:
    installed: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    merged: List[str] = field(default_factory=list)
    declined: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    smoke_failures: List[str] = field(default_factory=list)


def _ask(prompt: str, *, auto_yes: bool, interactive: bool) -> bool:
    if auto_yes:
        return True
    if not interactive or not sys.stdin.isatty():
        return False
    try:
        ans = input(prompt + " [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return ans in {"y", "yes"}


def _expand_dest(dest_path: str, home: Path) -> Path:
    if dest_path.startswith("~/"):
        return home / dest_path[2:]
    if dest_path == "~":
        return home
    return Path(dest_path)


def _safe_extract(tar: tarfile.TarFile, target_dir: Path) -> None:
    """Extract a tarfile, rejecting path traversal / abs / symlink escapes (R7)."""
    target_dir = target_dir.resolve()
    for member in tar.getmembers():
        member_path = (target_dir / member.name).resolve()
        if not str(member_path).startswith(str(target_dir) + os.sep) and member_path != target_dir:
            raise RuntimeError(f"Unsafe tar member: {member.name!r}")
        if member.issym() or member.islnk():
            raise RuntimeError(f"Tar contains symlink/hardlink: {member.name!r}")
    tar.extractall(target_dir)


def _sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _merge_json(target_path: Path, incoming: dict) -> None:
    """Idempotent additive merge of incoming dict into target JSON file.

    Used for ~/.claude.json and ~/.claude/settings.json. Keys present in
    BOTH are deep-merged (dict-only). Lists are union'd by string repr.
    Existing user values are NEVER replaced.
    """
    existing: dict = {}
    if target_path.exists():
        try:
            existing = json.loads(target_path.read_text())
        except json.JSONDecodeError:
            existing = {}

    def _merge(a: dict, b: Mapping) -> dict:
        out = dict(a)
        for k, v in b.items():
            if k not in out:
                out[k] = v
            elif isinstance(out[k], dict) and isinstance(v, Mapping):
                out[k] = _merge(out[k], v)
            elif isinstance(out[k], list) and isinstance(v, list):
                seen = {repr(x) for x in out[k]}
                for item in v:
                    if repr(item) not in seen:
                        out[k].append(item)
                        seen.add(repr(item))
            # else: existing user value wins (idempotent)
        return out

    merged = _merge(existing, incoming)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(merged, indent=2))


def _open_bundle(bundle_path: Path) -> Path:
    """Bundle can be a directory or a .tar.gz. Returns path to the dir."""
    if bundle_path.is_dir():
        return bundle_path
    if bundle_path.suffix in {".gz", ".tgz"} or str(bundle_path).endswith(".tar.gz"):
        target = bundle_path.parent / (bundle_path.stem.replace(".tar", "") + "-extracted")
        target.mkdir(exist_ok=True)
        with tarfile.open(bundle_path, "r:gz") as tar:
            _safe_extract(tar, target)
        return target
    raise ValueError(f"Bundle must be a directory or .tar.gz: {bundle_path}")


def _apply_one_asset(
    asset: AssetEntry,
    bundle_dir: Path,
    home: Path,
    *,
    auto_yes: bool,
    interactive: bool,
    result: IngestResult,
) -> None:
    src = bundle_dir / "bundle" / asset.path
    if not src.exists():
        result.errors.append(f"Bundle missing asset bytes for {asset.path}")
        return

    # Verify hash before install (corruption / tampering check)
    actual = _sha256_of(src)
    if actual != asset.sha256:
        result.errors.append(
            f"sha256 mismatch on bundle asset {asset.path}: expected {asset.sha256[:12]}…, got {actual[:12]}…"
        )
        return

    dest = _expand_dest(asset.dest_path, home)

    # Risk gate
    if asset.risk in ("yellow", "red"):
        ok = _ask(
            f"Install {asset.risk.upper()} asset {asset.dest_path}?",
            auto_yes=auto_yes, interactive=interactive,
        )
        if not ok:
            result.declined.append(asset.dest_path)
            return

    # Conflict policy
    policy = asset.conflict
    if dest.exists() and policy == "skip":
        result.skipped.append(asset.dest_path)
        return
    if dest.exists() and policy == "ask":
        ok = _ask(f"Overwrite existing {asset.dest_path}?", auto_yes=auto_yes, interactive=interactive)
        if not ok:
            result.skipped.append(asset.dest_path)
            return

    if policy == "merge" and dest.exists() and dest.suffix == ".json":
        try:
            incoming = json.loads(src.read_text())
        except json.JSONDecodeError:
            result.errors.append(f"merge requested for non-JSON file {asset.path}")
            return
        _merge_json(dest, incoming)
        result.merged.append(asset.dest_path)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        os.chmod(dest, asset.mode_bits)  # FR-011 — preserve executable bit
        result.installed.append(asset.dest_path)


def ingest(
    bundle_path: Path,
    *,
    home: Optional[Path] = None,
    auto_yes: bool = False,
    interactive: bool = True,
) -> IngestResult:
    """Install an AgentBridge bundle on this machine.

    Args:
        bundle_path: Either a bundle directory or a .tar.gz file.
        home: Override $HOME (for tests with sandbox HOME).
        auto_yes: Skip prompts; treat all Yellow/Red as confirmed.
        interactive: Allow stdin prompts; otherwise behave as auto-no.

    Returns:
        IngestResult with installed / skipped / merged / declined / errors
        / smoke_failures lists.
    """
    home = home or Path.home()
    bundle_dir = _open_bundle(Path(bundle_path))
    result = IngestResult()

    # Read manifest
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.exists():
        result.errors.append(f"Bundle missing manifest.json at {manifest_path}")
        return result
    try:
        manifest = ManifestModel.model_validate_json(manifest_path.read_text())
    except Exception as e:  # pragma: no cover — pydantic raises ValidationError
        result.errors.append(f"manifest.json failed validation: {e}")
        return result

    # Refuse incompatible major version
    major = manifest.schema_version.split(".", 1)[0]
    if major != "1":
        result.errors.append(
            f"Bundle schema_version {manifest.schema_version} is not 1.x — refusing."
        )
        return result

    # Generate rollback snapshot BEFORE any write (FR-016)
    target_dest_paths = [a.dest_path for a in manifest.capability.assets]
    _rollback_snapshot(target_dest_paths, bundle_dir, home=home)

    # Apply each asset
    for asset in manifest.capability.assets:
        _apply_one_asset(
            asset, bundle_dir, home,
            auto_yes=auto_yes, interactive=interactive, result=result,
        )

    # Smoke test (FR-017)
    smoke = _run_smoke(manifest, home=home)
    if not smoke.passed:
        result.smoke_failures = smoke.failures

    return result
