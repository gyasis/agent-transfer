"""Diff-based conflict resolution for agent imports."""

import difflib
import re
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.syntax import Syntax
from rich.table import Table
from rich import box

from ..models import AgentComparison

console = Console()


class ConflictMode(Enum):
    """Conflict resolution modes."""
    OVERWRITE = "overwrite"
    KEEP = "keep"
    DUPLICATE = "duplicate"
    DIFF = "diff"  # Default - interactive merge


@dataclass
class DiffBlock:
    """Represents a block of differing lines."""
    block_num: int
    start_line: int
    end_line: int
    existing_lines: List[str]
    incoming_lines: List[str]
    context_before: List[str]
    context_after: List[str]


def parse_agent_sections(content: str) -> Tuple[str, str]:
    """Split agent file into YAML frontmatter and markdown body.

    Returns:
        Tuple of (yaml_frontmatter, markdown_body).
        If no frontmatter, returns ("", full_content).
    """
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', content, re.DOTALL)
    if match:
        return match.group(1), match.group(2)
    return "", content


def show_unified_diff(existing: str, incoming: str, filename: str) -> None:
    """Display colored unified diff using Rich."""
    diff_lines = list(difflib.unified_diff(
        existing.splitlines(keepends=True),
        incoming.splitlines(keepends=True),
        fromfile=f"existing/{filename}",
        tofile=f"incoming/{filename}",
        lineterm=""
    ))

    if not diff_lines:
        console.print("[green]Files are identical[/green]")
        return

    diff_text = '\n'.join(diff_lines)
    console.print(Syntax(diff_text, "diff", theme="monokai", line_numbers=True))


def show_side_by_side(existing: str, incoming: str, filename: str) -> None:
    """Display side-by-side comparison using Rich Table."""
    ex_lines = existing.splitlines()
    in_lines = incoming.splitlines()

    table = Table(
        title=f"Comparison: {filename}",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta"
    )
    table.add_column("#", width=4, justify="right", style="dim")
    table.add_column("Existing", width=50, style="red")
    table.add_column("Incoming", width=50, style="green")

    max_lines = max(len(ex_lines), len(in_lines))

    for i in range(max_lines):
        ex_line = ex_lines[i] if i < len(ex_lines) else ""
        in_line = in_lines[i] if i < len(in_lines) else ""

        # Highlight differences
        if ex_line != in_line:
            ex_style = "red bold"
            in_style = "green bold"
        else:
            ex_style = "dim"
            in_style = "dim"

        table.add_row(
            str(i + 1),
            f"[{ex_style}]{ex_line[:47]}{'...' if len(ex_line) > 47 else ''}[/{ex_style}]",
            f"[{in_style}]{in_line[:47]}{'...' if len(in_line) > 47 else ''}[/{in_style}]"
        )

    console.print(table)


def show_comparison_diff(comparison: AgentComparison) -> None:
    """Show unified diff for an AgentComparison.

    Args:
        comparison: AgentComparison object with agent metadata and content
    """
    # Display header panel
    console.print(Panel(
        f"[bold]{comparison.agent.name}[/bold] ({comparison.status})\n"
        f"Local: {comparison.local_path or 'N/A'}\n"
        f"Archive: {comparison.agent.name}.md\n"
        f"Changes: {comparison.diff_summary or 'N/A'}",
        title="Agent Comparison",
        border_style="cyan"
    ))

    # Show unified diff
    if comparison.local_content and comparison.archive_content:
        show_unified_diff(
            existing=comparison.local_content,
            incoming=comparison.archive_content,
            filename=f"{comparison.agent.name}.md"
        )
    elif comparison.status == "IDENTICAL":
        console.print("[green]Files are identical[/green]")
    else:
        console.print("[yellow]No diff available (NEW agent)[/yellow]")


