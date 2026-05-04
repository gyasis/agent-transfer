"""Briefing Preview UI — per-asset preview with risk tags.

Enforces y/n confirmation on every Yellow and Red asset before sealing.
Refuses to seal on declined Red. Writes confirmations.log. Implementation
lands in T029 (Wave 4).
"""

from __future__ import annotations

from pathlib import Path

from agent_transfer.bridge.models import Capability


def preview_and_confirm(capability: Capability, bundle_root: Path) -> Capability:
    """Show per-asset preview, gate Yellow/Red, log confirmations. T029."""
    raise NotImplementedError("preview_and_confirm() lands in T029 (Wave 4)")
