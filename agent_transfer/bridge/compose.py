"""Capability composition — `ab compose --capability <name>`.

Implementation lands in T026 (Wave 3). This stub exists so tests and the
CLI wiring (T031) can import it without ImportError during scaffolding.
"""

from __future__ import annotations

from agent_transfer.bridge.models import Capability


def compose(capability_name: str) -> Capability:
    """Walk dependency graph in ~/.claude/ to propose a capability bundle.

    Implemented in T026 (Wave 3). See specs/003-agentbridge-mvp/plan.md
    Phase 0 §1 for the deterministic graph heuristics.
    """
    raise NotImplementedError("compose() lands in T026 (Wave 3)")
