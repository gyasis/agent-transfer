"""Interactive agent selector UI."""

from typing import List, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich import box

from ..models import Agent, AgentComparison
from .conflict_resolver import show_unified_diff, show_side_by_side

console = Console()


def display_agents_table(
    agents: List[Agent],
    selected: List[int],
    comparisons: Optional[List[AgentComparison]] = None
) -> Table:
    """Create a rich table displaying agents.

    Args:
        agents: List of agents to display
        selected: List of selected agent indices
        comparisons: Optional list of AgentComparison objects for import mode
    """
    title = "Import Preview" if comparisons else "Available Claude Code Agents"

    table = Table(
        title=title,
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta"
    )

    table.add_column("✓", width=3, justify="center")
    table.add_column("#", width=4, justify="right")
    table.add_column("Name", width=25, style="cyan")
    table.add_column("Description", width=40)

    # Add Status and Diff columns for import mode
    if comparisons:
        table.add_column("Status", width=10, justify="center")
        table.add_column("Diff", width=10, justify="center")

    table.add_column("Type", width=8, justify="center")

    # Only show tools in export mode
    if not comparisons:
        table.add_column("Tools", width=20)

    for idx, agent in enumerate(agents):
        is_selected = "✓" if idx in selected else " "
        type_style = "green" if agent.agent_type == "user" else "blue"
        type_text = "User" if agent.agent_type == "user" else "Project"

        # Truncate description if too long
        desc_width = 37 if comparisons else 47
        desc = agent.description
        if len(desc) > desc_width:
            desc = desc[:desc_width - 3] + "..."

        row_data = [
            is_selected,
            str(idx + 1),
            agent.name,
            desc,
        ]

        # Add status and diff for import mode
        if comparisons:
            comparison = comparisons[idx]
            status = comparison.status

            # Style based on status
            if status == "NEW":
                status_display = "[bold green]NEW[/bold green]"
                diff_display = ""
            elif status == "CHANGED":
                status_display = "[bold yellow]CHANGED[/bold yellow]"
                diff_display = comparison.diff_summary or ""
            else:  # IDENTICAL
                status_display = "[dim]IDENTICAL[/dim]"
                diff_display = ""
                # Make entire row dim for identical agents
                row_data = [f"[dim]{val}[/dim]" for val in row_data]

            row_data.append(status_display)
            row_data.append(diff_display)

        row_data.append(f"[{type_style}]{type_text}[/{type_style}]")

        # Add tools column for export mode
        if not comparisons:
            tools = agent.tools or []  # Handle None
            tools_str = ", ".join(tools[:3])
            if len(tools) > 3:
                tools_str += f" (+{len(tools) - 3})"
            if not tools_str:
                tools_str = "N/A"
            row_data.append(tools_str)

        table.add_row(*row_data)

    return table


def show_agent_details(agent: Agent):
    """Display detailed information about an agent."""
    console.print()
    console.print(Panel.fit(
        f"[bold cyan]{agent.name}[/bold cyan]\n\n"
        f"[bold]Description:[/bold] {agent.description}\n"
        f"[bold]Type:[/bold] {'User-level' if agent.agent_type == 'user' else 'Project-level'}\n"
        f"[bold]File:[/bold] {agent.file_path}\n"
        f"[bold]Tools:[/bold] {', '.join(agent.tools) if agent.tools else 'None specified'}\n"
        f"[bold]Permission Mode:[/bold] {agent.permission_mode or 'Not specified'}\n"
        f"[bold]Model:[/bold] {agent.model or 'Default'}",
        title="Agent Details",
        border_style="cyan"
    ))


def interactive_select_agents(agents: List[Agent]) -> List[Agent]:
    """Interactive agent selection with Rich UI."""
    if not agents:
        console.print("[red]No agents found![/red]")
        return []
    
    selected_indices = []
    
    while True:
        console.clear()
        console.print()
        
        # Show selection status
        status_text = f"[green]{len(selected_indices)}[/green] agent(s) selected"
        if len(selected_indices) == len(agents):
            status_text += " [bold](All)[/bold]"
        console.print(Panel(status_text, border_style="green"))
        console.print()
        
        # Display agents table
        table = display_agents_table(agents, selected_indices)
        console.print(table)
        console.print()
        
        # Show menu options
        console.print("[bold]Options:[/bold]")
        console.print("  [cyan]1-N[/cyan]  - Toggle agent by number")
        console.print("  [cyan]a[/cyan]    - Select all agents")
        console.print("  [cyan]d[/cyan]    - Deselect all agents")
        console.print("  [cyan]i[/cyan]    - Show details for agent")
        console.print("  [cyan]enter[/cyan] - Confirm selection")
        console.print("  [cyan]q[/cyan]    - Quit without selecting")
        console.print()
        
        choice = Prompt.ask(
            "[bold cyan]Your choice[/bold cyan]",
            default=""
        ).strip().lower()
        
        if choice == "" or choice == "enter":
            if selected_indices:
                return [agents[i] for i in selected_indices]
            else:
                if Confirm.ask("[yellow]No agents selected. Continue anyway?[/yellow]"):
                    return []
                continue
        
        if choice == "q":
            if Confirm.ask("[yellow]Quit without selecting any agents?[/yellow]"):
                return []
            continue
        
        if choice == "a":
            selected_indices = list(range(len(agents)))
            continue
        
        if choice == "d":
            selected_indices = []
            continue
        
        if choice == "i":
            try:
                num = int(Prompt.ask("Enter agent number to view details", default="1"))
                if 1 <= num <= len(agents):
                    show_agent_details(agents[num - 1])
                    Prompt.ask("\n[dim]Press Enter to continue...[/dim]", default="")
                else:
                    console.print("[red]Invalid agent number[/red]")
                    Prompt.ask("\n[dim]Press Enter to continue...[/dim]", default="")
            except ValueError:
                console.print("[red]Invalid input[/red]")
                Prompt.ask("\n[dim]Press Enter to continue...[/dim]", default="")
            continue
        
        # Try to parse as number
        try:
            num = int(choice)
            if 1 <= num <= len(agents):
                idx = num - 1
                if idx in selected_indices:
                    selected_indices.remove(idx)
                else:
                    selected_indices.append(idx)
            else:
                console.print(f"[red]Invalid agent number. Must be 1-{len(agents)}[/red]")
                Prompt.ask("\n[dim]Press Enter to continue...[/dim]", default="")
        except ValueError:
            console.print("[red]Invalid choice[/red]")
            Prompt.ask("\n[dim]Press Enter to continue...[/dim]", default="")


