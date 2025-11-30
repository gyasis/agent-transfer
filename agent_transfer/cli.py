"""Command-line interface for agent-transfer."""

import sys
from pathlib import Path

import click
from rich.console import Console

from . import __version__
from .utils.parser import find_all_agents
from .utils.transfer import export_agents, import_agents
from .utils.discovery import discover_claude_code_info, display_discovery_info
from .utils.web_server import start_server
from .utils.conflict_resolver import ConflictMode
from .utils.tool_checker import (
    check_all_agents, display_compatibility_report,
    get_missing_servers, check_tool_compatibility
)
from .utils.discovery import find_agent_directories

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
@click.option('--discover', is_flag=True, help='Show Claude Code installation info before export')
def export(output_file, export_all, interactive, discover):
    """Export agents to a tar.gz archive.
    
    If OUTPUT_FILE is not provided, a timestamped filename will be used.
    """
    try:
        if discover:
            info = discover_claude_code_info()
            display_discovery_info(info)
            console.print()
        
        if export_all:
            interactive = False
        
        result_file = export_agents(
            output_file=output_file,
            interactive=interactive
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
def import_cmd(input_file, overwrite, conflict_mode, discover):
    """Import agents from a tar.gz archive.

    INPUT_FILE is the path to the backup archive to import.

    Conflict handling modes:
      - diff: Interactive diff/merge (default) - view changes and choose what to keep
      - overwrite: Replace existing files with incoming
      - keep: Skip conflicts, keep existing files
      - duplicate: Save incoming as filename_1.md, filename_2.md, etc.
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

        import_agents(input_file, conflict_mode=mode)
        console.print(f"\n[green]✓ Successfully imported from: {input_file}[/green]")
    except KeyboardInterrupt:
        console.print("\n[yellow]Import cancelled[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
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

