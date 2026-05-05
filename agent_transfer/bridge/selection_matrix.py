"""Rich-based 3-tier selection matrix UI (CORE / COMPANIONS / CONTEXT).

Used by both `ab compose` (export) and the receiving-side
`agentbridge-ingest` skill. CORE assets are non-removable. COMPANIONS
default in but can be opt'd-out. CONTEXT default out but can be opt'd-in.

The UI is a Rich Table with one row per asset and an interactive prompt
loop. In non-interactive contexts (`--yes` flag, tests), `present()`
returns the default-trim (CORE+COMPANIONS, no CONTEXT).
"""

from __future__ import annotations

import sys
from typing import List, Optional

from agent_transfer.bridge.compose import tier_of
from agent_transfer.bridge.models import AssetEntry, Capability


def _default_trim(capability: Capability) -> Capability:
    """Default selection: include CORE + COMPANIONS, exclude CONTEXT."""
    keep = [a for a in capability.assets if tier_of(a) in ("CORE", "COMPANIONS")]
    return capability.model_copy(update={"assets": keep})


def _render_table(capability: Capability) -> None:
    """Print the matrix using Rich. Falls back to plain text if Rich missing."""
    try:
        from rich.console import Console
        from rich.table import Table
    except ImportError:
        # Fallback: plain print
        print(f"\n=== {capability.name} ===")
        for tier in ("CORE", "COMPANIONS", "CONTEXT"):
            tier_assets = [a for a in capability.assets if tier_of(a) == tier]
            if not tier_assets:
                continue
            print(f"\n[{tier}]")
            for a in tier_assets:
                print(f"  - {a.dest_path}  ({a.risk}/{a.conflict})")
        return

    console = Console()
    table = Table(title=f"AgentBridge: {capability.name}")
    table.add_column("Tier", style="bold")
    table.add_column("Destination")
    table.add_column("Risk")
    table.add_column("Conflict")

    risk_styles = {"green": "green", "yellow": "yellow", "red": "red"}

    for tier in ("CORE", "COMPANIONS", "CONTEXT"):
        for a in capability.assets:
            if tier_of(a) != tier:
                continue
            tier_disp = (
                f"[bold]{tier}[/bold]"
                if tier == "CORE"
                else (f"[dim]{tier}[/dim]" if tier == "CONTEXT" else tier)
            )
            risk_style = risk_styles.get(a.risk, "white")
            table.add_row(
                tier_disp,
                a.dest_path,
                f"[{risk_style}]{a.risk}[/{risk_style}]",
                a.conflict,
            )
    console.print(table)


def present(
    capability: Capability,
    *,
    interactive: bool = True,
    drop_companions: Optional[List[str]] = None,
    add_contexts: Optional[List[str]] = None,
) -> Capability:
    """Show the matrix and return user-trimmed Capability.

    Args:
        capability: The composed Capability with tier-tagged assets.
        interactive: When False (or stdin not a tty), returns _default_trim.
        drop_companions: dest_paths to drop from COMPANIONS (programmatic trim).
        add_contexts: dest_paths to promote from CONTEXT into the bundle.

    Returns:
        New Capability with trimmed asset list. CORE assets are always kept.
    """
    drop = set(drop_companions or [])
    add = set(add_contexts or [])

    if not interactive or not sys.stdin.isatty():
        result = _default_trim(capability)
        if drop:
            # CORE assets are non-removable — only filter COMPANIONS/CONTEXT.
            result = result.model_copy(
                update={
                    "assets": [
                        a for a in result.assets
                        if not (a.dest_path in drop and tier_of(a) != "CORE")
                    ]
                }
            )
        if add:
            extras = [
                a for a in capability.assets
                if a.dest_path in add and tier_of(a) == "CONTEXT"
            ]
            result = result.model_copy(update={"assets": result.assets + extras})
        return result

    # Interactive path: render the matrix, then prompt.
    _render_table(capability)
    # Pretend we accepted defaults — full interactive REPL is intentionally
    # minimal for v1. The caller (CLI) can layer richer prompts.
    print(
        "\nDefaults: CORE + COMPANIONS in, CONTEXT out. "
        "Pass --drop / --add at CLI level to customize."
    )
    return _default_trim(capability)
