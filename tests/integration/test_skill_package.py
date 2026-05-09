"""G2 — skill packages (directory-shaped skills) bundle as a tree.

Pre-fix bug: `_walk_dir` filtered to .md files only. A skill structured
as a directory (e.g. `~/.claude/skills/sio-scan/SKILL.md` plus
`scripts/foo.sh`, `requirements.txt`, `assets/x.css`) had everything
except SKILL.md silently dropped.

Post-fix: when an anchored SKILL.md lives in a skill-package directory,
the entire package subtree is added as CORE candidates.
"""

from __future__ import annotations

from pathlib import Path

from agent_transfer.bridge.compose import compose


def _seed_skill_package(home: Path, slug: str) -> Path:
    pkg = home / ".claude" / "skills" / slug
    pkg.mkdir(parents=True)
    (pkg / "SKILL.md").write_text(
        f"---\nname: {slug}\n---\n# {slug} skill\n"
    )
    (pkg / "scripts").mkdir()
    (pkg / "scripts" / "run.sh").write_text("#!/bin/sh\necho hi\n")
    (pkg / "scripts" / "helper.py").write_text("print('helper')\n")
    (pkg / "requirements.txt").write_text("requests==2.31.0\n")
    (pkg / "assets").mkdir()
    (pkg / "assets" / "style.css").write_text("body{}\n")
    return pkg


def test_g2_skill_package_pulls_full_subtree(tmp_path):
    home = tmp_path / "home"
    _seed_skill_package(home, "sio-scan")

    cap = compose("sio-scan", home=home)
    rels = sorted({a.dest_path for a in cap.assets})

    # Every file in the package must be present.
    expected = {
        "~/.claude/skills/sio-scan/SKILL.md",
        "~/.claude/skills/sio-scan/scripts/run.sh",
        "~/.claude/skills/sio-scan/scripts/helper.py",
        "~/.claude/skills/sio-scan/requirements.txt",
        "~/.claude/skills/sio-scan/assets/style.css",
    }
    actual_relevant = {r for r in rels if "/skills/sio-scan/" in r}
    assert expected <= actual_relevant, (
        f"G2 regression: skill package siblings dropped. "
        f"Expected: {expected - actual_relevant}"
    )


def test_g2_skill_package_anchor_by_dir_slug_when_skill_md_lacks_match(tmp_path):
    """SKILL.md generic frontmatter; package dir name is the anchor."""
    home = tmp_path / "home"
    pkg = home / ".claude" / "skills" / "sio-scan"
    pkg.mkdir(parents=True)
    # SKILL.md says nothing about "sio-scan" by token — only generic text.
    (pkg / "SKILL.md").write_text("# Generic skill body\n")
    (pkg / "scripts").mkdir()
    (pkg / "scripts" / "run.sh").write_text("#!/bin/sh\n")

    cap = compose("sio-scan", home=home)
    rels = {a.dest_path for a in cap.assets}
    assert "~/.claude/skills/sio-scan/SKILL.md" in rels
    assert "~/.claude/skills/sio-scan/scripts/run.sh" in rels


def test_g2_does_not_pull_unrelated_skill_package(tmp_path):
    home = tmp_path / "home"
    _seed_skill_package(home, "sio-scan")
    _seed_skill_package(home, "kami")  # unrelated package

    cap = compose("sio-scan", home=home)
    rels = {a.dest_path for a in cap.assets}

    assert any("/sio-scan/" in r for r in rels)
    assert not any("/kami/" in r for r in rels), (
        "Unrelated skill package was pulled in"
    )


def test_g2_flat_skill_md_still_works(tmp_path):
    """Flat .md skills (no package dir) keep working."""
    home = tmp_path / "home"
    skills = home / ".claude" / "skills"
    skills.mkdir(parents=True)
    (skills / "sio-rule-audit.md").write_text("# sio-rule-audit\n")

    cap = compose("sio-rule-audit", home=home)
    rels = {a.dest_path for a in cap.assets}
    assert "~/.claude/skills/sio-rule-audit.md" in rels