def interactive_select_import_agents(comparisons: List[AgentComparison]) -> List[AgentComparison]:
    """Interactive agent selection for import with status highlighting and diff viewing.

    Args:
        comparisons: List of AgentComparison objects

    Returns:
        List of selected AgentComparison objects
    """
    if not comparisons:
        console.print("[red]No agents found in archive![/red]")
        return []

    # Extract agents for display
    agents = [comp.agent for comp in comparisons]

    # Pre-select NEW + CHANGED agents by default (CRITICAL!)
    selected_indices = [
        i for i, comp in enumerate(comparisons)
        if comp.status in ["NEW", "CHANGED"]
    ]

    # Filter mode: ALL, NEW, CHANGED, IDENTICAL
    filter_mode = "ALL"

    while True:
        console.clear()
        console.print()

        # Show selection status with filter mode
        status_parts = [f"[green]{len(selected_indices)}[/green] agent(s) selected"]
        if filter_mode != "ALL":
            status_parts.append(f"Filter: [cyan]{filter_mode}[/cyan]")

        status_text = " | ".join(status_parts)
        console.print(Panel(status_text, border_style="green"))
        console.print()

        # Apply filter
        if filter_mode == "ALL":
            display_comparisons = comparisons
            display_agents = agents
            idx_mapping = list(range(len(comparisons)))
        else:
            filtered = [
                (i, comp) for i, comp in enumerate(comparisons)
                if comp.status == filter_mode
            ]
            idx_mapping = [i for i, _ in filtered]
            display_comparisons = [comp for _, comp in filtered]
            display_agents = [comp.agent for comp in display_comparisons]

        if not display_comparisons:
            console.print(f"[yellow]No agents with status {filter_mode}[/yellow]")
            Prompt.ask("\n[dim]Press Enter to continue...[/dim]", default="")
            filter_mode = "ALL"
            continue

        # Map selected indices for display
        display_selected = [
            display_comparisons.index(comparisons[i])
            for i in selected_indices
            if i in idx_mapping
        ]

        # Display agents table with status and diff
        table = display_agents_table(display_agents, display_selected, display_comparisons)
        console.print(table)
        console.print()

        # Show menu options
        console.print("[bold]Options:[/bold]")
        console.print("  [cyan]1-N[/cyan]   - Toggle agent by number")
        console.print("  [cyan]a[/cyan]     - Select all (in current filter)")
        console.print("  [cyan]d[/cyan]     - Deselect all")
        console.print("  [cyan]n[/cyan]     - Select NEW only")
        console.print("  [cyan]c[/cyan]     - Select CHANGED only")
        console.print("  [cyan]f[/cyan]     - Filter view (cycle: ALL → NEW → CHANGED → IDENTICAL)")
        console.print("  [cyan]v[/cyan]     - View unified diff for agent")
        console.print("  [cyan]s[/cyan]     - View side-by-side for agent")
        console.print("  [cyan]i[/cyan]     - Show details for agent")
        console.print("  [cyan]enter[/cyan] - Confirm selection")
        console.print("  [cyan]q[/cyan]     - Quit without selecting")
        console.print()

        choice = Prompt.ask(
            "[bold cyan]Your choice[/bold cyan]",
            default=""
        ).strip().lower()

        if choice == "" or choice == "enter":
            if selected_indices:
                return [comparisons[i] for i in selected_indices]
            else:
                if Confirm.ask("[yellow]No agents selected. Continue anyway?[/yellow]"):
                    return []
                continue

        if choice == "q":
            if Confirm.ask("[yellow]Quit without selecting any agents?[/yellow]"):
                return []
            continue

        if choice == "a":
            # Select all in current filter
            selected_indices = list(set(selected_indices + idx_mapping))
            continue

        if choice == "d":
            selected_indices = []
            continue

        if choice == "n":
            # Select NEW only
            selected_indices = [
                i for i, comp in enumerate(comparisons)
                if comp.status == "NEW"
            ]
            continue

        if choice == "c":
            # Select CHANGED only
            selected_indices = [
                i for i, comp in enumerate(comparisons)
                if comp.status == "CHANGED"
            ]
            continue

        if choice == "f":
            # Cycle filter mode
            filter_cycle = ["ALL", "NEW", "CHANGED", "IDENTICAL"]
            current_idx = filter_cycle.index(filter_mode)
            filter_mode = filter_cycle[(current_idx + 1) % len(filter_cycle)]
            continue

        if choice == "v":
            # View unified diff
            try:
                num = int(Prompt.ask("Enter agent number to view diff", default="1"))
                if 1 <= num <= len(display_comparisons):
                    comp = display_comparisons[num - 1]

                    if comp.status == "IDENTICAL":
                        console.print("[green]This agent is identical to the local version[/green]")
                    elif comp.status == "NEW":
                        console.print("[yellow]This is a new agent (no local version to compare)[/yellow]")
                    else:
                        show_unified_diff(
                            comp.local_content or "",
                            comp.archive_content,
                            comp.agent.name
                        )

                    Prompt.ask("\n[dim]Press Enter to continue...[/dim]", default="")
                else:
                    console.print("[red]Invalid agent number[/red]")
                    Prompt.ask("\n[dim]Press Enter to continue...[/dim]", default="")
            except ValueError:
                console.print("[red]Invalid input[/red]")
                Prompt.ask("\n[dim]Press Enter to continue...[/dim]", default="")
            continue

        if choice == "s":
            # View side-by-side
            try:
                num = int(Prompt.ask("Enter agent number to view side-by-side", default="1"))
                if 1 <= num <= len(display_comparisons):
                    comp = display_comparisons[num - 1]

                    if comp.status == "IDENTICAL":
                        console.print("[green]This agent is identical to the local version[/green]")
                    elif comp.status == "NEW":
                        console.print("[yellow]This is a new agent (no local version to compare)[/yellow]")
                    else:
                        show_side_by_side(
                            comp.local_content or "",
                            comp.archive_content,
                            comp.agent.name
                        )

                    Prompt.ask("\n[dim]Press Enter to continue...[/dim]", default="")
                else:
                    console.print("[red]Invalid agent number[/red]")
                    Prompt.ask("\n[dim]Press Enter to continue...[/dim]", default="")
            except ValueError:
                console.print("[red]Invalid input[/red]")
                Prompt.ask("\n[dim]Press Enter to continue...[/dim]", default="")
            continue

        if choice == "i":
            # Show agent details
            try:
                num = int(Prompt.ask("Enter agent number to view details", default="1"))
                if 1 <= num <= len(display_comparisons):
                    comp = display_comparisons[num - 1]

                    # Show agent details with status info
                    console.print()
                    console.print(Panel.fit(
                        f"[bold cyan]{comp.agent.name}[/bold cyan]\n\n"
                        f"[bold]Description:[/bold] {comp.agent.description}\n"
                        f"[bold]Type:[/bold] {'User-level' if comp.agent.agent_type == 'user' else 'Project-level'}\n"
                        f"[bold]Status:[/bold] {comp.status}\n"
                        f"[bold]File:[/bold] {comp.agent.file_path}\n"
                        f"[bold]Tools:[/bold] {', '.join(comp.agent.tools or []) or 'None specified'}\n"
                        f"[bold]Permission Mode:[/bold] {comp.agent.permission_mode or 'Not specified'}\n"
                        f"[bold]Model:[/bold] {comp.agent.model or 'Default'}\n"
                        f"[bold]Local Path:[/bold] {comp.local_path or 'N/A (new agent)'}\n"
                        f"[bold]Diff:[/bold] {comp.diff_summary or 'No changes'}",
                        title="Agent Details",
                        border_style="cyan"
                    ))
                    Prompt.ask("\n[dim]Press Enter to continue...[/dim]", default="")
                else:
                    console.print("[red]Invalid agent number[/red]")
                    Prompt.ask("\n[dim]Press Enter to continue...[/dim]", default="")
            except ValueError:
                console.print("[red]Invalid input[/red]")
                Prompt.ask("\n[dim]Press Enter to continue...[/dim]", default="")
            continue

        # Try to parse as number
        try:
            num = int(choice)
            if 1 <= num <= len(display_comparisons):
                # Map display index to actual index
                actual_idx = idx_mapping[num - 1]

                if actual_idx in selected_indices:
                    selected_indices.remove(actual_idx)
                else:
                    selected_indices.append(actual_idx)
            else:
                console.print(f"[red]Invalid agent number. Must be 1-{len(display_comparisons)}[/red]")
                Prompt.ask("\n[dim]Press Enter to continue...[/dim]", default="")
        except ValueError:
            console.print("[red]Invalid choice[/red]")
            Prompt.ask("\n[dim]Press Enter to continue...[/dim]", default="")
