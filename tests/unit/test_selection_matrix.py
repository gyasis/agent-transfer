"""T025 — Unit test: 3-tier selection matrix semantics.

Default trim: CORE + COMPANIONS in, CONTEXT out. CORE non-removable.
Programmatic trim via drop_companions / add_contexts.
"""

from __future__ import annotations

from agent_transfer.bridge.compose import tier_of
from agent_transfer.bridge.models import AssetEntry, Capability
from agent_transfer.bridge.selection_matrix import present


def _asset(dest: str, tier: str, risk: str = "yellow") -> AssetEntry:
    return AssetEntry(
        path=dest.lstrip("~/"),
        dest_path=dest,
        risk=risk,  # type: ignore[arg-type]
        conflict="ask",
        sha256="a" * 64,
        mode_bits=0o644,
        notes=f"tier={tier}",
        kind="skill",
    )


def _cap(*assets: AssetEntry) -> Capability:
    return Capability(
        name="test", description="t", intent="t",
        assets=list(assets), dependencies=[],
    )


def test_default_drops_context_keeps_core_and_companions():
    cap = _cap(
        _asset("~/a", "CORE"),
        _asset("~/b", "COMPANIONS"),
        _asset("~/c", "CONTEXT"),
    )
    out = present(cap, interactive=False)
    paths = {a.dest_path for a in out.assets}
    assert paths == {"~/a", "~/b"}


def test_drop_companion_removes_it():
    cap = _cap(
        _asset("~/a", "CORE"),
        _asset("~/b", "COMPANIONS"),
        _asset("~/c", "COMPANIONS"),
    )
    out = present(cap, interactive=False, drop_companions=["~/b"])
    paths = {a.dest_path for a in out.assets}
    assert paths == {"~/a", "~/c"}


def test_add_context_promotes_it():
    cap = _cap(
        _asset("~/a", "CORE"),
        _asset("~/b", "CONTEXT"),
    )
    out = present(cap, interactive=False, add_contexts=["~/b"])
    paths = {a.dest_path for a in out.assets}
    assert paths == {"~/a", "~/b"}


def test_drop_does_not_remove_core():
    cap = _cap(_asset("~/a", "CORE"), _asset("~/b", "COMPANIONS"))
    # Even if user "drops" a CORE path via the wrong API, default_trim keeps it.
    out = present(cap, interactive=False, drop_companions=["~/a"])
    paths = {a.dest_path for a in out.assets}
    # ~/a is CORE so it stays; ~/b stays as COMPANIONS not in drop list.
    assert "~/a" in paths


def test_tier_of_default_context_when_no_marker():
    a = AssetEntry(
        path="x", dest_path="~/x", risk="green", conflict="skip",
        sha256="b" * 64, mode_bits=0o644, notes=None, kind="skill",
    )
    assert tier_of(a) == "CONTEXT"


def test_tier_of_reads_notes_marker():
    a = AssetEntry(
        path="x", dest_path="~/x", risk="green", conflict="skip",
        sha256="b" * 64, mode_bits=0o644, notes="tier=CORE extra", kind="skill",
    )
    assert tier_of(a) == "CORE"
