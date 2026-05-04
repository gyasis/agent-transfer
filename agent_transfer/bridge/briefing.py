"""Render the 'Dear Receiving Claude' briefing markdown.

Implementation lands in T028 (Wave 3). Uses the contract template at
specs/003-agentbridge-mvp/contracts/briefing.template.md.
"""

from __future__ import annotations

from agent_transfer.bridge.models import ManifestModel


def render(manifest: ManifestModel) -> str:
    """Render BRIEFING.md from a manifest. Implemented in T028."""
    raise NotImplementedError("render() lands in T028 (Wave 3)")
