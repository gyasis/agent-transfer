#!/usr/bin/env python3
"""
Interactive Agent Selector for Claude Code Agent Transfer
Uses Rich library for beautiful terminal UI
"""

import os
import sys
import yaml
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.markdown import Markdown
    from rich.text import Text
    from rich import box
except ImportError:
    print("Error: rich library not installed. Install with: pip install rich pyyaml")
    sys.exit(1)

console = Console()

@dataclass
class Agent:
    """Represents a Claude Code agent."""
    name: str
    description: str
    file_path: str
    agent_type: str  # 'user' or 'project'
    tools: List[str] = None
    permission_mode: str = None
    model: str = None
    full_content: str = None

    def __post_init__(self):
        if self.tools is None:
            self.tools = []

def parse_agent_file(file_path: Path) -> Optional[Agent]:
    """Parse an agent markdown file and extract metadata."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract YAML frontmatter
        yaml_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', content, re.DOTALL)
        if not yaml_match:
            # Try without frontmatter
            return Agent(
                name=file_path.stem,
                description="No description available",
                file_path=str(file_path),
                agent_type="unknown",
                full_content=content
            )
        
        yaml_content = yaml_match.group(1)
        body_content = yaml_match.group(2)
        
        try:
            metadata = yaml.safe_load(yaml_content) or {}
        except yaml.YAMLError:
            metadata = {}
        
        # Extract description from body if not in frontmatter
        description = metadata.get('description', '')
        if not description:
            # Try to extract first paragraph from body
            first_line = body_content.strip().split('\n')[0]
            if first_line and len(first_line) < 200:
                description = first_line
            else:
                description = "No description available"
        
        # Parse tools
        tools_str = metadata.get('tools', '')
        if isinstance(tools_str, str):
            tools = [t.strip() for t in tools_str.split(',') if t.strip()]
        else:
            tools = tools_str if isinstance(tools_str, list) else []
        
        return Agent(
            name=metadata.get('name', file_path.stem),
            description=description,
            file_path=str(file_path),
            agent_type=metadata.get('agent_type', 'unknown'),
            tools=tools,
            permission_mode=metadata.get('permissionMode') or metadata.get('permission_mode'),
            model=metadata.get('model'),
            full_content=content
        )
    except Exception as e:
        console.print(f"[red]Error parsing {file_path}: {e}[/red]")
        return None

def find_all_agents() -> List[Agent]:
    """Find all agents in user-level and project-level directories."""
    agents = []
    
    # User-level agents
    user_agents_dir = Path.home() / '.claude' / 'agents'
    if user_agents_dir.exists():
        for agent_file in user_agents_dir.glob('*.md'):
            agent = parse_agent_file(agent_file)
            if agent:
                agent.agent_type = 'user'
                agents.append(agent)
    
    # Project-level agents (current directory and parents)
    current_dir = Path.cwd()
    for _ in range(4):  # Check up to 4 levels up
        project_agents_dir = current_dir / '.claude' / 'agents'
        if project_agents_dir.exists():
            for agent_file in project_agents_dir.glob('*.md'):
                agent = parse_agent_file(agent_file)
                if agent:
                    agent.agent_type = 'project'
                    agents.append(agent)
            break
        current_dir = current_dir.parent
    
    return agents

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

def main():
    """Main entry point."""
    console.print()
    console.print(Panel.fit(
        "[bold cyan]Claude Code Agent Selector[/bold cyan]\n\n"
        "Select agents to transfer",
        border_style="cyan"
    ))
    console.print()
    
    # Find all agents
    console.print("[dim]Scanning for agents...[/dim]")
    agents = find_all_agents()
    
    if not agents:
        console.print("[red]No agents found![/red]")
        console.print("\n[dim]Checked locations:[/dim]")
        console.print(f"  - {Path.home() / '.claude' / 'agents'}")
        console.print(f"  - {Path.cwd() / '.claude' / 'agents'}")
        sys.exit(1)
    
    console.print(f"[green]Found {len(agents)} agent(s)[/green]")
    console.print()
    
    # Interactive selection
    selected_agents = interactive_select_agents(agents)
    
    if not selected_agents:
        console.print("\n[yellow]No agents selected. Exiting.[/yellow]")
        sys.exit(0)
    
    # Output selected agent paths (one per line) for bash script to read
    for agent in selected_agents:
        print(agent.file_path)
    
    # Also output summary to stderr for user feedback
    console.print("\n[green]Selected agents:[/green]", file=sys.stderr)
    for agent in selected_agents:
        console.print(f"  [cyan]✓[/cyan] {agent.name} ({agent.agent_type})", file=sys.stderr)

if __name__ == "__main__":
    main()

