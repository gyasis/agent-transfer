"""T037 — Integration test: re-running ingestion is idempotent (FR-014).

Specifically: settings.json hook entries are not duplicated when the
ingest pipeline runs twice. The ingest core's _merge_json deep-merges
dicts and unions lists by repr — the test confirms a second pass adds
nothing.
"""

from __future__ import annotations

import json
import os
import stat
import tarfile
from pathlib import Path

import pytest

from agent_transfer.bridge.ingest import _merge_json, ingest
from agent_transfer.bridge.models import (
    AssetEntry,
    Capability,
    ManifestModel,
)


def _seal_one_asset_bundle(tmp_path: Path, asset_relpath: str, asset_bytes: bytes) -> Path:
    """Build a minimal valid bundle directory with one asset."""
    bundle = tmp_path / "bundle-test"
    bundle.mkdir()
    (bundle / "bundle").mkdir()
    asset_in_bundle = bundle / "bundle" / asset_relpath
    asset_in_bundle.parent.mkdir(parents=True, exist_ok=True)
    asset_in_bundle.write_bytes(asset_bytes)

    import hashlib
    sha = hashlib.sha256(asset_bytes).hexdigest()
    asset = AssetEntry(
        path=asset_relpath,
        dest_path=f"~/{asset_relpath}",
        risk="green",
        conflict="overwrite",
        sha256=sha,
        mode_bits=0o644,
    )
    cap = Capability(
        name="test", description="t", intent="t",
        assets=[asset], dependencies=[],
    )
    manifest = ManifestModel(
        generated_at="2026-05-04T10:00:00Z",
        source_machine_hint="linux-wsl2",
        capability=cap,
    )
    (bundle / "manifest.json").write_text(manifest.model_dump_json(indent=2))
    (bundle / "BRIEFING.md").write_text("# placeholder\n")
    return bundle


# ----------------------------------------------------------------------
# Direct _merge_json test — fast and surgical
# ----------------------------------------------------------------------


def test_merge_json_does_not_duplicate_existing_entry(tmp_path: Path):
    s = tmp_path / "settings.json"
    initial = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Edit", "hooks": [{"type": "command", "command": "x"}]}
            ]
        }
    }
    s.write_text(json.dumps(initial))

    incoming = initial  # exact same payload
    _merge_json(s, incoming)
    after = json.loads(s.read_text())
    assert len(after["hooks"]["PreToolUse"]) == 1, "duplicated existing entry"


def test_merge_json_appends_new_entry_then_idempotent_on_second_run(tmp_path: Path):
    s = tmp_path / "settings.json"
    s.write_text(json.dumps({"hooks": {"PreToolUse": [{"a": 1}]}}))

    incoming = {"hooks": {"PreToolUse": [{"a": 1}, {"b": 2}]}}
    _merge_json(s, incoming)
    after_first = json.loads(s.read_text())
    assert after_first["hooks"]["PreToolUse"] == [{"a": 1}, {"b": 2}]

    # Second pass with the same incoming should be a no-op.
    _merge_json(s, incoming)
    after_second = json.loads(s.read_text())
    assert after_first == after_second


def test_merge_json_preserves_user_scalar(tmp_path: Path):
    s = tmp_path / "settings.json"
    s.write_text(json.dumps({"theme": "dark"}))

    _merge_json(s, {"theme": "light"})
    assert json.loads(s.read_text())["theme"] == "dark", "user value must win on scalar conflict"


def test_merge_json_adds_new_top_level_key(tmp_path: Path):
    s = tmp_path / "settings.json"
    s.write_text(json.dumps({"theme": "dark"}))

    _merge_json(s, {"env": {"DEBUG": "1"}})
    after = json.loads(s.read_text())
    assert after["theme"] == "dark"
    assert after["env"] == {"DEBUG": "1"}


# ----------------------------------------------------------------------
# Full ingest idempotency test — second ingest of the same bundle
# ----------------------------------------------------------------------


def test_full_ingest_twice_is_idempotent(tmp_path: Path):
    """Run ingest twice with the same bundle → second pass is a no-op net."""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / ".claude").mkdir()

    bundle = _seal_one_asset_bundle(tmp_path, ".claude/test.md", b"# hello\n")

    r1 = ingest(bundle, home=sandbox, auto_yes=True, interactive=False)
    assert not r1.errors, r1.errors
    assert (sandbox / ".claude" / "test.md").read_text() == "# hello\n"

    # Snapshot mtime + size of the destination
    stat1 = (sandbox / ".claude" / "test.md").stat()

    r2 = ingest(bundle, home=sandbox, auto_yes=True, interactive=False)
    assert not r2.errors, r2.errors
    stat2 = (sandbox / ".claude" / "test.md").stat()

    assert stat1.st_size == stat2.st_size
    # Content unchanged
    assert (sandbox / ".claude" / "test.md").read_text() == "# hello\n"