def show_comparison_side_by_side(comparison: AgentComparison) -> None:
    """Show side-by-side diff for an AgentComparison.

    Args:
        comparison: AgentComparison object with agent metadata and content
    """
    # Display header panel
    console.print(Panel(
        f"[bold]{comparison.agent.name}[/bold] ({comparison.status})\n"
        f"Local: {comparison.local_path or 'N/A'}\n"
        f"Archive: {comparison.agent.name}.md\n"
        f"Changes: {comparison.diff_summary or 'N/A'}",
        title="Agent Comparison",
        border_style="cyan"
    ))

    # Show side-by-side diff
    if comparison.local_content and comparison.archive_content:
        show_side_by_side(
            existing=comparison.local_content,
            incoming=comparison.archive_content,
            filename=f"{comparison.agent.name}.md"
        )
    elif comparison.status == "IDENTICAL":
        console.print("[green]Files are identical[/green]")
    else:
        console.print("[yellow]No diff available (NEW agent)[/yellow]")


def show_diff_summary(comparison: AgentComparison) -> None:
    """Show quick diff summary for an AgentComparison.

    Args:
        comparison: AgentComparison object with agent metadata and content
    """
    console.print(Panel(
        f"[bold cyan]{comparison.agent.name}[/bold cyan]\n"
        f"Status: {comparison.status}\n"
        f"Type: {comparison.agent.agent_type}\n"
        f"Local: {comparison.local_path or 'N/A'}\n"
        f"Changes: {comparison.diff_summary or 'N/A'}",
        title=f"Agent: {comparison.agent.name}",
        border_style="cyan"
    ))


def get_duplicate_name(target_dir: Path, base_name: str) -> Path:
    """Find next available numeric suffix for duplicate file.

    Examples:
        agent.md -> agent_1.md
        agent_1.md -> agent_2.md
    """
    stem = Path(base_name).stem
    suffix = Path(base_name).suffix
    counter = 1

    while (target_dir / f"{stem}_{counter}{suffix}").exists():
        counter += 1

    return target_dir / f"{stem}_{counter}{suffix}"


def get_diff_blocks(existing: str, incoming: str, context_lines: int = 2) -> List[DiffBlock]:
    """Parse diff into blocks for selective merging."""
    ex_lines = existing.splitlines()
    in_lines = incoming.splitlines()

    matcher = difflib.SequenceMatcher(None, ex_lines, in_lines)
    blocks = []
    block_num = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            continue

        block_num += 1

        # Get context lines
        context_before = ex_lines[max(0, i1 - context_lines):i1]
        context_after = ex_lines[i2:min(len(ex_lines), i2 + context_lines)]

        blocks.append(DiffBlock(
            block_num=block_num,
            start_line=i1 + 1,
            end_line=i2,
            existing_lines=ex_lines[i1:i2],
            incoming_lines=in_lines[j1:j2],
            context_before=context_before,
            context_after=context_after
        ))

    return blocks


def display_diff_block(block: DiffBlock) -> None:
    """Display a single diff block with context."""
    console.print()
    console.print(Panel(
        f"[bold]Block {block.block_num}[/bold] - Lines {block.start_line}-{block.end_line}",
        border_style="cyan"
    ))

    # Show context before
    if block.context_before:
        for line in block.context_before:
            console.print(f"  [dim]{line}[/dim]")

    # Show existing (red)
    console.print("\n[bold red]─── EXISTING ───[/bold red]")
    for line in block.existing_lines:
        console.print(f"[red]- {line}[/red]")

    # Show incoming (green)
    console.print("\n[bold green]─── INCOMING ───[/bold green]")
    for line in block.incoming_lines:
        console.print(f"[green]+ {line}[/green]")

    # Show context after
    if block.context_after:
        console.print()
        for line in block.context_after:
            console.print(f"  [dim]{line}[/dim]")


