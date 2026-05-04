"""T022 — SC-001 ship gate: cascade-memory-shaped roundtrip on a sandbox HOME.

Unblocked by T037 (Wave 6). Uses the Python API directly (compose →
selection_matrix → preview → manifest → bundle write → ingest) instead
of shelling to `ab`, so it runs in CI without an installed entry point.

The fixture HOME mimics the structure of cascade-memory: a CORE-anchored
skill, a strict-bin reference, a hook, and a rule.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
from pathlib import Path

from agent_transfer.bridge.briefing import render as _render, render_sections
from agent_transfer.bridge.compose import compose
from agent_transfer.bridge.ingest import ingest
from agent_transfer.bridge.models import ManifestModel
from agent_transfer.bridge.preview import preview_and_confirm
from agent_transfer.bridge.rollback import snapshot as _rollback_snapshot
from agent_transfer.bridge.selection_matrix import present


def _build_source_home(tmp_path: Path) -> Path:
    """Build a fixture HOME with a cascade-memory-shaped capability."""
    home = tmp_path / "src-home"
    claude = home / ".claude"
    skills = claude / "skills"
    rules = claude / "rules" / "domains"
    hooks = claude / "hooks" / "unified-memory"
    bin_dir = home / "bin"
    for d in (skills, rules, hooks, bin_dir):
        d.mkdir(parents=True)

    # CORE — skill with capability name in its filename
    (skills / "memory-search.md").write_text(
        "---\nname: memory-search\ndescription: cascade-memory anchor for past sessions.\n---\n"
        "# memory-search\nCalls `~/bin/session-search` for the actual lookup.\n"
    )

    # COMPANIONS — bin script referenced strictly
    ss = bin_dir / "session-search"
    ss.write_text("#!/usr/bin/env bash\nset -e\nargs=$@\nexit 0\n")
    ss.chmod(0o755)

    return home


def _seal_bundle(home: Path, bundle_root: Path) -> Path:
    """Run the source-side pipeline: compose -> present -> preview -> manifest -> bundle."""
    cap = compose("cascade-memory", home=home)
    cap = present(cap, interactive=False)
    cap = preview_and_confirm(
        cap, bundle_root, interactive=False, auto_yes=True
    )

    from datetime import datetime, timezone
    manifest = ManifestModel(
        generated_at=datetime.now(timezone.utc),
        source_machine_hint="linux-wsl2",
        capability=cap,
    )
    manifest = manifest.model_copy(update={"briefing_sections": render_sections(manifest)})

    (bundle_root / "manifest.json").write_text(
        json.dumps(json.loads(manifest.model_dump_json()), indent=2)
    )
    (bundle_root / "BRIEFING.md").write_text(_render(manifest))

    asset_root = bundle_root / "bundle"
    asset_root.mkdir(exist_ok=True)
    for a in cap.assets:
        if a.dest_path.startswith("~/"):
            src = home / a.dest_path[2:]
        else:
            src = Path(a.dest_path)
        if not src.exists():
            continue
        dst = asset_root / a.path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        # Re-stat: ensure copy preserved exec bit on bin scripts
        if str(src).endswith("session-search"):
            assert dst.stat().st_mode & 0o111

    _rollback_snapshot(
        [a.dest_path for a in cap.assets], bundle_root, home=home,
    )
    return bundle_root


def test_cascade_memory_python_api_roundtrip(tmp_path: Path):
    """SC-001 ship gate via the Python API.

    Steps:
      1. Build source HOME with cascade-memory-shaped tree.
      2. Seal bundle from source HOME.
      3. Ingest into a clean sandbox HOME.
      4. Verify all bundled assets present at correct dest with correct mode.
      5. Verify rollback.tar.gz + rollback.sh exist.
    """
    src_home = _build_source_home(tmp_path)
    bundle_root = tmp_path / "bundle-cascade-memory"
    _seal_bundle(src_home, bundle_root)

    # Sanity on bundle structure
    assert (bundle_root / "manifest.json").exists()
    assert (bundle_root / "BRIEFING.md").exists()
    assert (bundle_root / "bundle").is_dir()
    assert (bundle_root / "rollback.tar.gz").exists()
    assert (bundle_root / "rollback.sh").exists()

    # Briefing has all 7 mandatory sections
    briefing = (bundle_root / "BRIEFING.md").read_text()
    for section in (
        "Identity",
        "Capability Description",
        "Inventory",
        "Build Instructions",
        "Ingest Instructions",
        "Verification",
        "Rollback",
    ):
        assert section in briefing, f"Briefing missing section: {section!r}"

    # Now ingest into a sandbox HOME
    dst_home = tmp_path / "dst-home"
    dst_home.mkdir()
    (dst_home / ".claude").mkdir()

    result = ingest(bundle_root, home=dst_home, auto_yes=True, interactive=False)

    assert not result.errors, f"ingest errors: {result.errors}"

    # Verify expected assets landed
    assert (dst_home / ".claude" / "skills" / "memory-search.md").exists()
    bin_script = dst_home / "bin" / "session-search"
    assert bin_script.exists(), "session-search not in destination ~/bin/"
    # FR-011 — exec bit must survive the round-trip
    assert bin_script.stat().st_mode & 0o111, "exec bit lost on session-search"

    # Smoke didn't catastrophically fail; ripgrep dependency may be flagged
    # since the test environment doesn't guarantee ripgrep, but file presence
    # checks must all pass.
    asset_failures = [f for f in result.smoke_failures if "Missing" in f or "sha256" in f or "mode_bits" in f]
    assert not asset_failures, f"smoke asset failures: {asset_failures}"
