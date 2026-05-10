"""G1/H8 — markdown conflict policy + section-marker merge.

Pre-fix bug: every .md asset defaulted to conflict=merge, but ingest only
implemented JSON merge — non-JSON merge fell through with an error
("merge requested for non-JSON file"). Result: any pre-existing .md at the
destination silently failed install. Affects every capability that ships
skill or rule markdown files (i.e., every capability).

Post-fix:
- Capability-owned .md files (skills, rules) default to conflict=overwrite.
- CLAUDE.md and any explicitly-merge-marked .md uses section-marker merge.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_transfer.bridge.ingest import (
    _merge_markdown,
    _MarkdownMergeError,
)
from agent_transfer.utils.config_manager import emit_asset_entries


# -- Default conflict policy -------------------------------------------------


def test_g1_skill_md_defaults_to_overwrite(tmp_path):
    """A regular skill .md file no longer gets the unimplemented merge default."""
    home = tmp_path / "home"
    skills = home / ".claude" / "skills"
    skills.mkdir(parents=True)
    sio = skills / "sio-scan.md"
    sio.write_text("# sio-scan skill\n")

    [entry] = emit_asset_entries([sio], home=home)

    assert entry["conflict"] == "overwrite", (
        "G1 regression: capability-owned skill .md should default to "
        "overwrite, not the unimplemented merge default."
    )


def test_g1_rule_md_defaults_to_overwrite(tmp_path):
    home = tmp_path / "home"
    rules = home / ".claude" / "rules" / "tools"
    rules.mkdir(parents=True)
    rule = rules / "sio.md"
    rule.write_text("# sio rule\n")

    [entry] = emit_asset_entries([rule], home=home)
    assert entry["conflict"] == "overwrite"


def test_g1_claude_md_keeps_merge_default(tmp_path):
    """CLAUDE.md is the one .md case that legitimately wants merge."""
    home = tmp_path / "home"
    home.mkdir()
    cm = home / "CLAUDE.md"
    cm.write_text("# user CLAUDE.md\n")

    [entry] = emit_asset_entries([cm], home=home)
    assert entry["conflict"] == "merge"


# -- Section-marker merge --------------------------------------------------


def test_h8_merge_appends_when_block_absent(tmp_path):
    target = tmp_path / "CLAUDE.md"
    target.write_text("# Existing\n\nUser content here.\n")

    incoming = (
        "<!-- BEGIN agentbridge:sio -->\n"
        "## SIO Keyword Detection\n"
        "Stuff\n"
        "<!-- END agentbridge:sio -->\n"
    )
    _merge_markdown(target, incoming)

    out = target.read_text()
    assert "User content here." in out, "destination's existing content must survive"
    assert "<!-- BEGIN agentbridge:sio -->" in out
    assert "## SIO Keyword Detection" in out
    assert "<!-- END agentbridge:sio -->" in out


def test_h8_merge_replaces_existing_block_idempotent(tmp_path):
    """Re-ingest of an updated fragment replaces in-place (idempotence)."""
    target = tmp_path / "CLAUDE.md"
    target.write_text(
        "# CLAUDE.md\n\n"
        "Some user note.\n\n"
        "<!-- BEGIN agentbridge:sio -->\n"
        "OLD CONTENT\n"
        "<!-- END agentbridge:sio -->\n\n"
        "Trailing user note.\n"
    )

    incoming = (
        "<!-- BEGIN agentbridge:sio -->\n"
        "NEW CONTENT v2\n"
        "<!-- END agentbridge:sio -->\n"
    )
    _merge_markdown(target, incoming)

    out = target.read_text()
    assert "Some user note." in out
    assert "Trailing user note." in out
    assert "OLD CONTENT" not in out
    assert "NEW CONTENT v2" in out
    # Only one block, not duplicated.
    assert out.count("BEGIN agentbridge:sio") == 1


def test_h8_merge_does_not_touch_other_capability_blocks(tmp_path):
    target = tmp_path / "CLAUDE.md"
    target.write_text(
        "# CLAUDE.md\n\n"
        "<!-- BEGIN agentbridge:cascade-memory -->\n"
        "memory rules\n"
        "<!-- END agentbridge:cascade-memory -->\n\n"
        "<!-- BEGIN agentbridge:sio -->\n"
        "old sio\n"
        "<!-- END agentbridge:sio -->\n"
    )

    incoming = (
        "<!-- BEGIN agentbridge:sio -->\n"
        "new sio\n"
        "<!-- END agentbridge:sio -->\n"
    )
    _merge_markdown(target, incoming)
    out = target.read_text()

    assert "memory rules" in out, "other capability's block must be untouched"
    assert "new sio" in out
    assert "old sio" not in out


def test_h8_merge_rejects_no_markers(tmp_path):
    target = tmp_path / "CLAUDE.md"
    target.write_text("# CLAUDE.md\n")
    with pytest.raises(_MarkdownMergeError, match="exactly one"):
        _merge_markdown(target, "raw fragment without markers\n")


def test_e_merge_rejects_marker_for_other_capability(tmp_path):
    """E (Hunter A F5) — incoming marker name must match the capability."""
    target = tmp_path / "CLAUDE.md"
    target.write_text("# CLAUDE.md\n")
    incoming = (
        "<!-- BEGIN agentbridge:cascade-memory -->\n"
        "rules\n"
        "<!-- END agentbridge:cascade-memory -->\n"
    )
    with pytest.raises(_MarkdownMergeError, match="does not belong to capability 'sio'"):
        _merge_markdown(target, incoming, capability_name="sio")


def test_e_merge_accepts_exact_capability_name(tmp_path):
    target = tmp_path / "CLAUDE.md"
    target.write_text("# CLAUDE.md\n")
    incoming = (
        "<!-- BEGIN agentbridge:sio -->\n"
        "rules\n"
        "<!-- END agentbridge:sio -->\n"
    )
    _merge_markdown(target, incoming, capability_name="sio")
    assert "BEGIN agentbridge:sio" in target.read_text()


def test_e_merge_accepts_subnamespace(tmp_path):
    """sio.routing is a sub-block of capability sio — allowed."""
    target = tmp_path / "CLAUDE.md"
    target.write_text("# CLAUDE.md\n")
    incoming = (
        "<!-- BEGIN agentbridge:sio.routing -->\n"
        "routing\n"
        "<!-- END agentbridge:sio.routing -->\n"
    )
    _merge_markdown(target, incoming, capability_name="sio")
    assert "BEGIN agentbridge:sio.routing" in target.read_text()


def test_e_merge_rejects_prefix_collision(tmp_path):
    """`siofoo` is NOT a sub-namespace of `sio` (no separating `.`)."""
    target = tmp_path / "CLAUDE.md"
    target.write_text("# CLAUDE.md\n")
    incoming = (
        "<!-- BEGIN agentbridge:siofoo -->\n"
        "x\n"
        "<!-- END agentbridge:siofoo -->\n"
    )
    with pytest.raises(_MarkdownMergeError, match="does not belong to"):
        _merge_markdown(target, incoming, capability_name="sio")


def test_f_post_merge_scan_catches_preexisting_secret(tmp_path):
    """F (Hunter B G1/H2 adjacent) — post-merge re-scan flags secrets in
    the resulting file even when the bundle's own block is clean.

    Models a destination CLAUDE.md that already contains a credential;
    our merge adds an unrelated block, but the merged file still has the
    secret. Should produce a non-fatal warning.
    """
    from agent_transfer.bridge.ingest import _post_merge_secret_scan
    target = tmp_path / "CLAUDE.md"
    target.write_text(
        "# CLAUDE.md\n\n"
        "Bearer abcdef0123456789ABCDEF0123456789\n"  # pre-existing secret
        "\n"
        "<!-- BEGIN agentbridge:sio -->\n"
        "clean rules\n"
        "<!-- END agentbridge:sio -->\n"
    )
    warns = _post_merge_secret_scan(target)
    assert any("Bearer" in w or "post-merge secret" in w for w in warns), (
        f"expected post-merge secret warning, got: {warns}"
    )


def test_f_post_merge_scan_silent_when_clean(tmp_path):
    target = tmp_path / "CLAUDE.md"
    target.write_text("# CLAUDE.md\n\nNothing suspicious here.\n")
    from agent_transfer.bridge.ingest import _post_merge_secret_scan
    assert _post_merge_secret_scan(target) == []


def test_j_post_merge_scan_runs_on_json_merge(tmp_path):
    """J (Hunter A N4) — JSON merge path now also runs post-merge scan.

    settings.json / .claude.json are exactly where Bearer / api-key tokens
    are most likely to live via mcpServers env vars. The original post-
    merge scan was wired only into the .md and .sh branches.
    """
    import hashlib
    from datetime import datetime

    from agent_transfer.bridge.ingest import ingest
    from agent_transfer.bridge.models import (
        AssetEntry, Capability, ManifestModel,
    )

    home = tmp_path / "home"
    home.mkdir()
    # Pre-existing settings.json with a Bearer token already in it.
    (home / ".claude").mkdir()
    settings = home / ".claude" / "settings.json"
    import json as _json
    settings.write_text(_json.dumps({
        "weird": {"old": "Bearer abcdef0123456789ABCDEF0123456789"},
    }))

    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "bundle").mkdir()
    src = bundle / "bundle" / "settings.json"
    src.write_text(_json.dumps({"new": {"clean": True}}))
    sha = hashlib.sha256(src.read_bytes()).hexdigest()

    manifest = ManifestModel(
        generated_at=datetime.utcnow(),
        source_machine_hint="test",
        capability=Capability(
            name="t", description="x", intent="x",
            assets=[AssetEntry(
                path="settings.json",
                dest_path="~/.claude/settings.json",
                risk="green",
                conflict="merge",
                sha256=sha,
                mode_bits=0o644,
            )],
        ),
    )
    (bundle / "manifest.json").write_text(manifest.model_dump_json())

    r = ingest(bundle, home=home, auto_yes=True, interactive=False)
    assert any(
        "Bearer" in w or "post-merge secret" in w
        for w in r.post_merge_secret_warnings
    ), (
        f"J regression: pre-existing token in settings.json was not "
        f"caught by post-merge JSON scan. Warnings: "
        f"{r.post_merge_secret_warnings}"
    )


def test_j_post_merge_scan_runs_on_overwrite(tmp_path):
    """J (Hunter A N5) — overwrite path also re-scans post-write."""
    import hashlib
    from datetime import datetime

    from agent_transfer.bridge.ingest import ingest
    from agent_transfer.bridge.models import (
        AssetEntry, Capability, ManifestModel,
    )

    home = tmp_path / "home"
    (home / ".claude" / "skills").mkdir(parents=True)

    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "bundle").mkdir()
    src = bundle / "bundle" / "rules.md"
    # Imagine seal-time scanner missed this token.
    src.write_text("# rules\nBearer abcdef0123456789ABCDEF0123456789\n")
    sha = hashlib.sha256(src.read_bytes()).hexdigest()

    manifest = ManifestModel(
        generated_at=datetime.utcnow(),
        source_machine_hint="test",
        capability=Capability(
            name="t", description="x", intent="x",
            assets=[AssetEntry(
                path="rules.md",
                dest_path="~/.claude/skills/rules.md",
                risk="green",
                conflict="overwrite",
                sha256=sha,
                mode_bits=0o644,
            )],
        ),
    )
    (bundle / "manifest.json").write_text(manifest.model_dump_json())

    r = ingest(bundle, home=home, auto_yes=True, interactive=False)
    assert any(
        "Bearer" in w or "post-merge secret" in w
        for w in r.post_merge_secret_warnings
    ), (
        f"J regression: post-overwrite scan missed the token. "
        f"Warnings: {r.post_merge_secret_warnings}"
    )


def test_h8_merge_rejects_mismatched_names(tmp_path):
    target = tmp_path / "CLAUDE.md"
    target.write_text("# CLAUDE.md\n")
    incoming = (
        "<!-- BEGIN agentbridge:sio -->\n"
        "X\n"
        "<!-- END agentbridge:other -->\n"
    )
    with pytest.raises(_MarkdownMergeError, match="does not match"):
        _merge_markdown(target, incoming)
