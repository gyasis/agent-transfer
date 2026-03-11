"""Preflight transfer readiness validation.

Public API:
    collect_inventory() — Scan agents/skills/hooks/configs and build dependency manifest
    run_preflight_checks() — Validate target environment against manifest
    write_manifest() / read_manifest() / read_manifest_from_archive() — Manifest I/O
    display_readiness_report() / report_to_json() — Report output
"""

from pathlib import Path
from typing import List, Optional

from agent_transfer.utils.preflight.manifest import (
    TransferManifest,
    read_manifest,
    read_manifest_from_archive,
    write_manifest,
)
from agent_transfer.utils.preflight.collector import collect_inventory

__all__ = [
    "collect_inventory",
    "write_manifest",
    "read_manifest",
    "read_manifest_from_archive",
    "TransferManifest",
]
