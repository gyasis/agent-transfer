"""R12 regression tests — one per CRITICAL/HIGH adversarial finding.

Each test is named after the finding so future maintainers can map test
back to the original bug if it ever regresses.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

from agent_transfer.bridge.ingest import (
    SettingsCorruptError,
    _merge_json,
    _safe_mode_bits,
    ingest,
)
from agent_transfer.bridge.models import AssetEntry, Capability, ManifestModel
from agent_transfer.utils.transfer import (
    _rewrite_one_string,
    _rewrite_paths_recursive,
    rewrite_mcp_servers_for_target_home,
)


# ----------------------------------------------------------------------
# C#1 — Corrupt settings.json must NOT be silently wiped
# ----------------------------------------------------------------------


def test_c1_merge_json_refuses_to_wipe_corrupt_settings(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text("// user comment\n{ trailing-comma:, }\n")

    with pytest.raises(SettingsCorruptError) as exc:
        _merge_json(s, {"new_key": "value"})

    # Original content untouched on disk
    assert s.read_text() == "// user comment\n{ trailing-comma:, }\n"
    # Corrupt sidecar exists
    sidecars = list(tmp_path.glob("settings.json.corrupt-*"))
    assert sidecars, "Expected a .corrupt-<ts> sidecar copy"
    assert "Refusing to overwrite" in str(exc.value)


# ----------------------------------------------------------------------
# C#3 — Idempotent list-of-dicts dedup across key reorder
# ----------------------------------------------------------------------


def test_c3_merge_idempotent_for_dicts_with_reordered_keys(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text(json.dumps({"hooks": {"PreToolUse": [{"a": 1, "b": 2}]}}))

    incoming = {"hooks": {"PreToolUse": [{"b": 2, "a": 1}]}}  # SAME content, reordered
    _merge_json(s, incoming)
    after = json.loads(s.read_text())
    assert len(after["hooks"]["PreToolUse"]) == 1, (
        "list-of-dicts dedup must be order-insensitive (R12 C#3)"
    )


# ----------------------------------------------------------------------
# H#7 — mode_bits clamping
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "dest,mode,expected_min",
    [
        ("~/bin/script", 0o000, 0o100),                  # bin script forces exec
        ("~/.claude/hooks/x/pre.sh", 0o000, 0o100),       # hook forces exec
        ("~/.claude/skills/x.md", 0o000, 0o400),          # owner-readable minimum
        ("~/.claude/rules/x.md", 0o644, 0o644),           # already sane
        ("~/.claude/hooks/y/run.sh", 0o644, 0o744),       # hook gains exec on top
    ],
)
def test_h7_safe_mode_bits_clamps(dest, mode, expected_min):
    out = _safe_mode_bits(dest, mode)
    assert out & expected_min == expected_min


# ----------------------------------------------------------------------
# H#8 — Path-rewrite must not mutate substrings
# ----------------------------------------------------------------------


def test_h8_rewrite_does_not_mutate_unrelated_substring():
    out = _rewrite_one_string("/home/u-old/data", "/home/u", "/home/users/u")
    assert out == "/home/u-old/data", (
        "anchored regex must not mutate /home/u-old (R12 H#8)"
    )


def test_h8_rewrite_correct_for_real_prefix():
    out = _rewrite_one_string("/home/u/bin/y", "/home/u", "/home/users/u")
    assert out == "/home/users/u/bin/y"


def test_h8_rewrite_handles_end_of_string():
    out = _rewrite_one_string("/home/u", "/home/u", "/home/users/u")
    assert out == "/home/users/u"


def test_h8_rewrite_does_not_double_map():
    """Already-target-shaped strings must not be re-mapped."""
    out = _rewrite_one_string(
        "/home/users/u/file", "/home/u", "/home/users/u",
    )
    # /home/u doesn't appear at a path boundary in /home/users/u — anchored
    # pattern doesn't fire. Result unchanged.
    assert out == "/home/users/u/file"


# ----------------------------------------------------------------------
# H#10 — Path-rewrite recurses into nested dicts
# ----------------------------------------------------------------------


def test_h10_rewrite_recurses_into_nested_dict():
    src = {"env": {"NESTED": {"CFG": "/home/src/x"}}}
    out = _rewrite_paths_recursive(src, "/home/src", "/home/dst")
    assert out["env"]["NESTED"]["CFG"] == "/home/dst/x"


def test_h10_full_rewrite_handles_nested_through_public_api():
    out = rewrite_mcp_servers_for_target_home(
        servers={"x": {"env": {"NESTED": {"CFG": "/home/src/x"}}}},
        classifications={},
        target_home="/home/dst",
        source_home="/home/src",
    )
    assert out["x"]["env"]["NESTED"]["CFG"] == "/home/dst/x"


# ----------------------------------------------------------------------
# H#9 — Duplicate dest_path raises at Capability construction
# ----------------------------------------------------------------------


def test_h9_duplicate_dest_path_rejected():
    a = AssetEntry(
        path="x", dest_path="~/x", risk="green", conflict="overwrite",
        sha256="a" * 64, mode_bits=0o644,
    )
    b = AssetEntry(
        path="y", dest_path="~/x",  # SAME dest as a
        risk="yellow", conflict="overwrite", sha256="b" * 64, mode_bits=0o644,
    )
    with pytest.raises(Exception, match="duplicate dest_path"):
        Capability(name="t", description="d", intent="i", assets=[a, b])


# ----------------------------------------------------------------------
# C#2 — Asset bytes secret scan (CLI-level — direct check via secrets API)
# ----------------------------------------------------------------------


def test_c2_secret_scan_catches_token_inside_asset_body():
    """Pre-seal scan in CLI now scans bundle/ tree. Direct sanity here."""
    from agent_transfer.bridge.secrets import scan
    asset_body = "#!/bin/bash\nAPI_KEY=ghp_abcdefghijklmnopqrstuvwxyz1234567\n"
    findings = scan(asset_body)
    assert findings, "github PAT in asset body must be caught by scan()"
    assert any(f.pattern == "github_pat" for f in findings)


# ----------------------------------------------------------------------
# H#4 — rollback.sh refuses to run with mismatched HOME
# ----------------------------------------------------------------------


def test_h4_rollback_sh_has_home_assert():
    from agent_transfer.bridge.rollback import _ROLLBACK_SH_BODY
    assert "manifest home" in _ROLLBACK_SH_BODY
    assert "current HOME" in _ROLLBACK_SH_BODY
    assert "refusing to restore into privileged path" in _ROLLBACK_SH_BODY


# ----------------------------------------------------------------------
# H#5 — rollback includes directories in find
# ----------------------------------------------------------------------


def test_h5_rollback_sh_includes_directories():
    from agent_transfer.bridge.rollback import _ROLLBACK_SH_BODY
    assert "-type d" in _ROLLBACK_SH_BODY
    assert "-print0" in _ROLLBACK_SH_BODY


# ----------------------------------------------------------------------
# H#6 — snapshot does not call resolve()
# ----------------------------------------------------------------------


def test_h6_snapshot_uses_unresolved_paths(tmp_path):
    """snapshot() must not call .resolve() on dest paths — match apply-side."""
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude").mkdir()
    (home / "bin").mkdir()
    (home / "bin" / "x").write_text("#!/bin/sh\necho\n")

    from agent_transfer.bridge.rollback import snapshot
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    snapshot(["~/bin/x"], bundle, home=home)

    import tarfile
    with tarfile.open(bundle / "rollback.tar.gz") as tar:
        names = tar.getnames()
    # bundle_writes inside manifest is the unresolved expansion
    manifest_data = None
    with tarfile.open(bundle / "rollback.tar.gz") as tar:
        f = tar.extractfile("manifest-of-bundle-writes.json")
        manifest_data = json.loads(f.read())
    # Should contain str(home / "bin" / "x"), NOT the resolved equivalent.
    assert manifest_data["bundle_writes"][0] == str(home / "bin" / "x")


def test_g9_snapshot_preserves_existing_baseline(tmp_path):
    """G9 — second snapshot() call must NOT overwrite the first.

    The first ingest's snapshot captures the authoritative pre-install
    state. A second ingest of the same bundle (re-sync, idempotent retry)
    must leave that baseline intact, otherwise rollback would restore the
    POST-install state and silently lose the original "before".
    """
    import tarfile

    home = tmp_path / "home"
    home.mkdir()
    target = home / "config.txt"
    target.write_text("ORIGINAL")

    from agent_transfer.bridge.rollback import snapshot

    bundle = tmp_path / "bundle"
    bundle.mkdir()

    # First snapshot: captures ORIGINAL.
    snapshot(["~/config.txt"], bundle, home=home)
    with tarfile.open(bundle / "rollback.tar.gz") as tar:
        f = tar.extractfile("before/home/config.txt")
        assert f.read() == b"ORIGINAL"

    # Simulate post-install state.
    target.write_text("INSTALLED")

    # Second snapshot: must NOT overwrite the baseline.
    snapshot(["~/config.txt"], bundle, home=home)
    with tarfile.open(bundle / "rollback.tar.gz") as tar:
        f = tar.extractfile("before/home/config.txt")
        assert f.read() == b"ORIGINAL", (
            "G9 regression: second snapshot overwrote the baseline with "
            "post-install state. Rollback would now restore INSTALLED, not "
            "ORIGINAL."
        )

    # Explicit override still works (compose-time regeneration).
    snapshot(["~/config.txt"], bundle, home=home, preserve_existing=False)
    with tarfile.open(bundle / "rollback.tar.gz") as tar:
        f = tar.extractfile("before/home/config.txt")
        assert f.read() == b"INSTALLED"


def test_h_ingest_result_signals_rollback_reuse(tmp_path):
    """H — IngestResult.rollback_reused tells the user the second ingest
    preserved the first ingest's baseline (G9) rather than capturing
    fresh pre-install state. Silent reuse is the original gap; this is
    the user-visible signal.
    """
    from agent_transfer.bridge.ingest import ingest
    from datetime import datetime

    home = tmp_path / "home"
    home.mkdir()
    target = home / ".claude" / "skills" / "test.md"
    target.parent.mkdir(parents=True)

    # Build a minimal bundle by hand.
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "bundle").mkdir()
    src = bundle_dir / "bundle" / "test.md"
    src.write_text("# from bundle\n")

    import hashlib
    sha = hashlib.sha256(src.read_bytes()).hexdigest()

    from agent_transfer.bridge.models import (
        AssetEntry, Capability, ManifestModel,
    )
    manifest = ManifestModel(
        generated_at=datetime.utcnow(),
        source_machine_hint="test",
        capability=Capability(
            name="t", description="x", intent="x",
            assets=[AssetEntry(
                path="test.md",
                dest_path="~/.claude/skills/test.md",
                risk="green",
                conflict="overwrite",
                sha256=sha,
                mode_bits=0o644,
            )],
        ),
    )
    (bundle_dir / "manifest.json").write_text(manifest.model_dump_json())

    # First ingest: rollback.tar.gz didn't exist before — should NOT be reused.
    r1 = ingest(bundle_dir, home=home, auto_yes=True, interactive=False)
    assert r1.rollback_reused is False, "first ingest should NOT signal reuse"

    # Second ingest: rollback.tar.gz exists from first run.
    r2 = ingest(bundle_dir, home=home, auto_yes=True, interactive=False)
    assert r2.rollback_reused is True, (
        "second ingest must signal that rollback baseline was preserved "
        "(silent reuse is the original gap)"
    )
