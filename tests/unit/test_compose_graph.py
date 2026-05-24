"""T024 — Unit test: capability dependency-graph walk.

Builds a fixture HOME under tmp_path, runs compose() against a known
capability name, and asserts the expected CORE/COMPANIONS/CONTEXT
partitioning.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from agent_transfer.bridge.compose import compose, tier_of


def _fixture_home(tmp_path: Path) -> Path:
    """Build a minimal ~/.claude/ tree mirroring cascade-memory structure."""
    home = tmp_path / "fixture-home"
    claude = home / ".claude"
    skills = claude / "skills"
    rules_domains = claude / "rules" / "domains"
    rules_tools = claude / "rules" / "tools"
    hooks_um = claude / "hooks" / "unified-memory"
    bin_dir = home / "bin"

    for d in (skills, rules_domains, rules_tools, hooks_um, bin_dir):
        d.mkdir(parents=True)

    # CORE-anchored skill: name contains the capability term
    (skills / "memory-search.md").write_text(
        "---\nname: memory-search\ndescription: Search past sessions via cascade memory.\n---\n# memory-search\n"
        "Anchors L1.5 of the cascade-memory stack. Calls `~/bin/session-search` for the lookup.\n"
    )

    # COMPANIONS — bin script referenced by the CORE skill (strict ref)
    ss = bin_dir / "session-search"
    ss.write_text("#!/usr/bin/env bash\ngrep \"$@\" /tmp/no-such-file 2>/dev/null || true\n")
    ss.chmod(ss.stat().st_mode | stat.S_IXUSR)

    # COMPANIONS — rule referenced by CORE skill via /done-before
    (rules_domains / "memory.md").write_text(
        "# memory\nWhen user mentions cascade-memory protocol...\n"
    )

    # 1-hop skill: links to memory-search via /memory-search (slug ref)
    (skills / "done-before.md").write_text(
        "---\nname: done-before\ndescription: Quickly recall prior work.\n---\n# done-before\n"
        "Calls /memory-search for cascade history.\n"
    )

    # CONTEXT — unrelated bin via lenient match (name appears in unrelated skill body)
    other = bin_dir / "session-search-helper"
    other.write_text("#!/usr/bin/env bash\necho hi\n")
    other.chmod(other.stat().st_mode | stat.S_IXUSR)
    (skills / "specstory-search.md").write_text(
        "---\nname: specstory-search\ndescription: Search SpecStory archives.\n---\n# specstory-search\n"
        "Use session-search-helper for archive queries.\n"
    )

    return home


def test_compose_finds_core_anchor(tmp_path):
    home = _fixture_home(tmp_path)
    cap = compose("cascade-memory", home=home)
    assert cap.name == "cascade-memory"
    cores = [a for a in cap.assets if tier_of(a) == "CORE"]
    assert any("memory-search" in a.dest_path for a in cores), (
        f"memory-search.md must be CORE; got tiers={[(a.dest_path, tier_of(a)) for a in cap.assets]}"
    )


def test_compose_includes_strict_bin_companion(tmp_path):
    home = _fixture_home(tmp_path)
    cap = compose("cascade-memory", home=home)
    bin_assets = [a for a in cap.assets if "/bin/session-search" in a.dest_path and "helper" not in a.dest_path]
    assert bin_assets, "session-search bin must be included via strict ref"
    assert tier_of(bin_assets[0]) == "COMPANIONS"


def test_compose_raises_on_unmatched_name(tmp_path):
    home = _fixture_home(tmp_path)
    with pytest.raises(ValueError, match="No assets matched"):
        compose("nonexistent-flim-flam", home=home)


def test_compose_assets_have_sha_and_mode(tmp_path):
    home = _fixture_home(tmp_path)
    cap = compose("cascade-memory", home=home)
    for a in cap.assets:
        assert len(a.sha256) == 64, f"Bad sha256 on {a.dest_path}: {a.sha256!r}"
        assert a.mode_bits >= 0


def _fixture_home_with_hook_dir(tmp_path: Path) -> Path:
    """Fixture where the critical hook lives in a dir whose name matches the
    capability stem, but the hook BODY does NOT name-drop any CORE seed.

    Origin 2026-05-24: regression test for the hook-walker gap that silently
    omitted ~/.claude/hooks/unified-memory/pre-compact.sh from
    `ab compose --capability memory` because the bash body doesn't say
    "memory.md". The fix added directory-name matching to _expand_one_hop.
    """
    home = tmp_path / "fixture-home-hookdir"
    claude = home / ".claude"
    skills = claude / "skills"
    rules_domains = claude / "rules" / "domains"
    hooks_um = claude / "hooks" / "unified-memory"
    hooks_unrelated = claude / "hooks" / "playwright-guard"
    bin_dir = home / "bin"

    for d in (skills, rules_domains, hooks_um, hooks_unrelated, bin_dir):
        d.mkdir(parents=True)

    # CORE anchor — matches file-stem on "memory"
    (skills / "memory-search.md").write_text(
        "---\nname: memory-search\ndescription: Cascade search.\n---\n# memory-search\n"
        "Anchors the cascade-memory stack.\n"
    )
    (rules_domains / "memory.md").write_text(
        "# memory\nRouting rules for cascade-memory.\n"
    )

    # CRITICAL hook in matching dir, body does NOT mention memory.md / memory-search.md
    (hooks_um / "pre-compact.sh").write_text(
        "#!/usr/bin/env bash\n"
        "# Backup transcript before /compact\n"
        "set -e\n"
        "BACKUP=~/.claude/backups/$(date +%Y%m%d)\n"
        "mkdir -p \"$BACKUP\"\n"
        "cp \"$1\" \"$BACKUP/\"\n"
    )
    (hooks_um / "extract-discoveries.py").write_text(
        "#!/usr/bin/env python3\n"
        "# Extract errors->fixes from session transcripts\n"
        "import json, sys\n"
        "print(json.dumps({'ok': True}))\n"
    )

    # UNRELATED hook in non-matching dir, also no body mention
    (hooks_unrelated / "playwright-guard.sh").write_text(
        "#!/usr/bin/env bash\n# Block expensive Playwright calls\nexit 0\n"
    )

    return home


def test_compose_pulls_hook_by_dirname_match(tmp_path):
    """REGRESSION (2026-05-24): hook in dir whose name contains the capability
    stem MUST be included even when the body has no CORE-seed mentions."""
    home = _fixture_home_with_hook_dir(tmp_path)
    cap = compose("memory", home=home)
    hook_paths = [a.dest_path for a in cap.assets if "/hooks/" in a.dest_path]
    assert any("unified-memory/pre-compact.sh" in p for p in hook_paths), (
        f"unified-memory/pre-compact.sh must be included via dir-name match; "
        f"got hooks={hook_paths}"
    )
    assert any("unified-memory/extract-discoveries.py" in p for p in hook_paths), (
        f"unified-memory/extract-discoveries.py must be included via dir-name match; "
        f"got hooks={hook_paths}"
    )


def test_compose_skips_unrelated_hooks(tmp_path):
    """Companion to the dir-match test: unrelated hook dirs MUST NOT be pulled."""
    home = _fixture_home_with_hook_dir(tmp_path)
    cap = compose("memory", home=home)
    hook_paths = [a.dest_path for a in cap.assets if "/hooks/" in a.dest_path]
    assert not any("playwright-guard" in p for p in hook_paths), (
        f"playwright-guard hook must NOT be pulled into a `memory` capability bundle; "
        f"got hooks={hook_paths}"
    )
