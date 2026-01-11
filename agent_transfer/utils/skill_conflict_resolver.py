"""Directory-aware conflict resolution for skill imports."""

import hashlib
import shutil
from pathlib import Path
from typing import Dict

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich import box

from ..models import SkillComparison
from .conflict_resolver import ConflictMode
from .skill_parser import parse_skill_directory

console = Console()


def hash_file(file_path: Path) -> str:
    """Compute SHA256 hash of file content.

    Args:
        file_path: Path to file to hash

    Returns:
        Hex digest string
    """
    sha256_hash = hashlib.sha256()

    try:
        with open(file_path, "rb") as f:
            # Read in 4096-byte chunks for memory efficiency
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    except Exception:
        # Return empty hash for files that can't be read
        return ""


def compare_skill_directories(
    existing_dir: Path,
    incoming_dir: Path
) -> SkillComparison:
    """Compare two skill directories using file hashing.

    Args:
        existing_dir: Path to existing local skill directory
        incoming_dir: Path to incoming skill directory from archive

    Returns:
        SkillComparison object with detailed change analysis
    """
    # Hash all files in existing directory
    existing_files: Dict[str, str] = {}
    if existing_dir.exists():
        for file_path in existing_dir.rglob("*"):
            if file_path.is_file():
                rel_path = str(file_path.relative_to(existing_dir))
                existing_files[rel_path] = hash_file(file_path)

    # Hash all files in incoming directory
    incoming_files: Dict[str, str] = {}
    for file_path in incoming_dir.rglob("*"):
        if file_path.is_file():
            rel_path = str(file_path.relative_to(incoming_dir))
            incoming_files[rel_path] = hash_file(file_path)

    # Calculate differences
    existing_set = set(existing_files.keys())
    incoming_set = set(incoming_files.keys())

    added_files = sorted(incoming_set - existing_set)
    removed_files = sorted(existing_set - incoming_set)

    # Find modified files (in both, different hashes)
    modified_files = []
    for rel_path in sorted(existing_set & incoming_set):
        if existing_files[rel_path] != incoming_files[rel_path]:
            modified_files.append(rel_path)

    # Determine status
    if not existing_files:
        status = "NEW"
    elif added_files or removed_files or modified_files:
        status = "CHANGED"
    else:
        status = "IDENTICAL"

    # Create diff summary
    diff_summary = None
    if status == "CHANGED":
        diff_summary = f"+{len(added_files)} -{len(removed_files)} ~{len(modified_files)}"

    # Parse incoming directory as Skill
    skill = parse_skill_directory(incoming_dir)
    if not skill:
        raise ValueError(f"Failed to parse skill directory: {incoming_dir}")

    # Create comparison object
    return SkillComparison(
        skill=skill,
        status=status,
        local_path=existing_dir if existing_dir.exists() else None,
        local_files=existing_files,
        archive_files=incoming_files,
        added_files=added_files,
        removed_files=removed_files,
        modified_files=modified_files,
        diff_summary=diff_summary
    )


def restore_permissions(source_dir: Path, target_dir: Path) -> None:
    """Restore file permissions from source to target directory.

    Args:
        source_dir: Directory with original permissions
        target_dir: Directory to restore permissions to
    """
    try:
        for source_path in source_dir.rglob("*"):
            if source_path.is_file():
                rel_path = source_path.relative_to(source_dir)
                target_path = target_dir / rel_path

                if target_path.exists():
                    try:
                        # Get source permissions
                        source_mode = source_path.stat().st_mode
                        # Apply to target
                        target_path.chmod(source_mode)
                    except Exception as e:
                        # Warn but don't fail
                        console.print(
                            f"[yellow]Warning: Could not restore permissions for {rel_path}: {e}[/yellow]"
                        )
    except Exception as e:
        console.print(f"[yellow]Warning: Permission restore failed: {e}[/yellow]")


