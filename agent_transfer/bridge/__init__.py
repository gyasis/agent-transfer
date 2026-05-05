"""AgentBridge — capability-level Claude Code → Claude Code transfer.

New subpackage introduced in feature 003-agentbridge-mvp. Wraps existing
agent_transfer/utils/* modules per constitution R4 (wrap, don't rewrite).
"""

from agent_transfer.bridge.models import (
    AssetEntry,
    BriefingSection,
    Capability,
    Confirmation,
    ConflictPolicy,
    ManifestModel,
    RiskTag,
)

__all__ = [
    "AssetEntry",
    "BriefingSection",
    "Capability",
    "Confirmation",
    "ConflictPolicy",
    "ManifestModel",
    "RiskTag",
]
