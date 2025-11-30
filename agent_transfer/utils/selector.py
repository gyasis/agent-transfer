"""Interactive agent selector UI."""

from typing import List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich import box

from ..models import Agent

console = Console()


def display_agents_table(agents: List[Agent], selected: List[int]) -> Table:
    """Create a rich table displaying agents."""
    table = Table(
        title="Available Claude Code Agents",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta"
    )
    
    table.add_column("✓", width=3, justify="center")
    table.add_column("#", width=4, justify="right")
    table.add_column("Name", width=25, style="cyan")
    table.add_column("Description", width=50)
    table.add_column("Type", width=8, justify="center")
    table.add_column("Tools", width=20)
    
    for idx, agent in enumerate(agents):
        is_selected = "✓" if idx in selected else " "
        type_style = "green" if agent.agent_type == "user" else "blue"
        type_text = "User" if agent.agent_type == "user" else "Project"
        
        tools_str = ", ".join(agent.tools[:3])
        if len(agent.tools) > 3:
            tools_str += f" (+{len(agent.tools) - 3})"
        if not tools_str:
            tools_str = "N/A"
        
        # Truncate description if too long
        desc = agent.description
        if len(desc) > 47:
            desc = desc[:44] + "..."
        
        table.add_row(
            is_selected,
            str(idx + 1),
            agent.name,
            desc,
            f"[{type_style}]{type_text}[/{type_style}]",
            tools_str
        )
    
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

