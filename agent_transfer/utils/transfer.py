"""Core transfer functionality."""

import os
import shutil
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict

from rich.console import Console
from rich.panel import Panel

from ..models import Agent, AgentComparison, Skill
from .parser import find_all_agents
from .skill_parser import find_all_skills
from .discovery import find_agent_directories
from .conflict_resolver import ConflictMode, resolve_conflict
from .skill_conflict_resolver import resolve_skill_conflict, restore_permissions

console = Console()


def check_claude_code_installed() -> bool:
    """Check if Claude Code CLI is installed using deep discovery."""
    from .discovery import find_claude_code_executable
    return find_claude_code_executable() is not None


def export_agents_and_skills(
    output_file: Optional[str] = None,
    selected_agents: Optional[List[Agent]] = None,
    selected_skills: Optional[List[Skill]] = None,
    interactive: bool = True,
    agent_type_filter: Optional[str] = None,
    export_type: str = 'all'
) -> str:
    """Export agents and/or skills to a tar.gz archive.

    Args:
        output_file: Output filename (auto-generated if None)
        selected_agents: Pre-selected agents (if None, will find/select)
        selected_skills: Pre-selected skills (if None, will find/select)
        interactive: Use interactive selection UI
        agent_type_filter: Filter by type: 'user', 'project', or None for all
        export_type: 'all', 'agents-only', or 'skills-only'
    """
    from .selector import interactive_select_agents

    # Import interactive_select_skills if it exists, otherwise use placeholder
    try:
        from .selector import interactive_select_skills
    except ImportError:
        interactive_select_skills = None

    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"claude-agents-backup_{timestamp}.tar.gz"

    # Process agents if needed
    if export_type in ('all', 'agents-only'):
        if selected_agents is None:
            all_agents = find_all_agents()

            # Apply type filter if specified
            if agent_type_filter:
                all_agents = [a for a in all_agents if a.agent_type == agent_type_filter]
                if not all_agents:
                    console.print(f"[yellow]No {agent_type_filter} agents found![/yellow]")
                    raise SystemExit(1)
                console.print(f"[dim]Filtering by type: {agent_type_filter} ({len(all_agents)} agents)[/dim]")

            if not all_agents:
                console.print("[red]No agents found![/red]")
                console.print("\n[dim]Checked locations:[/dim]")
                console.print(f"  - {Path.home() / '.claude' / 'agents'}")
                console.print(f"  - {Path.cwd() / '.claude' / 'agents'}")
                raise SystemExit(1)

            if interactive:
                console.print("[dim]Launching interactive agent selector...[/dim]")
                selected_agents = interactive_select_agents(all_agents)

                if not selected_agents:
                    console.print("[yellow]No agents selected. Exiting.[/yellow]")
                    raise SystemExit(0)
            else:
                selected_agents = all_agents
    else:
        # Export type is 'skills-only' - skip agent processing
        selected_agents = []

    # Process skills if needed
    if export_type in ('all', 'skills-only'):
        if selected_skills is None:
            all_skills = find_all_skills()

            if not all_skills and export_type == 'skills-only':
                console.print("[red]No skills found![/red]")
                console.print("\n[dim]Checked locations:[/dim]")
                console.print(f"  - {Path.home() / '.claude' / 'skills'}")
                console.print(f"  - {Path.cwd() / '.claude' / 'skills'}")
                raise SystemExit(1)

            if all_skills and interactive and interactive_select_skills:
                console.print("[dim]Launching interactive skill selector...[/dim]")
                selected_skills = interactive_select_skills(all_skills)

                if not selected_skills and export_type == 'skills-only':
                    console.print("[yellow]No skills selected. Exiting.[/yellow]")
                    raise SystemExit(0)
            else:
                selected_skills = all_skills if all_skills else []
    else:
        # Export type is 'agents-only' - skip skill processing
        selected_skills = []
    
    # Create temp directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Organize agents by type
        user_agents_dir = temp_path / "user-agents"
        project_agents_dir = temp_path / "project-agents"
        user_skills_dir = temp_path / "user-skills"
        project_skills_dir = temp_path / "project-skills"

        # Only create directories for what we're exporting
        if export_type in ('all', 'agents-only'):
            user_agents_dir.mkdir()
            project_agents_dir.mkdir()

        if export_type in ('all', 'skills-only'):
            user_skills_dir.mkdir()
            project_skills_dir.mkdir()

        # Copy selected agents
        for agent in selected_agents:
            agent_path = Path(agent.file_path)
            if not agent_path.exists():
                continue

            if agent.agent_type == "user":
                shutil.copy2(agent_path, user_agents_dir / agent_path.name)
            else:
                # Preserve relative path structure for project agents
                try:
                    rel_path = agent_path.relative_to(Path.cwd())
                    target_dir = project_agents_dir / rel_path.parent
                    target_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(agent_path, target_dir / agent_path.name)
                except ValueError:
                    # Agent not under cwd, just copy the file directly
                    shutil.copy2(agent_path, project_agents_dir / agent_path.name)

        # Define ignore patterns for skill directory copying
        def ignore_patterns(_directory, files):
            """Ignore common development artifacts."""
            ignore_list = ['.venv', '__pycache__', '.pyc', '.git', '.DS_Store', 'node_modules']
            return [f for f in files if any(pattern in f for pattern in ignore_list)]

        # Copy selected skills
        user_skill_count = 0
        project_skill_count = 0

        for skill in (selected_skills or []):
            skill_path = Path(skill.skill_path)
            if not skill_path.exists() or not skill_path.is_dir():
                continue

            if skill.skill_type == "user":
                target_dir = user_skills_dir / skill_path.name
                shutil.copytree(skill_path, target_dir, ignore=ignore_patterns)
                user_skill_count += 1
            else:
                # Preserve relative path structure for project skills
                try:
                    rel_path = skill_path.relative_to(Path.cwd())
                    target_dir = project_skills_dir / rel_path
                    target_dir.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(skill_path, target_dir, ignore=ignore_patterns)
                    project_skill_count += 1
                except ValueError:
                    # Skill not under cwd, copy to root of project-skills
                    target_dir = project_skills_dir / skill_path.name
                    shutil.copytree(skill_path, target_dir, ignore=ignore_patterns)
                    project_skill_count += 1
        
        # Create metadata
        metadata = temp_path / "metadata.txt"
        system_name = 'Unknown'
        try:
            if hasattr(os, 'uname'):
                system_name = os.uname().sysname
            elif os.name == 'nt':
                system_name = 'Windows'
            elif os.name == 'posix':
                system_name = 'Unix/Linux'
        except Exception:
            pass

        username = os.getenv('USER') or os.getenv('USERNAME') or 'unknown'

        # Count agents by type
        user_agent_count = sum(1 for a in selected_agents if a.agent_type == "user")
        project_agent_count = sum(1 for a in selected_agents if a.agent_type == "project")

        with open(metadata, 'w') as f:
            f.write(f"""Claude Code Agents and Skills Backup
Created: {datetime.now().isoformat()}
Export Version: 1.1
System: {system_name}
User: {username}
Home Directory: {Path.home()}
User Agents: {user_agent_count}
Project Agents: {project_agent_count}
User Skills: {user_skill_count}
Project Skills: {project_skill_count}
""")
        
        # Create archive
        console.print(f"[blue]Creating archive: {output_file}[/blue]")
        with tarfile.open(output_file, 'w:gz') as tar:
            tar.add(temp_path, arcname='.')

        # Get file size
        file_size = Path(output_file).stat().st_size
        size_mb = file_size / (1024 * 1024)
        size_str = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{file_size / 1024:.2f} KB"

        console.print("[green]Export complete![/green]")
        console.print(f"[dim]Archive: {output_file} ({size_str})[/dim]")
        console.print(f"[dim]Location: {Path(output_file).absolute()}[/dim]")

        # Summary info
        if export_type == 'all':
            agent_count = len(selected_agents) if selected_agents else 0
            skill_count = len(selected_skills) if selected_skills else 0
            console.print(f"[dim]Exported {agent_count} agent(s) and {skill_count} skill(s)[/dim]")
        elif export_type == 'agents-only':
            agent_count = len(selected_agents) if selected_agents else 0
            console.print(f"[dim]Exported {agent_count} agent(s)[/dim]")
        elif export_type == 'skills-only':
            skill_count = len(selected_skills) if selected_skills else 0
            console.print(f"[dim]Exported {skill_count} skill(s)[/dim]")

        return output_file


