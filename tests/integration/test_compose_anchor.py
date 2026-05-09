"""G4 — composer anchor narrowing (word-boundary match).

Pre-fix bug: `_anchor_pass` used `s in norm_name` substring match. The
synonym "sio" then matched filenames containing s-i-o in sequence —
session, decision, mission, regression, occasion, etc. A `compose
--capability sio` invocation would pull thousands of false-positive
files before the SIO state issues even surfaced.

Post-fix: word-boundary match on the normalized stem (which already
collapses non-alnum to spaces, so wrapping in spaces yields token equality).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_transfer.bridge.compose import compose


def _seed_skill(home: Path, slug: str, body: str = "") -> Path:
    skills = home / ".claude" / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    p = skills / f"{slug}.md"
    p.write_text(body or f"# {slug}\n\nA skill named {slug}.\n")
    return p


def test_g4_sio_does_not_match_session(tmp_path):
    """`--capability sio` must NOT pull session-* skills."""
    home = tmp_path / "home"
    _seed_skill(home, "sio-scan", "# sio-scan\nMines errors\n")
    _seed_skill(home, "session-prd-cleanup", "# session-prd-cleanup\n")
    _seed_skill(home, "session-review", "# session-review\n")
    _seed_skill(home, "decision-log", "# decision-log\n")
    _seed_skill(home, "mission-statement", "# mission-statement\n")

    cap = compose("sio", home=home)
    paths = {a.dest_path for a in cap.assets}

    assert any("sio-scan" in p for p in paths), "real sio-* skill must be in"
    assert not any("session-prd-cleanup" in p for p in paths), (
        "G4 regression: 'sio' substring-matched 'session'"
    )
    assert not any("session-review" in p for p in paths)
    assert not any("decision-log" in p for p in paths)
    assert not any("mission-statement" in p for p in paths)


def test_g4_sio_still_matches_real_sio_skills(tmp_path):
    """The narrower match must NOT drop legitimate sio-* hits."""
    home = tmp_path / "home"
    _seed_skill(home, "sio-scan")
    _seed_skill(home, "sio-suggest")
    _seed_skill(home, "sio-status")

    cap = compose("sio", home=home)
    names = {Path(a.dest_path).stem for a in cap.assets}

    assert "sio-scan" in names
    assert "sio-suggest" in names
    assert "sio-status" in names


def test_g4_compound_capability_name(tmp_path):
    """Multi-token capability name still matches each token."""
    home = tmp_path / "home"
    _seed_skill(home, "cascade-memory", "# cascade-memory\nL1.5 anchor\n")
    _seed_skill(home, "memory-bank", "# memory-bank\n")
    _seed_skill(home, "unrelated", "# unrelated\n")

    cap = compose("cascade-memory", home=home)
    names = {Path(a.dest_path).stem for a in cap.assets}

    assert "cascade-memory" in names
    # memory-bank legitimately matches the "memory" synonym (acceptable).
    assert "unrelated" not in names
