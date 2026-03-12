"""Command-line interface for agent-transfer."""

import sys
from pathlib import Path

import click
from rich.console import Console

from . import __version__
from .utils.parser import find_all_agents
from .utils.transfer import export_agents_and_skills, import_agents_selective, import_agents_and_skills
from .utils.discovery import discover_claude_code_info, display_discovery_info
from .utils.web_server import start_server
from .utils.conflict_resolver import ConflictMode
from .utils.tool_checker import (
    check_all_agents, display_compatibility_report
)
from .utils.skill_validator import (
    validate_all_skills, display_skill_validation_report,
    detect_environment, display_environment_info,
    get_setup_recommendations, display_setup_recommendations,
    validate_archive_skills, display_archive_validation_report,
    get_skills_with_missing_deps,
    check_system_readiness, display_readiness_report
)
from .utils.discovery import find_agent_directories
from .utils.import_analyzer import analyze_import_archive
from .utils.selector import interactive_select_import_agents
from .utils.skill_parser import find_all_skills

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
@click.option('--type', 'export_type',
              type=click.Choice(['all', 'agents', 'skills']),
              default='all',
              help='What to export: all, agents-only, or skills-only')
@click.option('--agent-type', 'agent_type', type=click.Choice(['user', 'project', 'all']), default='all',
              help='Filter by agent type: user, project, or all (default: all)')