def merge_section(section_name: str, existing: str, incoming: str) -> str:
    """Interactive merge for a single section (YAML or body)."""
    console.print(Panel(
        f"[bold cyan]Section: {section_name}[/bold cyan]",
        border_style="cyan"
    ))

    # Show diff
    show_unified_diff(existing, incoming, section_name)

    console.print("\n[bold]Options:[/bold]")
    console.print("  [cyan]k[/cyan] - Keep existing")
    console.print("  [cyan]r[/cyan] - Replace with incoming")
    console.print("  [cyan]b[/cyan] - Keep both (concatenate)")
    console.print("  [cyan]l[/cyan] - Line-by-line selection")

    choice = Prompt.ask(
        "\n[bold cyan]Choice[/bold cyan]",
        choices=["k", "r", "b", "l"],
        default="k"
    )

    if choice == "k":
        return existing
    elif choice == "r":
        return incoming
    elif choice == "b":
        return f"{existing}\n\n# --- Merged from incoming ---\n{incoming}"
    elif choice == "l":
        return line_by_line_merge(existing, incoming)

    return existing


def line_by_line_merge(existing: str, incoming: str) -> str:
    """Interactive line-by-line merge."""
    blocks = get_diff_blocks(existing, incoming)

    if not blocks:
        console.print("[green]No differences found[/green]")
        return existing

    console.print(f"\n[bold]Found {len(blocks)} differing block(s)[/bold]")

    result_lines = existing.splitlines()
    offset = 0  # Track line offset due to insertions/deletions

    for block in blocks:
        display_diff_block(block)

        console.print("\n[bold]Options:[/bold]")
        console.print("  [cyan]k[/cyan] - Keep existing lines")
        console.print("  [cyan]r[/cyan] - Replace with incoming lines")
        console.print("  [cyan]b[/cyan] - Keep both")
        console.print("  [cyan]s[/cyan] - Skip (keep existing)")

        choice = Prompt.ask(
            "[bold cyan]Choice[/bold cyan]",
            choices=["k", "r", "b", "s"],
            default="k"
        )

        start_idx = block.start_line - 1 + offset
        end_idx = block.end_line + offset

        if choice == "k" or choice == "s":
            # Keep existing - no change needed
            pass
        elif choice == "r":
            # Replace with incoming
            result_lines[start_idx:end_idx] = block.incoming_lines
            offset += len(block.incoming_lines) - len(block.existing_lines)
        elif choice == "b":
            # Keep both
            combined = block.existing_lines + ["# --- incoming ---"] + block.incoming_lines
            result_lines[start_idx:end_idx] = combined
            offset += len(combined) - len(block.existing_lines)

    return '\n'.join(result_lines)


def interactive_merge(existing_path: Path, incoming_path: Path) -> str:
    """Hybrid merge: section-aware with line-by-line fallback.

    For agent files, tries to parse YAML frontmatter and markdown body
    separately. Falls back to line-by-line for non-standard formats.
    """
    existing = existing_path.read_text(encoding='utf-8')
    incoming = incoming_path.read_text(encoding='utf-8')

    # Try section-aware first
    ex_yaml, ex_body = parse_agent_sections(existing)
    in_yaml, in_body = parse_agent_sections(incoming)

    # If both have YAML frontmatter, do section-aware merge
    if ex_yaml and in_yaml:
        console.print(Panel(
            "[bold cyan]Section-Aware Merge Mode[/bold cyan]\n"
            "Agent file detected with YAML frontmatter",
            border_style="cyan"
        ))

        result_yaml = ex_yaml
        result_body = ex_body

        # Merge YAML section if different
        if ex_yaml != in_yaml:
            result_yaml = merge_section("YAML Frontmatter", ex_yaml, in_yaml)
        else:
            console.print("[dim]YAML frontmatter: identical[/dim]")

        # Merge body section if different
        if ex_body != in_body:
            result_body = merge_section("Markdown Body", ex_body, in_body)
        else:
            console.print("[dim]Markdown body: identical[/dim]")

        return f"---\n{result_yaml}\n---\n{result_body}"

    # Fallback to line-by-line
    console.print(Panel(
        "[bold yellow]Line-by-Line Merge Mode[/bold yellow]\n"
        "No YAML frontmatter detected or format mismatch",
        border_style="yellow"
    ))

    return line_by_line_merge(existing, incoming)


