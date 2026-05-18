"""Spec-006 — `--anchor-mode` selector for `_anchor_pass`.

Tests the three explicit modes plus the smart-fallback path from "name"
to "both" when name finds nothing.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from agent_transfer.bridge.compose import compose


def _seed_skill(home: Path, slug: str, body: str = "") -> Path:
    skills = home / ".claude" / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    p = skills / f"{slug}.md"
    p.write_text(body or f"# {slug}\n\nA skill.\n")
    return p


def _seed_bin(home: Path, name: str) -> Path:
    bd = home / "bin"
    bd.mkdir(parents=True, exist_ok=True)
    p = bd / name
    # Realistic shape: shebang + leading comment block so the
    # vacuous-description gate (v1.1) has a fallback to extract.
    p.write_text(
        f"#!/usr/bin/env bash\n# {name} — a tool for the {name} workflow.\necho hi\n"
    )
    p.chmod(p.stat().st_mode | stat.S_IXUSR)
    return p


def test_anchor_mode_name_skips_body_matches(tmp_path):
    """name mode must NOT match files that only reference the capability in body."""
    home = tmp_path / "home"
    _seed_skill(home, "session-search", "# session-search\nThe CLI tool\n")
    # downstream consumer — mentions session-search in body but unrelated stem
    _seed_skill(
        home,
        "memory-search",
        "# memory-search\nUses session-search under the hood.\n",
    )

    cap = compose("session-search", home=home, anchor_mode="name")
    cores = {
        Path(a.dest_path).stem
        for a in cap.assets
        if "tier=CORE" in (a.notes or "")
    }
    assert "session-search" in cores
    assert "memory-search" not in cores, (
        "name mode must not promote body-mention consumers to CORE"
    )


def test_anchor_mode_body_matches_body_only(tmp_path):
    """body mode picks up consumers whose body mentions the capability,
    even when no stem matches."""
    home = tmp_path / "home"
    _seed_skill(
        home,
        "memory-search",
        "# memory-search\nThis skill drives the session-search pipeline.\n",
    )

    cap = compose("session-search", home=home, anchor_mode="body")
    cores = {Path(a.dest_path).stem for a in cap.assets}
    assert "memory-search" in cores


def test_anchor_mode_both_is_legacy_or_match(tmp_path):
    """both mode matches either stem or body — the pre-spec-006 default."""
    home = tmp_path / "home"
    _seed_skill(home, "session-search", "# session-search\n")
    _seed_skill(
        home,
        "memory-search",
        "# memory-search\nDelegates to session-search.\n",
    )
    _seed_skill(home, "unrelated", "# unrelated\nNothing here.\n")

    cap = compose("session-search", home=home, anchor_mode="both")
    cores = {Path(a.dest_path).stem for a in cap.assets}
    assert "session-search" in cores
    assert "memory-search" in cores
    assert "unrelated" not in cores


def test_anchor_mode_name_smart_fallback_to_both(tmp_path, capsys):
    """When name finds nothing, compose falls back to both and emits a WARN."""
    home = tmp_path / "home"
    # No stem matches "cascade-memory"; only a body mention.
    _seed_skill(
        home,
        "memory-recall",
        "# memory-recall\nImplements cascade-memory protocol.\n",
    )

    cap = compose("cascade-memory", home=home)  # default anchor_mode="name"
    cores = {Path(a.dest_path).stem for a in cap.assets}
    assert "memory-recall" in cores, "smart fallback must widen to body"

    captured = capsys.readouterr()
    assert "anchor-mode=name found no concrete artifact" in captured.err
    assert "cascade-memory" in captured.err


def test_anchor_mode_name_finds_bin_anchor(tmp_path):
    """Capabilities anchored on a ~/bin/ CLI tool resolve under name mode."""
    home = tmp_path / "home"
    _seed_bin(home, "session-search")
    # Patch DEFAULT_BIN_DIRS by relying on compose's home-rewrite — it
    # rewrites paths under Path.home() to `home`, so a real-home `~/bin`
    # entry maps to `<home>/bin`. We seeded that path above.

    cap = compose("session-search", home=home, anchor_mode="name")
    paths = {a.dest_path for a in cap.assets}
    assert any("session-search" in p for p in paths)


def test_anchor_mode_invalid_raises(tmp_path):
    home = tmp_path / "home"
    _seed_skill(home, "session-search")
    with pytest.raises(ValueError, match="anchor_mode must be"):
        compose("session-search", home=home, anchor_mode="bogus")
