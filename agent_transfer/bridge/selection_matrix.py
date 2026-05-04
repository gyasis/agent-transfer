"""Rich-based 3-tier selection matrix UI (CORE / COMPANIONS / CONTEXT).

Implementation lands in T027 (Wave 3). Used by both `ab compose` (export)
and the receiving-side `agentbridge-ingest` skill.
"""

from __future__ import annotations

from agent_transfer.bridge.models import Capability


def present(capability: Capability) -> Capability:
    """Show 3-tier matrix; return user-trimmed capability. Implemented in T027."""
    raise NotImplementedError("present() lands in T027 (Wave 3)")