@click.option('--discover', is_flag=True, help='Show Claude Code installation info before export')
def export(output_file, export_all, interactive, export_type, agent_type, discover):
    """Export agents to a tar.gz archive.

    If OUTPUT_FILE is not provided, a timestamped filename will be used.

    Use --type to choose what to export (agents, skills, or all).
    Use --agent-type to filter by agent type (user agents are in ~/.claude/agents,
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

        # Map export_type to the format expected by export_agents_and_skills
        type_map = {
            'all': 'all',
            'agents': 'agents-only',
            'skills': 'skills-only'
        }
        mapped_type = type_map[export_type]

        result_file = export_agents_and_skills(
            output_file=output_file,
            interactive=interactive,
            agent_type_filter=type_filter,
            export_type=mapped_type
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
@click.option('--type', 'import_type',
              type=click.Choice(['all', 'agents', 'skills']),
              default='all',
              help='What to import: all, agents-only, or skills-only')
@click.option('--discover', is_flag=True, help='Show Claude Code installation info before import')
@click.option('--bulk', is_flag=True, help='Skip preview, import all agents (old behavior)')
@click.option('--agent', type=str, help='Import specific agent by name')
@click.option('--force', is_flag=True, help='Bypass preflight RED blocks and import anyway')
def import_cmd(input_file, overwrite, conflict_mode, import_type, discover, bulk, agent, force=False):
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

        # Preflight gate: check readiness before importing
        try:
            from .utils.preflight import run_preflight_checks, read_manifest_from_archive
            from .utils.preflight.report import display_readiness_report

            manifest = read_manifest_from_archive(Path(input_file))
            if manifest is None:
                console.print(
                    "[yellow]No preflight data — this archive was created "
                    "before preflight support. Proceeding with import.[/yellow]"
                )
                console.print()
            else:
                report = run_preflight_checks(manifest)
                display_readiness_report(report)

                if report.overall_status == "FAIL" and not force:
                    console.print()
                    if click.confirm(
                        "[red]RED items detected.[/red] Continue with import?",
                        default=False,
                    ):
                        console.print("[yellow]Proceeding despite RED items...[/yellow]")
                    else:
                        console.print("[dim]Import cancelled. Use --force to bypass.[/dim]")
                        sys.exit(1)
                elif report.overall_status == "WARN":
                    console.print(
                        "[yellow]YELLOW warnings detected. Proceeding with import.[/yellow]"
                    )
                    console.print()
        except ImportError:
            pass  # Preflight module not available — proceed without gate
        except Exception as preflight_err:
            console.print(f"[dim yellow]Preflight check skipped: {preflight_err}[/dim yellow]")

        # Convert string to ConflictMode enum
        mode = ConflictMode(conflict_mode)

        # Legacy --overwrite flag takes precedence if specified
        if overwrite:
            mode = ConflictMode.OVERWRITE

        # Map import_type to the format expected by import_agents_and_skills
        type_map = {
            'all': 'all',
            'agents': 'agents-only',
            'skills': 'skills-only'
        }
        mapped_type = type_map[import_type]

        # Route based on flags
        if bulk:
            # OLD BEHAVIOR: Import all agents (now with type support)
            import_agents_and_skills(input_file, conflict_mode=mode, import_type=mapped_type)
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

        console.print("\n[green]✓ Import operation complete[/green]")
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


@cli.command('list-skills')
def list_skills():
    """List all available Claude Code skills."""
    skills = find_all_skills()

    if not skills:
        console.print("[yellow]No skills found[/yellow]")
        console.print("\n[dim]Run 'agent-transfer discover' to see search locations[/dim]")
        return

    from rich.table import Table

    # Create Rich table
    table = Table(title=f"Found {len(skills)} skill(s)")
    table.add_column("Name", style="cyan")
    table.add_column("Type", justify="center")
    table.add_column("Files", justify="right")
    table.add_column("Size", justify="right")
    table.add_column("Scripts", justify="center")
    table.add_column("Deps", justify="center")
    table.add_column("Description", style="dim")

    for skill in skills:
        # Type badge
        type_badge = "[green]USER[/green]" if skill.skill_type == "user" else "[blue]PROJECT[/blue]"

        # Size
        size_mb = skill.total_size_bytes / (1024 * 1024)
        size_str = f"{size_mb:.1f} MB" if size_mb >= 1 else f"{skill.total_size_bytes / 1024:.1f} KB"

        # Scripts indicator
        scripts = "[green]Yes[/green]" if skill.has_scripts else "[dim]No[/dim]"

        # Dependencies indicator
        deps = "[yellow]Yes[/yellow]" if (skill.has_requirements_txt or skill.has_pyproject_toml) else "[dim]No[/dim]"

        # Truncate description
        desc = skill.description[:60] + "..." if len(skill.description) > 60 else skill.description

        table.add_row(
            skill.name,
            type_badge,
            str(skill.file_count),
            size_str,
            scripts,
            deps,
            desc
        )

    console.print(table)


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


@cli.command('validate-skills')
@click.option('--verbose', '-v', is_flag=True, help='Show detailed dependency information')
@click.option('--archive', '-a', type=click.Path(exists=True), help='Validate skills from archive before import')
@click.option('--env', 'show_env', is_flag=True, help='Show current Python environment info')
@click.option('--setup', 'show_setup', is_flag=True, help='Show setup recommendations')
def validate_skills(verbose, archive, show_env, show_setup):
    """Check Python dependency availability for skills.

    Scans skills and checks if the Python packages they reference
    in requirements.txt or pyproject.toml are installed on this system.

    Modes:
      - Default: Validate local installed skills
      - --archive FILE: Validate skills in archive BEFORE importing
      - --env: Show current Python environment details
      - --setup: Show recommended setup commands

    Skills can declare dependencies via:
    - requirements.txt
    - pyproject.toml (dependencies section)
    - uv.lock (indicates uv-managed project)

    If uv is available, it will be recommended for installing missing
    dependencies as it provides faster, isolated environments.

    Examples:
        agent-transfer validate-skills                    # Validate local skills
        agent-transfer validate-skills --archive backup.tar.gz  # Pre-import check
        agent-transfer validate-skills --env              # Show environment info
        agent-transfer validate-skills --setup            # Show setup commands
    """
    import shutil

    try:
        # Show environment info if requested
        if show_env:
            env_info = detect_environment()
            display_environment_info(env_info)
            if not archive and not show_setup:
                return

        # Archive validation mode (pre-import check)
        if archive:
            console.print(f"[cyan]Validating skills in archive: {archive}[/cyan]\n")

            reports, temp_dir = validate_archive_skills(Path(archive))

            try:
                display_archive_validation_report(reports, Path(archive))

                # Show setup recommendations if requested
                if show_setup:
                    env_info = detect_environment()
                    recommendations = get_setup_recommendations(env_info, reports)
                    display_setup_recommendations(recommendations)

                # Exit with error code if missing dependencies
                missing = get_skills_with_missing_deps(reports)
                if missing:
                    sys.exit(1)
            finally:
                # Clean up temp directory
                shutil.rmtree(temp_dir, ignore_errors=True)

            return

        # Default: Validate local skills
        console.print("[cyan]Scanning skills for dependency compatibility...[/cyan]\n")

        # Get all local skills
        skills = find_all_skills()

        if not skills:
            console.print("[yellow]No skills found to validate.[/yellow]")
            console.print("\n[dim]Run 'agent-transfer discover' to see search locations[/dim]")
            return

        # Validate all skills
        reports = validate_all_skills(skills)

        # Display report
        display_skill_validation_report(reports)

        # Show setup recommendations if requested
        if show_setup:
            env_info = detect_environment()
            recommendations = get_setup_recommendations(env_info, reports)
            display_setup_recommendations(recommendations)

        # Exit with error code if missing dependencies found
        missing = get_skills_with_missing_deps(reports)
        if missing:
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]Error checking skill dependencies: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        sys.exit(1)


@cli.command('check-ready')
@click.option('--archive', '-a', type=click.Path(exists=True),
              help='Check readiness for skills in archive before import')
@click.option('--verbose', '-v', is_flag=True, help='Show detailed information')
@click.option('--all-skills', is_flag=True, help='Show all skills, not just those with issues')
def check_ready(archive, verbose, all_skills):
    """Comprehensive system readiness check for skill transfer.

    Performs ALL checks in one command:
      - Python environment detection (pip, uv, venv)
      - Skill dependency validation
      - Missing package collection
      - Setup recommendations

    This is a "one-shot" command that tells you exactly what needs
    to be done before skills can run properly.

    Modes:
      - Default: Check readiness for local skills
      - --archive FILE: Check readiness BEFORE importing archive

    The readiness score (0-100%) considers:
      - Environment (30%): pip available, uv available, venv active
      - Dependencies (70%): Percentage of required packages installed

    Examples:
        agent-transfer check-ready                         # Check local skills
        agent-transfer check-ready --archive backup.tar.gz # Pre-import check
        agent-transfer check-ready --verbose               # Detailed output
        agent-transfer check-ready --all-skills            # Show all skills
    """
    import shutil

    try:
        # Perform comprehensive readiness check
        if archive:
            console.print(f"[cyan]Checking system readiness for archive: {archive}[/cyan]\n")
            report, temp_dir = check_system_readiness(archive_path=Path(archive))
        else:
            console.print("[cyan]Checking system readiness for local skills...[/cyan]\n")
            skills = find_all_skills()
            report, temp_dir = check_system_readiness(local_skills=skills)

        try:
            # Display the comprehensive report
            display_readiness_report(report, verbose=verbose, show_all_skills=all_skills)

            # Exit with appropriate code
            if not report.is_ready:
                sys.exit(1)
            elif report.readiness_score < 100:
                # Not perfect but acceptable
                sys.exit(0)
            else:
                sys.exit(0)

        finally:
            # Clean up temp directory if archive was used
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)

    except Exception as e:
        console.print(f"[red]Error during readiness check: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        sys.exit(1)


@cli.command()
@click.argument('archive', required=False, type=click.Path(exists=False))
@click.option('--json', 'json_output', is_flag=True, help='Machine-readable JSON output')
@click.option('--self', 'self_audit', is_flag=True, help='Audit local environment (no archive needed)')
@click.option('--force', is_flag=True, help='Used with import gate — bypass RED blocks')
def preflight(archive, json_output, self_audit, force):
    """Check transfer readiness for an archive or local environment.

    Run against an archive:
        agent-transfer preflight archive.tar.gz

    Audit local machine:
        agent-transfer preflight --self

    Machine-readable output:
        agent-transfer preflight archive.tar.gz --json
    """
    from .utils.preflight import (
        run_preflight_checks,
        read_manifest_from_archive,
        collect_inventory,
        TransferManifest,
    )
    from .utils.preflight.report import display_readiness_report, report_to_json

    try:
        manifest = None

        if self_audit:
            # T029/T030: Self-audit mode — scan local environment
            from .utils.preflight.collector import collect_inventory as _collect
            try:
                from .utils.pathfinder import get_pathfinder
                pf = get_pathfinder()
                slug = "claude-code"

                # Discover agents
                agents_dir = pf.agents_dir(slug)
                agents = []
                if agents_dir and agents_dir.is_dir():
                    agents = list(agents_dir.glob("*.md"))

                # Discover skills
                skills_dir = pf.skills_dir(slug)
                skills = []
                if skills_dir and skills_dir.is_dir():
                    skills = [d for d in skills_dir.iterdir() if d.is_dir()]

                # Discover MCP configs
                configs = []
                mcp_config = pf.config_dir(slug) / "settings.json"
                if mcp_config.exists():
                    configs.append(mcp_config)
            except Exception:
                agents = []
                skills = []
                configs = []

            manifest = _collect(
                agents=agents,
                skills=skills,
                hooks=[],
                configs=configs,
                platform="claude-code",
            )
        elif archive:
            archive_path = Path(archive)
            if not archive_path.exists():
                console.print(f"[red]Archive not found: {archive}[/red]")
                sys.exit(1)

            manifest = read_manifest_from_archive(archive_path)

            if manifest is None:
                # Legacy archive — no manifest
                console.print(
                    "[yellow]No manifest.json found — this archive was created "
                    "before preflight support.[/yellow]"
                )
                sys.exit(0)
        else:
            console.print("[red]Please provide an archive path or use --self[/red]")
            console.print("Usage: agent-transfer preflight <archive.tar.gz>")
            console.print("       agent-transfer preflight --self")
            sys.exit(1)

        # Run checks
        report = run_preflight_checks(manifest)

        # Output
        if json_output:
            click.echo(report_to_json(report))
        else:
            display_readiness_report(report)

        # Exit code: 0 for PASS/WARN, 1 for FAIL
        if report.overall_status == "FAIL" and not force:
            sys.exit(1)

    except SystemExit:
        raise
    except Exception as e:
        console.print(f"[red]Preflight check failed: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        sys.exit(1)


def main():
    """Main entry point."""
    cli()


if __name__ == '__main__':
    main()