def export_agents(
    output_file: Optional[str] = None,
    selected_agents: Optional[List[Agent]] = None,
    interactive: bool = True,
    agent_type_filter: Optional[str] = None
) -> str:
    """Export agents to a tar.gz archive (backward compatibility wrapper).

    This function maintains backward compatibility with existing code that calls
    export_agents(). It delegates to export_agents_and_skills() with export_type='agents-only'.

    Args:
        output_file: Output filename (auto-generated if None)
        selected_agents: Pre-selected agents (if None, will find/select)
        interactive: Use interactive selection UI
        agent_type_filter: Filter by type: 'user', 'project', or None for all

    Returns:
        Path to created archive file
    """
    return export_agents_and_skills(
        output_file=output_file,
        selected_agents=selected_agents,
        selected_skills=None,
        interactive=interactive,
        agent_type_filter=agent_type_filter,
        export_type='agents-only'
    )


def import_agents_and_skills(
    input_file: str,
    overwrite: bool = False,
    conflict_mode: Optional[ConflictMode] = None,
    import_type: str = 'all'
) -> None:
    """Import agents and/or skills from a tar.gz archive.

    Args:
        input_file: Path to the backup archive
        overwrite: Legacy flag - if True, sets conflict_mode to OVERWRITE
        conflict_mode: How to handle conflicts (default: DIFF for interactive)
        import_type: Type of import - 'all', 'agents-only', 'skills-only'
    """
    input_path = Path(input_file)

    if not input_path.exists():
        console.print(f"[red]File not found: {input_file}[/red]")
        raise SystemExit(1)

    # Handle legacy overwrite flag
    if conflict_mode is None:
        if overwrite:
            conflict_mode = ConflictMode.OVERWRITE
        else:
            conflict_mode = ConflictMode.DIFF  # Default to interactive diff

    console.print("[blue]Starting agent import...[/blue]")
    console.print(f"[dim]Input file: {input_file}[/dim]")
    console.print(f"[dim]Conflict mode: {conflict_mode.value}[/dim]")

    # Check Claude Code using deep discovery
    from .discovery import find_claude_code_executable, discover_claude_code_info

    claude_exe = find_claude_code_executable()
    if claude_exe:
        info = discover_claude_code_info()
        console.print("[green]Claude Code detected[/green]")
        console.print(f"[dim]Location: {claude_exe}[/dim]")
        console.print(f"[dim]Type: {info['installation_type']}[/dim]")
    else:
        console.print("[yellow]Claude Code not found[/yellow]")
        console.print("[dim]Agents will be extracted but may not be usable[/dim]")
        console.print("[dim]Run 'agent-transfer list-agents --discover' to troubleshoot[/dim]")

    # Extract to temp directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        console.print("[dim]Extracting archive...[/dim]")
        with tarfile.open(input_file, 'r:gz') as tar:
            tar.extractall(temp_path)

        # Read metadata
        metadata_file = temp_path / "metadata.txt"
        if metadata_file.exists():
            console.print("[dim]Backup metadata:[/dim]")
            with open(metadata_file) as f:
                for line in f:
                    console.print(f"  [dim]{line.strip()}[/dim]")

        imported_count = 0
        skipped_count = 0
        conflict_count = 0
        skills_imported = 0
        skills_skipped = 0

        # Import user-level agents (skip if skills-only)
        user_agents_source = temp_path / "user-agents"
        if user_agents_source.exists() and import_type != 'skills-only':
            user_agents = list(user_agents_source.glob("*.md"))
            if user_agents:
                console.print(f"\n[blue]Found {len(user_agents)} user-level agent(s)[/blue]")

                user_agents_dir = Path.home() / '.claude' / 'agents'
                user_agents_dir.mkdir(parents=True, exist_ok=True)

                for agent_file in user_agents:
                    target = user_agents_dir / agent_file.name

                    if target.exists():
                        conflict_count += 1
                        # Use conflict resolver
                        result = resolve_conflict(
                            existing_path=target,
                            incoming_path=agent_file,
                            target_dir=user_agents_dir,
                            mode=conflict_mode
                        )
                        if result:
                            imported_count += 1
                        else:
                            skipped_count += 1
                    else:
                        # No conflict - just copy
                        shutil.copy2(agent_file, target)
                        console.print(f"[green]Imported: {agent_file.name}[/green]")
                        imported_count += 1

                console.print(f"[green]User-level agents directory: {user_agents_dir}[/green]")

        # Import project-level agents (skip if skills-only)
        project_agents_source = temp_path / "project-agents"
        if project_agents_source.exists() and import_type != 'skills-only':
            project_agents = list(project_agents_source.rglob("*.md"))
            if project_agents:
                console.print(f"\n[blue]Found {len(project_agents)} project-level agent(s)[/blue]")

                project_agents_dir = Path.cwd() / '.claude' / 'agents'

                if not project_agents_dir.parent.exists():
                    from rich.prompt import Confirm
                    if Confirm.ask("[yellow]Create .claude/agents in current directory?[/yellow]"):
                        project_agents_dir.mkdir(parents=True, exist_ok=True)
                    else:
                        console.print("[dim]Skipping project-level agents[/dim]")
                        skipped_count += len(project_agents)
                        project_agents = []
                else:
                    project_agents_dir.mkdir(parents=True, exist_ok=True)

                for agent_file in project_agents:
                    target = project_agents_dir / agent_file.name

                    if target.exists():
                        conflict_count += 1
                        # Use conflict resolver
                        result = resolve_conflict(
                            existing_path=target,
                            incoming_path=agent_file,
                            target_dir=project_agents_dir,
                            mode=conflict_mode
                        )
                        if result:
                            imported_count += 1
                        else:
                            skipped_count += 1
                    else:
                        # No conflict - just copy
                        shutil.copy2(agent_file, target)
                        console.print(f"[green]Imported: {agent_file.name}[/green]")
                        imported_count += 1

                if project_agents:
                    console.print(f"[green]Project-level agents directory: {project_agents_dir}[/green]")

        # Import skills (skip if agents-only)
        if import_type in ('all', 'skills-only'):
            # Import user-level skills
            user_skills_source = temp_path / "user-skills"
            if user_skills_source.exists():
                skill_dirs = [d for d in user_skills_source.iterdir() if d.is_dir()]
                if skill_dirs:
                    console.print(f"\n[blue]Found {len(skill_dirs)} user-level skill(s)[/blue]")

                    user_skills_base = Path.home() / '.claude' / 'skills'
                    user_skills_base.mkdir(parents=True, exist_ok=True)

                    for skill_dir in skill_dirs:
                        target_path = user_skills_base / skill_dir.name

                        if target_path.exists():
                            # Conflict - use resolver
                            result = resolve_skill_conflict(
                                existing_dir=target_path,
                                incoming_dir=skill_dir,
                                target_base=user_skills_base,
                                mode=conflict_mode
                            )
                            if result:
                                skills_imported += 1
                            else:
                                skills_skipped += 1
                        else:
                            # No conflict - copy directory and restore permissions
                            shutil.copytree(skill_dir, target_path)
                            restore_permissions(skill_dir, target_path)
                            console.print(f"[green]Imported: {skill_dir.name}[/green]")
                            skills_imported += 1

                            # Show dependency warnings
                            if (skill_dir / 'requirements.txt').exists():
                                console.print(f"[yellow]⚠️  {skill_dir.name} has dependencies:[/yellow]")
                                console.print(f"  Run: uv pip install -r {target_path}/requirements.txt")
                            elif (skill_dir / 'pyproject.toml').exists():
                                console.print(f"[yellow]⚠️  {skill_dir.name} has dependencies:[/yellow]")
                                console.print(f"  Run: cd {target_path} && uv pip install .")

                    console.print(f"[green]User-level skills directory: {user_skills_base}[/green]")

            # Import project-level skills
            project_skills_source = temp_path / "project-skills"
            if project_skills_source.exists():
                skill_dirs = [d for d in project_skills_source.iterdir() if d.is_dir()]
                if skill_dirs:
                    console.print(f"\n[blue]Found {len(skill_dirs)} project-level skill(s)[/blue]")

                    project_skills_base = Path.cwd() / '.claude' / 'skills'

                    if not project_skills_base.parent.exists():
                        from rich.prompt import Confirm
                        if Confirm.ask("[yellow]Create .claude/skills in current directory?[/yellow]"):
                            project_skills_base.mkdir(parents=True, exist_ok=True)
                        else:
                            console.print("[dim]Skipping project-level skills[/dim]")
                            skills_skipped += len(skill_dirs)
                            skill_dirs = []
                    else:
                        project_skills_base.mkdir(parents=True, exist_ok=True)

                    for skill_dir in skill_dirs:
                        target_path = project_skills_base / skill_dir.name

                        if target_path.exists():
                            # Conflict - use resolver
                            result = resolve_skill_conflict(
                                existing_dir=target_path,
                                incoming_dir=skill_dir,
                                target_base=project_skills_base,
                                mode=conflict_mode
                            )
                            if result:
                                skills_imported += 1
                            else:
                                skills_skipped += 1
                        else:
                            # No conflict - copy directory and restore permissions
                            shutil.copytree(skill_dir, target_path)
                            restore_permissions(skill_dir, target_path)
                            console.print(f"[green]Imported: {skill_dir.name}[/green]")
                            skills_imported += 1

                            # Show dependency warnings
                            if (skill_dir / 'requirements.txt').exists():
                                console.print(f"[yellow]⚠️  {skill_dir.name} has dependencies:[/yellow]")
                                console.print(f"  Run: uv pip install -r {target_path}/requirements.txt")
                            elif (skill_dir / 'pyproject.toml').exists():
                                console.print(f"[yellow]⚠️  {skill_dir.name} has dependencies:[/yellow]")
                                console.print(f"  Run: cd {target_path} && uv pip install .")

                    if skill_dirs:
                        console.print(f"[green]Project-level skills directory: {project_skills_base}[/green]")

    # Summary
    console.print()

    # Build summary based on import type
    summary_lines = ["[bold green]Import Complete![/bold green]\n"]

    if import_type in ('all', 'agents-only'):
        summary_lines.append(f"Agents Imported: [green]{imported_count}[/green]")
        summary_lines.append(f"Agent Conflicts: [yellow]{conflict_count}[/yellow]")
        summary_lines.append(f"Agents Skipped: [dim]{skipped_count}[/dim]")

    if import_type in ('all', 'skills-only'):
        if import_type == 'all':
            summary_lines.append("")  # Add blank line between agents and skills
        summary_lines.append(f"Skills Imported: [green]{skills_imported}[/green]")
        summary_lines.append(f"Skills Skipped: [dim]{skills_skipped}[/dim]")

    console.print(Panel(
        "\n".join(summary_lines),
        title="Summary",
        border_style="green"
    ))

    # Verify import
    if import_type in ('all', 'agents-only'):
        total = 0
        agent_dirs = find_agent_directories()

        for agent_dir_path, agent_type in agent_dirs:
            if agent_dir_path.exists():
                agent_count = len(list(agent_dir_path.glob("*.md")))
                total += agent_count
                if agent_count > 0:
                    type_label = "User-level" if agent_type == "user" else "Project-level"
                    console.print(f"[dim]{type_label}: {agent_count} agent(s) in {agent_dir_path}[/dim]")

        console.print(f"[green]Total agents available: {total}[/green]")

    if import_type in ('all', 'skills-only'):
        from .skill_discovery import find_skill_directories

        total_skills = 0
        skill_dirs = find_skill_directories()

        for skill_dir_path, skill_type in skill_dirs:
            if skill_dir_path.exists():
                # Count subdirectories with SKILL.md
                skill_count = sum(1 for d in skill_dir_path.iterdir()
                                 if d.is_dir() and (d / 'SKILL.md').exists())
                total_skills += skill_count
                if skill_count > 0:
                    type_label = "User-level" if skill_type == "user" else "Project-level"
                    console.print(f"[dim]{type_label}: {skill_count} skill(s) in {skill_dir_path}[/dim]")

        console.print(f"[green]Total skills available: {total_skills}[/green]")


