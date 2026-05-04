"""Destination-side ingestion — read briefing, walk inventory, install per policy.

Implements per-asset conflict resolution (skip / merge / overwrite / ask)
and idempotent merges for ~/.claude.json + settings.json. Implementation
lands in T033 (Wave 5).
"""

from __future__ import annotations

from pathlib import Path


def ingest(bundle_path: Path) -> None:
    """Read BRIEFING.md, validate manifest, prompt Yellow/Red, install. T033."""
    raise NotImplementedError("ingest() lands in T033 (Wave 5)")
