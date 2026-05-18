"""Pydantic data models for AgentBridge bundles.

Source manifest schema (capabilities-not-files) plus all supporting types.
Re-exported from agent_transfer/models.py for backward compat per R5.

Constitution: R6 (no hardcoded absolute paths — caller passes paths in).
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

# v1.1 bundle schema (additive: adds AssetEntry.kind + AssetEntry.behavior_md).
# Receivers that only understand 1.0.x still parse 1.1.x bundles (pydantic
# ignores unknown fields by default in BaseModel); 1.0.x bundles are accepted
# by 1.1 ingest with a DeprecationWarning (see bridge/ingest.py).
SCHEMA_VERSION = "1.1.0"
MIN_SUPPORTED_SCHEMA = "1.0.0"

# Cross-harness asset kind. v1.1 makes this required on AssetEntry so
# non-Claude harnesses (OpenClaw / ZeroClaw / PromptChain) can map an asset
# onto their own primitive — instead of guessing from dest_path. "other" is
# explicitly refused at seal time; the composer must classify every shipped
# asset into one of the five concrete categories.
AssetKind = Literal["skill", "rule", "hook", "bin", "capability", "other"]

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
    # v1.1 — cross-harness risk mapping appendix
    "risk_mapping",
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
    kind: AssetKind = Field(
        ...,
        description=(
            "v1.1 — concrete asset category for cross-harness mapping. One of "
            "'skill' | 'rule' | 'hook' | 'bin' | 'capability'. 'other' is "
            "reserved as a parser-side sentinel and is REJECTED at seal time."
        ),
    )
    behavior_md: Optional[str] = Field(
        default=None,
        description=(
            "v1.1 — short behavioral hint (~200 chars) extracted from the "
            "asset source at compose time. Helps non-Claude receivers and "
            "human readers see what each asset does without opening the file."
        ),
    )

    @model_validator(mode="after")
    def _refuse_kind_other(self) -> "AssetEntry":
        """Refuse kind='other' at seal time — composer must classify."""
        if self.kind == "other":
            raise ValueError(
                f"AssetEntry.kind='other' is not permitted at seal time "
                f"(dest_path={self.dest_path!r}). Classify the asset as "
                "one of: skill, rule, hook, bin, capability."
            )
        return self


class BriefingSection(BaseModel):
    """One section of the 'Dear Receiving Claude' briefing."""

    name: BriefingSectionName
    content_md: str = Field(..., description="Rendered Markdown content for this section")


class RegistrationRef(BaseModel):
    """C (Hunter B G12 adjacent) — provenance of a registry-composed bundle.

    When a capability is composed from `~/.claude/capabilities/<name>.yaml`
    (rather than from discovery), the registry path + content sha256 are
    stamped here. Receivers can verify the bundle's origin and replay the
    same registration semantically.
    """

    registry_path: str = Field(
        ...,
        description="Path to the registry YAML on the source machine, with ~/ where applicable",
    )
    yaml_sha256: str = Field(
        ...,
        description="Hex sha256 of the registry YAML at compose time",
    )


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
    smoke_commands: List[str] = Field(
        default_factory=list,
        description=(
            "G6 — shell commands the destination runs post-install to verify the "
            "capability is actually wired up. Each must exit 0 within "
            "10 seconds (executed under sh -c with destination HOME). Catches "
            "partial installs that file-presence smoke would miss "
            "(e.g. skills installed but the binary they call is absent, "
            "or hook section never reached because of an unrelated parse error)."
        ),
    )
    registered_via: Optional[RegistrationRef] = Field(
        default=None,
        description=(
            "C (B G12 adjacent) — when set, this capability was composed "
            "from a registry YAML rather than discovery. Path + sha lets "
            "the receiver verify provenance and tell registry-composed "
            "bundles from discovery-composed ones (otherwise they'd be "
            "byte-indistinguishable)."
        ),
    )

    @model_validator(mode="after")
    def _no_duplicate_dest_paths(self) -> "Capability":
        """R12 H#9 fix — refuse duplicate dest_path values within one Capability.

        Two AssetEntry rows pointing at the same destination would silently
        either skip the second install (conflict=skip) or clobber the first
        (conflict=overwrite) with no warning. The duplicate is almost always
        a composer bug; surface it loudly at construction time.

        FR-005 (v1.1 mac-compat) — compare paths case-INSENSITIVELY. macOS
        APFS is case-preserving but case-insensitive by default; two
        AssetEntry rows differing only in case both write to the same
        underlying file on Mac, producing silent data loss. The case-fold
        check costs nothing on Linux ext4 (where the paths really are
        distinct files) and prevents the silent failure on Mac.
        """
        seen: dict[str, int] = {}
        case_seen: dict[str, int] = {}
        for i, a in enumerate(self.assets):
            if a.dest_path in seen:
                raise ValueError(
                    f"duplicate dest_path {a.dest_path!r} (assets[{seen[a.dest_path]}] "
                    f"and assets[{i}]); each capability may only land one asset per "
                    "destination path"
                )
            folded = a.dest_path.casefold()
            if folded in case_seen and case_seen[folded] != i:
                # Distinct strings, same case-folded form — Mac APFS hazard.
                first_idx = case_seen[folded]
                raise ValueError(
                    f"duplicate dest_path (case-insensitive): assets[{first_idx}] "
                    f"= {self.assets[first_idx].dest_path!r} and assets[{i}] = "
                    f"{a.dest_path!r}. These resolve to the same file on macOS "
                    "APFS (case-preserving, case-insensitive by default); rename "
                    "one before bundling to avoid silent overwrite."
                )
            seen[a.dest_path] = i
            case_seen[folded] = i
        return self


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

    schema_version: str = Field(default=SCHEMA_VERSION)
    generated_at: datetime
    source_machine_hint: str = Field(
        ...,
        description="Non-identifying hint, e.g. 'linux-wsl2-claude-code-v2.x'",
    )
    source_machine_home: Optional[str] = Field(
        default=None,
        description=(
            "FR-002 (v1.1 mac-compat) — absolute path of `Path.home()` on "
            "the source machine at seal time (e.g. '/home/user' on Linux, "
            "'/Users/user' on macOS). Separate from any per-asset `home` "
            "fields so the receiver can re-stamp paths into ITS own home "
            "without losing provenance. Optional for backward compat: "
            "v1.0 bundles do not carry this and ingest falls back to the "
            "old behavior (same-OS receiver only)."
        ),
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
