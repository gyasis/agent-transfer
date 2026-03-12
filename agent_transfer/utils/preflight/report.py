"""Preflight readiness report display and serialization.

Rich terminal report for human consumption and JSON output for --json flag.
"""

import json
from typing import Any, Dict, List

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from agent_transfer.utils.preflight.checker import CheckResult, ReadinessReport


# Status color mapping
_STATUS_COLORS = {
    "GREEN": "green",
    "YELLOW": "yellow",
    "RED": "red",
}

_STATUS_ICONS = {
    "GREEN": "[green]✓[/green]",
    "YELLOW": "[yellow]⚠[/yellow]",
    "RED": "[red]✗[/red]",
}

_OVERALL_COLORS = {
    "PASS": "green",
    "WARN": "yellow",
    "FAIL": "red",
}

# Human-readable category names
_CATEGORY_LABELS = {
    "mcp_servers": "MCP Servers",
    "cli_tools": "CLI Tools",
    "env_vars": "Environment Variables",
    "git_repos": "Git Repositories",
    "compiled_binaries": "Compiled Binaries",
    "skill_trees": "Skill Trees",
    "docker": "Docker",
    "packages": "Packages",
    "sourced_files": "Sourced Files",
}


def _dep_name(result: CheckResult) -> str:
    """Extract a display name from the dependency object."""
    dep = result.dependency
    if hasattr(dep, "id"):
        return dep.id
    if hasattr(dep, "name"):
        return dep.name
    if hasattr(dep, "path"):
        return dep.path
    if hasattr(dep, "file"):
        return dep.file or "(unnamed)"
    return str(dep)


def display_readiness_report(report: ReadinessReport) -> None:
    """Print Rich-formatted readiness report to terminal."""
    console = Console()

    # Header
    overall_color = _OVERALL_COLORS.get(report.overall_status, "white")
    header = Text()
    header.append("Preflight Readiness: ", style="bold")
    header.append(report.overall_status, style=f"bold {overall_color}")

    console.print()
    console.print(Panel(
        header,
        subtitle=f"Target: {report.target_os}/{report.target_arch}",
        border_style=overall_color,
    ))

    # Summary counts
    console.print(
        f"  [green]✓ {report.green_count} GREEN[/green]  "
        f"[yellow]⚠ {report.yellow_count} YELLOW[/yellow]  "
        f"[red]✗ {report.red_count} RED[/red]"
    )
    console.print()

    # Results by category
    for category, results in report.results.items():
        label = _CATEGORY_LABELS.get(category, category)

        table = Table(
            title=label,
            show_header=True,
            header_style="bold",
            show_lines=False,
            padding=(0, 1),
        )
        table.add_column("", width=3)  # status icon
        table.add_column("Name", style="cyan", min_width=20)
        table.add_column("Status", min_width=8)
        table.add_column("Details", ratio=1)

        for result in results:
            icon = _STATUS_ICONS.get(result.status, "?")
            color = _STATUS_COLORS.get(result.status, "white")
            name = _dep_name(result)

            detail = result.message
            if result.remediation:
                detail += f"\n[dim]{result.remediation}[/dim]"

            table.add_row(
                icon,
                name,
                f"[{color}]{result.status}[/{color}]",
                detail,
            )

        console.print(table)
        console.print()

    # Manual checklist
    if report.manual_checklist:
        console.print("[bold]Manual Checklist:[/bold]")
        for item in report.manual_checklist:
            console.print(f"  □ {item}")
        console.print()

    # Source info
    if report.manifest:
        m = report.manifest
        console.print(f"[dim]Source: {m.source_platform} on {m.source_os}/{m.source_arch}[/dim]")
        if m.contents.agents or m.contents.skills:
            console.print(
                f"[dim]Contents: {len(m.contents.agents)} agent(s), "
                f"{len(m.contents.skills)} skill(s)[/dim]"
            )


def _check_result_to_dict(result: CheckResult) -> Dict[str, Any]:
    """Serialize a single CheckResult to a dict."""
    return {
        "name": _dep_name(result),
        "status": result.status,
        "message": result.message,
        "remediation": result.remediation,
    }


def report_to_json(report: ReadinessReport) -> str:
    """Serialize report to JSON string for --json flag."""
    data = {
        "overall_status": report.overall_status,
        "target_os": report.target_os,
        "target_arch": report.target_arch,
        "green_count": report.green_count,
        "yellow_count": report.yellow_count,
        "red_count": report.red_count,
        "results": {},
        "manual_checklist": report.manual_checklist,
    }  # type: Dict[str, Any]

    for category, results in report.results.items():
        data["results"][category] = [
            _check_result_to_dict(r) for r in results
        ]

    if report.manifest:
        data["source"] = {
            "platform": report.manifest.source_platform,
            "os": report.manifest.source_os,
            "arch": report.manifest.source_arch,
        }

    return json.dumps(data, indent=2)
