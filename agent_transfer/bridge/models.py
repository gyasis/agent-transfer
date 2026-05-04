"""Pydantic data models for AgentBridge bundles.

Source manifest schema (capabilities-not-files) plus all supporting types.
Re-exported from agent_transfer/models.py for backward compat per R5.

Constitution: R6 (no hardcoded absolute paths — caller passes paths in).
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# Risk tag for an individual asset. Drives whether user confirmation is required
# at preview / ingest time. Green = personas/tone/text-only rules. Yellow = tool
# defs, parameter types, settings.json fragments. Red = auth hooks, circuit
# breakers, state-writing hooks, anything that blocks tool calls.
RiskTag = Literal["green", "yellow", "red"]

# Conflict policy — what to do when the destination already has a file at
# the asset's destination path. Settings/json mcpServers always merge.
ConflictPolicy = Literal["skip", "merge", "overwrite", "ask"]

# Briefing section identifiers — the 7 mandatory sections of the
# "Dear Receiving Claude" briefing markdown.
BriefingSectionName = Literal[
    "identity",
    "capability_description",
    "inventory",
    "build_instructions",
    "ingest_instructions",
    "verification",
    "rollback",
]


class AssetEntry(BaseModel):
    """A single concrete file the bundle ships."""

    path: str = Field(..., description="Path inside the bundle (relative to bundle/)")
    dest_path: str = Field(
        ...,
        description="Destination path on receiving machine, with ~ expansion deferred to ingest time",
    )
    risk: RiskTag = Field(..., description="Green / Yellow / Red")
    conflict: ConflictPolicy = Field(..., description="Per-asset conflict resolution policy")
    sha256: str = Field(..., description="Hex digest of asset bytes — verified on ingest")
    mode_bits: int = Field(
        ...,
        ge=0,
        description="POSIX mode bits to restore on ingest (executable bit etc.)",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional human-readable note shown in Briefing Preview",
    )


class BriefingSection(BaseModel):
    """One section of the 'Dear Receiving Claude' briefing."""

    name: BriefingSectionName
    content_md: str = Field(..., description="Rendered Markdown content for this section")


class Capability(BaseModel):
    """A named bundle of intent + behavior, composed of one or more assets."""

    name: str = Field(..., description="User-facing capability name, e.g. 'cascade-memory'")
    description: str = Field(..., description="One-sentence what-it-does")
    intent: str = Field(..., description="Why-it-exists, in user's words where possible")
    assets: List[AssetEntry] = Field(default_factory=list)
    dependencies: List[str] = Field(
        default_factory=list,
        description="Names of OS-level binaries the destination must have (e.g. ripgrep)",
    )


class Confirmation(BaseModel):
    """One user y/n decision recorded in confirmations.log."""

    asset_path: str
    risk: RiskTag
    decided_at: datetime
    user_choice: Literal["yes", "no"]


class ManifestModel(BaseModel):
    """Top-level manifest — authoritative on the source side.

    Shipped at bundle root as `manifest.json`. Consumed by the receiving
    `agentbridge-ingest` skill alongside BRIEFING.md.
    """

    schema_version: str = Field(default="1.0.0")
    generated_at: datetime
    source_machine_hint: str = Field(
        ...,
        description="Non-identifying hint, e.g. 'linux-wsl2-claude-code-v2.x'",
    )
    capability: Capability
    briefing_sections: List[BriefingSection] = Field(default_factory=list)
    confirmations: List[Confirmation] = Field(
        default_factory=list,
        description="User Y/N decisions captured by Briefing Preview UI (FR-009, SC-007)",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "schema_version": "1.0.0",
                    "generated_at": "2026-05-04T10:00:00Z",
                    "source_machine_hint": "linux-wsl2-claude-code-v2.x",
                    "capability": {
                        "name": "cascade-memory",
                        "description": "L1.5 anchor for past-session search",
                        "intent": "Recover prior context across compactions",
                        "assets": [],
                        "dependencies": ["ripgrep"],
                    },
                    "briefing_sections": [],
                    "confirmations": [],
                }
            ]
        }
    }
