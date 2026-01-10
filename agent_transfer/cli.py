"""Command-line interface for agent-transfer."""

import sys
from pathlib import Path

import click
from rich.console import Console

from . import __version__
from .utils.parser import find_all_agents
from .utils.transfer import export_agents, import_agents, import_agents_selective
from .utils.discovery import discover_claude_code_info, display_discovery_info
from .utils.web_server import start_server
from .utils.conflict_resolver import ConflictMode
from .utils.tool_checker import (
    check_all_agents, display_compatibility_report,
    get_missing_servers, check_tool_compatibility
)
from .utils.discovery import find_agent_directories
from .utils.import_analyzer import analyze_import_archive
from .utils.selector import interactive_select_import_agents

console = Console()


@click.group()
@click.version_option(version=__version__)
def cli():
    """Transfer Claude Code agents between systems with interactive selection."""
    pass


@cli.command()
@click.argument('output_file', required=False)
@click.option('--all', 'export_all', is_flag=True, help='Export all agents without interactive selection')
@click.option('--interactive/--no-interactive', default=True, help='Use interactive selection (default: True)')
@click.option('--type', 'agent_type', type=click.Choice(['user', 'project', 'all']), default='all',
              help='Filter by agent type: user, project, or all (default: all)')
@click.option('--discover', is_flag=True, help='Show Claude Code installation info before export')
def export(output_file, export_all, interactive, agent_type, discover):
    """Export agents to a tar.gz archive.

    If OUTPUT_FILE is not provided, a timestamped filename will be used.

    Use --type to filter by agent type (user agents are in ~/.claude/agents,
    project agents are in .claude/agents within project directories).
    """
    try:
        if discover:
            info = discover_claude_code_info()
            display_discovery_info(info)
            console.print()

        if export_all:
            interactive = False

        # Convert 'all' to None for the function
        type_filter = None if agent_type == 'all' else agent_type

        result_file = export_agents(
            output_file=output_file,
            interactive=interactive,
            agent_type_filter=type_filter
        )
        console.print(f"\n[green]✓ Successfully exported to: {result_file}[/green]")
    except KeyboardInterrupt:
        console.print("\n[yellow]Export cancelled[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.argument('input_file', type=click.Path(exists=True))
@click.option('--overwrite', is_flag=True, help='Overwrite existing agents without prompting (legacy, use --conflict-mode)')
@click.option('--conflict-mode', '-c', type=click.Choice(['overwrite', 'keep', 'duplicate', 'diff']),
              default='diff', help='How to handle conflicts: overwrite, keep, duplicate, or diff (default: diff)')
@click.option('--discover', is_flag=True, help='Show Claude Code installation info before import')
@click.option('--bulk', is_flag=True, help='Skip preview, import all agents (old behavior)')
@click.option('--agent', type=str, help='Import specific agent by name')
def import_cmd(input_file, overwrite, conflict_mode, discover, bulk, agent):
    """Import agents from a tar.gz archive.

    INPUT_FILE is the path to the backup archive to import.

    By default, shows an interactive preview where you can select which
    agents to import. Use --bulk to import all agents without preview.

    Conflict handling modes:
      - diff: Interactive diff/merge (default) - view changes and choose what to keep
      - overwrite: Replace existing files with incoming
      - keep: Skip conflicts, keep existing files
      - duplicate: Save incoming as filename_1.md, filename_2.md, etc.

    Examples:
      agent-transfer import backup.tar.gz              # Interactive preview
      agent-transfer import backup.tar.gz --bulk       # Import all
      agent-transfer import backup.tar.gz --agent data-analyst  # Import one
    """
    try:
        if discover:
            info = discover_claude_code_info()
            display_discovery_info(info)
            console.print()

        # Convert string to ConflictMode enum
        mode = ConflictMode(conflict_mode)

        # Legacy --overwrite flag takes precedence if specified
        if overwrite:
            mode = ConflictMode.OVERWRITE

        # Route based on flags
        if bulk:
            # OLD BEHAVIOR: Import all agents
            import_agents(input_file, conflict_mode=mode)
        elif agent:
            # DIRECT IMPORT: Import specific agent by name
            preview = analyze_import_archive(input_file)

            # Find agent in comparisons
            comparison = None
            for comp in preview.comparisons:
                if comp.agent.name == agent:
                    comparison = comp
                    break

            if not comparison:
                console.print(f"[red]Error: Agent '{agent}' not found in archive[/red]")
                console.print("\n[cyan]Available agents:[/cyan]")
                for comp in preview.comparisons:
                    console.print(f"  - {comp.agent.name} ({comp.status})")
                sys.exit(1)

            # Import single agent
            total_count = len(preview.comparisons)
            import_agents_selective(input_file, [comparison], mode, total_count)
        else:
            # DEFAULT: Interactive preview (NEW BEHAVIOR)
            from rich.panel import Panel
            from rich.prompt import Confirm

            preview = analyze_import_archive(input_file)

            # Show preview summary
            console.print(Panel(
                f"[bold]Archive:[/bold] {input_file}\n"
                f"[bold]Agents:[/bold] {len(preview.comparisons)} total\n"
                f"  [green]NEW:[/green] {preview.new_count}\n"
                f"  [yellow]CHANGED:[/yellow] {preview.changed_count}\n"
                f"  [dim]IDENTICAL:[/dim] {preview.identical_count}",
                title="Import Preview",
                border_style="cyan"
            ))

            # Handle all identical case
            if preview.new_count == 0 and preview.changed_count == 0 and len(preview.comparisons) > 0:
                console.print("\n[yellow]All agents are identical to local versions.[/yellow]")
                if not Confirm.ask("Show identical agents anyway?", default=False):
                    console.print("[dim]Import cancelled[/dim]")
                    return

            # Interactive selection
            selected = interactive_select_import_agents(preview.comparisons)

            if not selected:
                console.print("[yellow]No agents selected. Import cancelled.[/yellow]")
                return

            # Import selected agents
            total_count = len(preview.comparisons)
            import_agents_selective(input_file, selected, mode, total_count)

        console.print(f"\n[green]✓ Import operation complete[/green]")
    except KeyboardInterrupt:
        console.print("\n[yellow]Import cancelled[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        sys.exit(1)


@cli.command()
@click.option('--discover', is_flag=True, help='Show Claude Code installation discovery info')
def list_agents(discover):
    """List all available agents."""
    if discover:
        info = discover_claude_code_info()
        display_discovery_info(info)
        return
    
    agents = find_all_agents()
    
    if not agents:
        console.print("[yellow]No agents found![/yellow]")
        console.print("\n[dim]Run with --discover to see search locations[/dim]")
        console.print("  [cyan]agent-transfer list-agents --discover[/cyan]")
        return
    
    from rich.table import Table
    from rich import box
    
    table = Table(title="Available Agents", box=box.ROUNDED, show_header=True)
    table.add_column("#", width=4, justify="right")
    table.add_column("Name", width=25, style="cyan")
    table.add_column("Description", width=50)
    table.add_column("Type", width=8, justify="center")
    table.add_column("Tools", width=20)
    
    for idx, agent in enumerate(agents, 1):
        type_style = "green" if agent.agent_type == "user" else "blue"
        type_text = "User" if agent.agent_type == "user" else "Project"
        
        tools_str = ", ".join(agent.tools[:3])
        if len(agent.tools) > 3:
            tools_str += f" (+{len(agent.tools) - 3})"
        if not tools_str:
            tools_str = "N/A"
        
        desc = agent.description
        if len(desc) > 47:
            desc = desc[:44] + "..."
        
        table.add_row(
            str(idx),
            agent.name,
            desc,
            f"[{type_style}]{type_text}[/{type_style}]",
            tools_str
        )
    
    console.print(table)
    console.print(f"\n[dim]Total: {len(agents)} agent(s)[/dim]")


@cli.command()
def discover():
    """Discover Claude Code installation and agent directories.
    
    Performs a deep search to find Claude Code in:
    - PATH
    - npm global installations
    - Virtual environments (venv, .venv, env)
    - Conda environments
    - System and user installations
    - Custom locations
    """
    info = discover_claude_code_info()
    display_discovery_info(info)


@cli.command()
@click.option('--host', default='127.0.0.1', help='Host to bind to')
@click.option('--port', default=7651, help='Port to bind to')
@click.option('--no-browser', is_flag=True, help='Don\'t open browser automatically')
def view(host, port, no_browser):
    """Launch web viewer to browse agents with beautiful HTML interface.
    
    Opens a web server with:
    - Sidebar navigation of all agents
    - Beautiful markdown rendering
    - Syntax highlighting
    - Easy browsing interface
    """
    try:
        start_server(host=host, port=port, open_browser=not no_browser)
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Error starting server: {e}[/red]")
        console.print("\n[dim]Make sure FastAPI and uvicorn are installed:[/dim]")
        console.print("[cyan]uv pip install fastapi uvicorn markdown pygments[/cyan]")
        sys.exit(1)


@cli.command()
@click.option('--verbose', '-v', is_flag=True, help='Show detailed tool information')
def validate_tools(verbose):
    """Check tool compatibility for all agents.

    Scans all agents and checks if the tools they reference are available
    on this system. This is useful before importing agents to verify
    compatibility.

    Tools are checked against:
    - Built-in Claude Code tools (always available)
    - MCP servers configured in ~/.claude/mcp_servers.json

    Examples:
        agent-transfer validate-tools
        agent-transfer validate-tools --verbose
    """
    try:
        # Get agent directories - returns list of (path, type) tuples
        agent_dirs = find_agent_directories()
        agent_paths = [path for path, _ in agent_dirs]

        console.print("[cyan]Scanning agents for tool compatibility...[/cyan]\n")

        # Check all agents
        reports = check_all_agents(agent_paths)

        # Display report
        display_compatibility_report(reports)

        # Exit with error code if incompatible agents found
        incompatible = [r for r in reports if not r.is_compatible]
        if incompatible:
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]Error checking tools: {e}[/red]")
        sys.exit(1)


def main():
    """Main entry point."""
    cli()


if __name__ == '__main__':
    main()