def show_skill_diff_summary(comparison: SkillComparison) -> None:
    """Display detailed diff summary for a skill comparison.

    Args:
        comparison: SkillComparison object to display
    """
    skill = comparison.skill

    # Create info panel
    info_lines = [
        f"[bold cyan]{skill.name}[/bold cyan]",
        f"Status: [{_get_status_color(comparison.status)}]{comparison.status}[/{_get_status_color(comparison.status)}]",
        f"Type: {skill.skill_type}",
        f"Files: {skill.file_count}",
        f"Size: {_format_bytes(skill.total_size_bytes)}",
    ]

    if comparison.local_path:
        info_lines.append(f"Local: {comparison.local_path}")

    if comparison.diff_summary:
        info_lines.append(f"Changes: {comparison.diff_summary}")

    console.print(Panel(
        "\n".join(info_lines),
        title=f"Skill: {skill.name}",
        border_style="cyan"
    ))

    # Show file changes if any
    if comparison.status == "CHANGED":
        console.print("\n[bold]File Changes:[/bold]")

        if comparison.added_files:
            console.print(f"[green]+ Added ({len(comparison.added_files)} files):[/green]")
            for file_path in comparison.added_files[:5]:
                console.print(f"  [green]+ {file_path}[/green]")
            if len(comparison.added_files) > 5:
                console.print(f"  [dim]... and {len(comparison.added_files) - 5} more[/dim]")

        if comparison.removed_files:
            console.print(f"[red]- Removed ({len(comparison.removed_files)} files):[/red]")
            for file_path in comparison.removed_files[:5]:
                console.print(f"  [red]- {file_path}[/red]")
            if len(comparison.removed_files) > 5:
                console.print(f"  [dim]... and {len(comparison.removed_files) - 5} more[/dim]")

        if comparison.modified_files:
            console.print(f"[yellow]~ Modified ({len(comparison.modified_files)} files):[/yellow]")
            for file_path in comparison.modified_files[:5]:
                console.print(f"  [yellow]~ {file_path}[/yellow]")
            if len(comparison.modified_files) > 5:
                console.print(f"  [dim]... and {len(comparison.modified_files) - 5} more[/dim]")


def show_skill_file_diff_table(comparison: SkillComparison) -> None:
    """Display file changes in a rich table format.

    Args:
        comparison: SkillComparison object
    """
    if comparison.status == "IDENTICAL":
        console.print("[green]All files are identical[/green]")
        return

    table = Table(
        title=f"File Changes: {comparison.skill.name}",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta"
    )
    table.add_column("Status", width=8, justify="center")
    table.add_column("File Path", width=60)
    table.add_column("Type", width=12)

    # Add rows for each file change
    for file_path in comparison.added_files:
        file_type = Path(file_path).suffix or "no ext"
        table.add_row(
            "[green]+[/green]",
            f"[green]{file_path}[/green]",
            file_type
        )

    for file_path in comparison.modified_files:
        file_type = Path(file_path).suffix or "no ext"
        table.add_row(
            "[yellow]~[/yellow]",
            f"[yellow]{file_path}[/yellow]",
            file_type
        )

    for file_path in comparison.removed_files:
        file_type = Path(file_path).suffix or "no ext"
        table.add_row(
            "[red]-[/red]",
            f"[red]{file_path}[/red]",
            file_type
        )

    console.print(table)


def get_duplicate_skill_name(target_base: Path, skill_name: str) -> Path:
    """Find next available numeric suffix for duplicate skill.

    Args:
        target_base: Base directory for skills
        skill_name: Original skill name

    Returns:
        Path to unused skill directory

    Examples:
        skill-name -> skill-name_1
        skill-name_1 -> skill-name_2
    """
    counter = 1
    while (target_base / f"{skill_name}_{counter}").exists():
        counter += 1
    return target_base / f"{skill_name}_{counter}"


def resolve_skill_conflict(
    existing_dir: Path,
    incoming_dir: Path,
    target_base: Path,
    mode: ConflictMode
) -> bool:
    """Resolve conflict for a skill directory.

    Args:
        existing_dir: Path to existing local skill directory
        incoming_dir: Path to incoming skill directory from archive
        target_base: Base directory for skills (user-skills or project-skills)
        mode: Conflict resolution mode

    Returns:
        True if imported, False if skipped
    """
    # Analyze changes
    comparison = compare_skill_directories(existing_dir, incoming_dir)

    console.print()
    console.print(Panel(
        f"[bold yellow]Skill Conflict Detected[/bold yellow]\n"
        f"Skill: [cyan]{comparison.skill.name}[/cyan]\n"
        f"Status: {comparison.status}",
        border_style="yellow"
    ))

    if mode == ConflictMode.OVERWRITE:
        # Remove existing and copy incoming
        shutil.rmtree(existing_dir)
        shutil.copytree(incoming_dir, existing_dir)
        restore_permissions(incoming_dir, existing_dir)
        console.print(f"[green]Overwritten: {comparison.skill.name}[/green]")
        return True

    elif mode == ConflictMode.KEEP:
        # Skip import
        console.print(f"[dim]Kept existing: {comparison.skill.name}[/dim]")
        return False

    elif mode == ConflictMode.DUPLICATE:
        # Save as duplicate with numeric suffix
        dup_path = get_duplicate_skill_name(target_base, comparison.skill.name)
        shutil.copytree(incoming_dir, dup_path)
        restore_permissions(incoming_dir, dup_path)
        console.print(f"[green]Saved as duplicate: {dup_path.name}[/green]")
        return True

    elif mode == ConflictMode.DIFF:
        # Interactive merge UI
        return resolve_skill_conflict_interactive(
            existing_dir,
            incoming_dir,
            target_base,
            comparison
        )

    return False


