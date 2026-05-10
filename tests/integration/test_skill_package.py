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


# -- A (F1) exclusions ------------------------------------------------------


def test_a_skill_package_excludes_dot_git_dot_venv_node_modules(tmp_path):
    home = tmp_path / "home"
    pkg = home / ".claude" / "skills" / "planning"
    pkg.mkdir(parents=True)
    (pkg / "SKILL.md").write_text("# planning\n")
    (pkg / "real_script.sh").write_text("#!/bin/sh\n")

    # Junk that should be excluded.
    (pkg / ".git").mkdir()
    (pkg / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (pkg / ".venv" / "bin").mkdir(parents=True)
    (pkg / ".venv" / "bin" / "python").write_text("fake")
    (pkg / "node_modules" / "junk").mkdir(parents=True)
    (pkg / "node_modules" / "junk" / "x.js").write_text("// junk\n")
    (pkg / "__pycache__").mkdir()
    (pkg / "__pycache__" / "x.cpython-313.pyc").write_text("bytecode")

    cap = compose("planning", home=home)
    rels = {a.dest_path for a in cap.assets}

    assert "~/.claude/skills/planning/real_script.sh" in rels
    assert not any(".git" in r for r in rels), f"junk in: {rels}"
    assert not any(".venv" in r for r in rels)
    assert not any("node_modules" in r for r in rels)
    assert not any("__pycache__" in r for r in rels)


def test_a_skill_package_excludes_dot_env_but_not_env_example(tmp_path):
    """Secrets file dropped; .env.example kept."""
    home = tmp_path / "home"
    pkg = home / ".claude" / "skills" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "SKILL.md").write_text("# p\n")
    (pkg / ".env").write_text("SECRET=hunter2\n")
    (pkg / ".env.example").write_text("SECRET=\n")

    cap = compose("pkg", home=home)
    rels = {a.dest_path for a in cap.assets}
    assert not any(r.endswith("/.env") for r in rels)
    assert "~/.claude/skills/pkg/.env.example" in rels


def test_a_skill_package_excludes_pyc_files(tmp_path):
    home = tmp_path / "home"
    pkg = home / ".claude" / "skills" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "SKILL.md").write_text("# p\n")
    (pkg / "real.py").write_text("# python source\n")
    (pkg / "stale.pyc").write_text("bytecode")

    cap = compose("pkg", home=home)
    rels = {a.dest_path for a in cap.assets}
    assert "~/.claude/skills/pkg/real.py" in rels
    assert not any(r.endswith(".pyc") for r in rels)


def test_g_companion_skill_package_pulls_full_subtree(tmp_path):
    """G — 1-hop slug-referenced skill packages also expand to siblings.

    Pre-fix: anchor pass expanded packages, but 1-hop BFS hit a SKILL.md
    by slug-lookup and dropped scripts/ etc. Post-fix: companion package
    expansion matches anchor expansion.
    """
    home = tmp_path / "home"
    skills = home / ".claude" / "skills"
    skills.mkdir(parents=True)

    # Anchor: a flat .md skill that references /companion-pkg.
    (skills / "anchor-skill.md").write_text(
        "# anchor-skill\n\nUses /companion-pkg for the heavy lifting.\n"
    )
    # Companion: a package, NOT a flat .md.
    pkg = skills / "companion-pkg"
    pkg.mkdir()
    (pkg / "SKILL.md").write_text("# companion-pkg\n")
    (pkg / "scripts").mkdir()
    (pkg / "scripts" / "do_thing.sh").write_text("#!/bin/sh\n")

    cap = compose("anchor-skill", home=home)
    rels = {a.dest_path for a in cap.assets}

    # Anchor present, companion's SKILL.md present (1-hop), AND its
    # script siblings present (G — package expansion symmetry).
    assert "~/.claude/skills/anchor-skill.md" in rels
    assert "~/.claude/skills/companion-pkg/SKILL.md" in rels
    assert "~/.claude/skills/companion-pkg/scripts/do_thing.sh" in rels


def test_a_skill_package_excludes_oversize_file(tmp_path):
    """Files >5 MiB are skipped to keep bundle size sane."""
    from agent_transfer.bridge import compose as compose_mod

    home = tmp_path / "home"
    pkg = home / ".claude" / "skills" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "SKILL.md").write_text("# p\n")
    (pkg / "small.txt").write_text("small\n")
    huge = pkg / "huge.bin"
    # 6 MiB (above default 5 MiB cap).
    huge.write_bytes(b"x" * (6 * 1024 * 1024))

    cap = compose("pkg", home=home)
    rels = {a.dest_path for a in cap.assets}
    assert "~/.claude/skills/pkg/small.txt" in rels
    assert "~/.claude/skills/pkg/huge.bin" not in rels
