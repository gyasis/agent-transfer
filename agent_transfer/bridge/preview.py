"""Briefing Preview UI — per-asset preview with risk tags.

Source-side gate before sealing the bundle. Per FR-009 / SC-007 / FR-018:
- Show every asset with its risk tag and conflict policy.
- Prompt y/n on every Yellow and Red asset before the bundle is sealed.
- Refuse to seal on a declined Red (no partial-trust bundles).
- Write `confirmations.log` to the bundle root for audit.

Constitution: R6 (no hardcoded ~/, paths come from caller).
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from agent_transfer.bridge.models import AssetEntry, Capability, Confirmation


class RedDeclinedError(RuntimeError):
    """Raised when the user declines a Red-tier asset — bundle MUST NOT seal."""


def _ask(prompt: str) -> bool:
    """Read a y/n answer from stdin. Empty → no. Non-tty → no."""
    if not sys.stdin.isatty():
        return False
    try:
        ans = input(prompt + " [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return ans in {"y", "yes"}


def _render_asset(a: AssetEntry) -> None:
    try:
        from rich.console import Console
        from rich.panel import Panel
    except ImportError:
        print(f"\n[{a.risk}] {a.dest_path}  (conflict: {a.conflict})")
        if a.notes:
            print(f"  {a.notes}")
        return

    risk_color = {"green": "green", "yellow": "yellow", "red": "red"}[a.risk]
    body_lines = [
        f"[bold]Destination:[/bold] {a.dest_path}",
        f"[bold]Conflict policy:[/bold] {a.conflict}",
        f"[bold]Mode bits:[/bold] {oct(a.mode_bits)}",
        f"[bold]Sha256:[/bold] {a.sha256[:16]}…",
    ]
    if a.notes:
        body_lines.append(f"[bold]Notes:[/bold] {a.notes}")
    Console().print(
        Panel(
            "\n".join(body_lines),
            title=f"[{risk_color}]{a.risk.upper()}[/{risk_color}]  {a.path}",
            border_style=risk_color,
        )
    )


def preview_and_confirm(
    capability: Capability,
    bundle_root: Path,
    *,
    interactive: bool = True,
    auto_yes: bool = False,
) -> Capability:
    """Show per-asset preview; gate Yellow/Red; log confirmations.

    Args:
        capability: The trimmed Capability about to be sealed.
        bundle_root: Where to write `confirmations.log`.
        interactive: When False or stdin not a tty, behavior depends on
            auto_yes — defaults to "auto-no" except for Green which always
            passes.
        auto_yes: Skip prompts, treat all Yellow/Red as confirmed (for
            tests / CI / `--yes` flag). Still records a Confirmation entry
            per asset so the audit log is honest.

    Returns:
        New Capability whose `confirmations` list is populated and whose
        `assets` is filtered to just confirmed entries (declined Yellow
        items are dropped; declined Red raises RedDeclinedError).

    Raises:
        RedDeclinedError: User declined a Red-tier asset. The CLI catches
            this and refuses to seal the bundle (FR-018).
    """
    bundle_root.mkdir(parents=True, exist_ok=True)
    log_path = bundle_root / "confirmations.log"

    confirmations: List[Confirmation] = []
    kept: List[AssetEntry] = []

    for a in capability.assets:
        if a.risk == "green":
            kept.append(a)
            continue

        _render_asset(a)
        if auto_yes:
            decision = True
        elif not interactive or not sys.stdin.isatty():
            decision = False
        else:
            decision = _ask(f"Confirm {a.risk.upper()} asset {a.dest_path}?")

        confirmations.append(
            Confirmation(
                asset_path=a.dest_path,
                risk=a.risk,
                decided_at=datetime.now(timezone.utc),
                user_choice="yes" if decision else "no",
            )
        )

        if decision:
            kept.append(a)
        elif a.risk == "red":
            # Write what we have so far so the audit trail isn't lost.
            _write_log(log_path, confirmations)
            raise RedDeclinedError(
                f"User declined Red-tier asset {a.dest_path}. "
                "Bundle will NOT be sealed (FR-018)."
            )
        # Yellow declined → dropped silently from the bundle.

    _write_log(log_path, confirmations)
    return capability.model_copy(
        update={"assets": kept, "confirmations": confirmations}
    )


def _write_log(log_path: Path, confs: List[Confirmation]) -> None:
    lines = [
        f"{c.decided_at.isoformat()}\t{c.user_choice}\t{c.risk}\t{c.asset_path}"
        for c in confs
    ]
    log_path.write_text("\n".join(lines) + ("\n" if lines else ""))