def resolve_skill_conflict_interactive(
    existing_dir: Path,
    incoming_dir: Path,
    target_base: Path,
    comparison: SkillComparison
) -> bool:
    """Interactive conflict resolution with file-by-file choices.

    Args:
        existing_dir: Path to existing local skill directory
        incoming_dir: Path to incoming skill directory
        target_base: Base directory for skills
        comparison: Pre-computed SkillComparison object

    Returns:
        True if imported, False if skipped
    """
    while True:
        console.print("\n[bold]Options:[/bold]")
        console.print("  [cyan]o[/cyan] - Overwrite with incoming")
        console.print("  [cyan]k[/cyan] - Keep existing (skip)")
        console.print("  [cyan]d[/cyan] - Duplicate (save as {}_1)".format(comparison.skill.name))
        console.print("  [cyan]v[/cyan] - View detailed changes")
        console.print("  [cyan]t[/cyan] - View file table")
        console.print("  [cyan]f[/cyan] - File-by-file merge")

        choice = Prompt.ask(
            "\n[bold cyan]Choice[/bold cyan]",
            choices=["o", "k", "d", "v", "t", "f"],
            default="v"
        )

        if choice == "o":
            shutil.rmtree(existing_dir)
            shutil.copytree(incoming_dir, existing_dir)
            restore_permissions(incoming_dir, existing_dir)
            console.print(f"[green]Overwritten: {comparison.skill.name}[/green]")
            return True

        elif choice == "k":
            console.print(f"[dim]Kept existing: {comparison.skill.name}[/dim]")
            return False

        elif choice == "d":
            dup_path = get_duplicate_skill_name(target_base, comparison.skill.name)
            shutil.copytree(incoming_dir, dup_path)
            restore_permissions(incoming_dir, dup_path)
            console.print(f"[green]Saved as duplicate: {dup_path.name}[/green]")
            return True

        elif choice == "v":
            show_skill_diff_summary(comparison)
            continue

        elif choice == "t":
            show_skill_file_diff_table(comparison)
            continue

        elif choice == "f":
            return file_by_file_merge(
                existing_dir,
                incoming_dir,
                comparison
            )

    return False


def file_by_file_merge(
    existing_dir: Path,
    incoming_dir: Path,
    comparison: SkillComparison
) -> bool:
    """Interactive file-by-file merge for skill directories.

    Args:
        existing_dir: Path to existing directory
        incoming_dir: Path to incoming directory
        comparison: SkillComparison with file lists

    Returns:
        True if any files were merged, False if cancelled
    """
    console.print(Panel(
        "[bold cyan]File-by-File Merge[/bold cyan]\n"
        "Review each changed file individually",
        border_style="cyan"
    ))

    changes_made = False

    # Handle added files
    for file_path in comparison.added_files:
        console.print(f"\n[green]+ New file: {file_path}[/green]")
        if Confirm.ask("Add this file?", default=True):
            source = incoming_dir / file_path
            target = existing_dir / file_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            console.print(f"[green]Added: {file_path}[/green]")
            changes_made = True

    # Handle modified files
    for file_path in comparison.modified_files:
        console.print(f"\n[yellow]~ Modified: {file_path}[/yellow]")
        console.print("[bold]Options:[/bold]")
        console.print("  [cyan]k[/cyan] - Keep existing")
        console.print("  [cyan]r[/cyan] - Replace with incoming")
        console.print("  [cyan]s[/cyan] - Skip")

        choice = Prompt.ask(
            "[bold cyan]Choice[/bold cyan]",
            choices=["k", "r", "s"],
            default="k"
        )

        if choice == "r":
            source = incoming_dir / file_path
            target = existing_dir / file_path
            shutil.copy2(source, target)
            console.print(f"[green]Replaced: {file_path}[/green]")
            changes_made = True
        elif choice == "k":
            console.print(f"[dim]Kept existing: {file_path}[/dim]")
        else:
            console.print(f"[dim]Skipped: {file_path}[/dim]")

    # Handle removed files
    for file_path in comparison.removed_files:
        console.print(f"\n[red]- Removed in incoming: {file_path}[/red]")
        if Confirm.ask("Delete this file?", default=False):
            target = existing_dir / file_path
            target.unlink()
            console.print(f"[red]Deleted: {file_path}[/red]")
            changes_made = True

    # Restore permissions for modified files
    if changes_made:
        restore_permissions(incoming_dir, existing_dir)
        console.print(f"\n[green]Merge completed for: {comparison.skill.name}[/green]")
    else:
        console.print("\n[dim]No changes made[/dim]")

    return changes_made


def _get_status_color(status: str) -> str:
    """Get Rich color for status."""
    colors = {
        "NEW": "green",
        "CHANGED": "yellow",
        "IDENTICAL": "dim"
    }
    return colors.get(status, "white")


def _format_bytes(size: int) -> str:
    """Format bytes as human-readable string."""
    size_float = float(size)
    for unit in ["B", "KB", "MB", "GB"]:
        if size_float < 1024.0:
            return f"{size_float:.1f} {unit}"
        size_float /= 1024.0
    return f"{size_float:.1f} TB"