def resolve_conflict(
    existing_path: Path,
    incoming_path: Path,
    target_dir: Path,
    mode: ConflictMode = ConflictMode.DIFF
) -> Optional[Path]:
    """Main conflict resolution entry point.

    Args:
        existing_path: Path to existing agent file
        incoming_path: Path to incoming agent file (from archive)
        target_dir: Directory to save resolved file
        mode: Conflict resolution mode

    Returns:
        Path to the resolved file, or None if skipped
    """
    filename = existing_path.name

    console.print()
    console.print(Panel(
        f"[bold yellow]Conflict Detected[/bold yellow]\n"
        f"File: [cyan]{filename}[/cyan]",
        border_style="yellow"
    ))

    if mode == ConflictMode.OVERWRITE:
        # Overwrite without prompting
        shutil.copy2(incoming_path, existing_path)
        console.print(f"[green]Overwritten: {filename}[/green]")
        return existing_path

    elif mode == ConflictMode.KEEP:
        # Keep existing without prompting
        console.print(f"[dim]Kept existing: {filename}[/dim]")
        return existing_path

    elif mode == ConflictMode.DUPLICATE:
        # Save as duplicate with numeric suffix
        dup_path = get_duplicate_name(target_dir, filename)
        shutil.copy2(incoming_path, dup_path)
        console.print(f"[green]Saved as duplicate: {dup_path.name}[/green]")
        return dup_path

    elif mode == ConflictMode.DIFF:
        # Interactive diff/merge
        return resolve_conflict_interactive(existing_path, incoming_path, target_dir)

    return None


def resolve_conflict_interactive(
    existing_path: Path,
    incoming_path: Path,
    target_dir: Path
) -> Optional[Path]:
    """Interactive conflict resolution with diff display.

    Returns:
        Path to the resolved file, or None if skipped
    """
    filename = existing_path.name
    existing_content = existing_path.read_text(encoding='utf-8')
    incoming_content = incoming_path.read_text(encoding='utf-8')

    while True:
        console.print("\n[bold]Options:[/bold]")
        console.print("  [cyan]o[/cyan] - Overwrite with incoming")
        console.print("  [cyan]k[/cyan] - Keep existing (skip)")
        console.print("  [cyan]d[/cyan] - Duplicate (save as {}_1.md)".format(existing_path.stem))
        console.print("  [cyan]v[/cyan] - View unified diff")
        console.print("  [cyan]s[/cyan] - View side-by-side")
        console.print("  [cyan]m[/cyan] - Interactive merge")

        choice = Prompt.ask(
            "\n[bold cyan]Choice[/bold cyan]",
            choices=["o", "k", "d", "v", "s", "m"],
            default="v"
        )

        if choice == "o":
            shutil.copy2(incoming_path, existing_path)
            console.print(f"[green]Overwritten: {filename}[/green]")
            return existing_path

        elif choice == "k":
            console.print(f"[dim]Kept existing: {filename}[/dim]")
            return existing_path

        elif choice == "d":
            dup_path = get_duplicate_name(target_dir, filename)
            shutil.copy2(incoming_path, dup_path)
            console.print(f"[green]Saved as duplicate: {dup_path.name}[/green]")
            return dup_path

        elif choice == "v":
            show_unified_diff(existing_content, incoming_content, filename)
            continue

        elif choice == "s":
            show_side_by_side(existing_content, incoming_content, filename)
            continue

        elif choice == "m":
            merged_content = interactive_merge(existing_path, incoming_path)

            # Preview merged result
            console.print("\n[bold]Merged result preview:[/bold]")
            console.print(Panel(merged_content[:500] + ("..." if len(merged_content) > 500 else "")))

            if Confirm.ask("Save merged result?", default=True):
                existing_path.write_text(merged_content, encoding='utf-8')
                console.print(f"[green]Saved merged: {filename}[/green]")
                return existing_path
            else:
                continue

    return None