def import_agents(
    input_file: str,
    overwrite: bool = False,
    conflict_mode: Optional[ConflictMode] = None
) -> None:
    """Import agents from a tar.gz archive (backward compatibility wrapper).

    This function maintains backward compatibility with existing code that calls
    import_agents(). It delegates to import_agents_and_skills() with import_type='agents-only'.

    Args:
        input_file: Path to the backup archive
        overwrite: Legacy flag - if True, sets conflict_mode to OVERWRITE
        conflict_mode: How to handle conflicts (default: DIFF for interactive)
    """
    return import_agents_and_skills(
        input_file=input_file,
        overwrite=overwrite,
        conflict_mode=conflict_mode,
        import_type='agents-only'
    )


def import_agents_selective(
    archive_path: str,
    selected_comparisons: List[AgentComparison],
    conflict_mode: ConflictMode,
    total_in_archive: int
) -> Dict[str, int]:
    """Import selected agents from a tar.gz archive with per-agent control.

    Args:
        archive_path: Path to the backup archive
        selected_comparisons: List of AgentComparison objects to import
        conflict_mode: How to handle conflicts (OVERWRITE, KEEP, DUPLICATE, DIFF)
        total_in_archive: Total number of agents in the archive (for stats)

    Returns:
        Dict with import statistics:
            - new_imported: Number of new agents imported
            - changed_imported: Number of changed agents imported
            - identical_skipped: Number of identical agents skipped
            - not_selected: Number of agents not selected for import
    """
    archive_file = Path(archive_path)

    if not archive_file.exists():
        console.print(f"[red]Archive not found: {archive_path}[/red]")
        raise SystemExit(1)

    console.print("[blue]Starting selective import...[/blue]")
    console.print(f"[dim]Archive: {archive_path}[/dim]")
    console.print(f"[dim]Importing {len(selected_comparisons)} of {total_in_archive} agents[/dim]")
    console.print(f"[dim]Conflict mode: {conflict_mode.value}[/dim]")

    # Initialize statistics
    new_imported = 0
    changed_imported = 0
    identical_skipped = 0
    not_selected = total_in_archive - len(selected_comparisons)

    # Extract archive to temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        console.print("[dim]Extracting archive...[/dim]")
        with tarfile.open(archive_file, 'r:gz') as tar:
            tar.extractall(temp_path)

        # Read metadata if present
        metadata_file = temp_path / "metadata.txt"
        if metadata_file.exists():
            console.print("[dim]Backup metadata:[/dim]")
            with open(metadata_file) as f:
                for line in f:
                    console.print(f"  [dim]{line.strip()}[/dim]")

        # Process each selected agent
        console.print("\n[bold]Processing selected agents...[/bold]")

        for comparison in selected_comparisons:
            agent = comparison.agent
            filename = Path(agent.file_path).name

            # Determine source and target paths based on agent type
            if agent.agent_type == "user":
                source_dir = temp_path / "user-agents"
                target_dir = Path.home() / ".claude" / "agents"
            else:  # project
                source_dir = temp_path / "project-agents"
                target_dir = Path.cwd() / ".claude" / "agents"

            # Find source file in archive (handle nested structures)
            source_path = None
            for md_file in source_dir.rglob("*.md"):
                if md_file.name == filename:
                    source_path = md_file
                    break

            if not source_path or not source_path.exists():
                console.print(f"[red]Warning: {filename} not found in archive[/red]")
                continue

            # Ensure target directory exists
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / filename

            # Process based on status
            if comparison.status == 'NEW':
                # Direct copy for new agents
                shutil.copy2(source_path, target_path)
                console.print(f"[green]Imported: {filename}[/green]")
                new_imported += 1

            elif comparison.status == 'CHANGED':
                # Handle conflicts using conflict resolver
                result = resolve_conflict(
                    existing_path=target_path,
                    incoming_path=source_path,
                    target_dir=target_dir,
                    mode=conflict_mode
                )
                if result:
                    console.print(f"[green]Updated: {filename}[/green]")
                    changed_imported += 1
                else:
                    console.print(f"[dim]Skipped: {filename}[/dim]")

            elif comparison.status == 'IDENTICAL':
                # Skip identical agents
                console.print(f"[dim]Skipping {filename} (identical)[/dim]")
                identical_skipped += 1

    # Display summary panel
    console.print()
    skipped_total = identical_skipped + not_selected
    summary_panel = Panel(
        f"[bold green]Imported: {new_imported + changed_imported} agents[/bold green]\n"
        f"  NEW: {new_imported}\n"
        f"  CHANGED: {changed_imported}\n\n"
        f"[yellow]Skipped: {skipped_total} agents[/yellow]\n"
        f"  IDENTICAL: {identical_skipped}\n"
        f"  NOT SELECTED: {not_selected}",
        title="Import Complete",
        border_style="green"
    )
    console.print(summary_panel)

    # Return statistics
    return {
        'new_imported': new_imported,
        'changed_imported': changed_imported,
        'identical_skipped': identical_skipped,
        'not_selected': not_selected
    }

