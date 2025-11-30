#!/usr/bin/env python3
"""Quick script to find agent directories."""

from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()

# Standard locations
locations = [
    ("User-level (standard)", Path.home() / ".claude" / "agents"),
    ("Project-level (current)", Path.cwd() / ".claude" / "agents"),
    ("User config", Path.home() / ".claude"),
]

console.print("\n[bold cyan]Searching for Claude Code agent directories...[/bold cyan]\n")

table = Table(title="Agent Directory Locations", box=box.ROUNDED, show_header=True)
table.add_column("Type", width=25, style="cyan")
table.add_column("Path", width=60)
table.add_column("Exists", width=10, justify="center")
table.add_column("Agent Files", width=12, justify="right")

found_any = False

for location_type, path in locations:
    exists = "✓ Yes" if path.exists() else "✗ No"
    exists_style = "[green]✓ Yes[/green]" if path.exists() else "[red]✗ No[/red]"
    
    agent_count = 0
    if path.exists() and path.is_dir():
        agent_files = list(path.glob("*.md"))
        agent_count = len(agent_files)
        found_any = True
    
    table.add_row(
        location_type,
        str(path),
        exists_style,
        str(agent_count) if agent_count > 0 else "-"
    )

console.print(table)

if found_any:
    console.print("\n[green]Found agent directories![/green]\n")
    
    # Show details for each found directory
    for location_type, path in locations:
        if path.exists() and path.is_dir():
            agent_files = list(path.glob("*.md"))
            if agent_files:
                console.print(f"[bold]{location_type}:[/bold] {path}")
                for agent_file in sorted(agent_files):
                    console.print(f"  - {agent_file.name}")
                console.print()
else:
    console.print("\n[yellow]No agent directories found in standard locations.[/yellow]")
    console.print("\n[dim]Claude Code agents are typically stored in:[/dim]")
    console.print("  - ~/.claude/agents (user-level)")
    console.print("  - .claude/agents (project-level)")

