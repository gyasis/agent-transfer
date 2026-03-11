"""Deep discovery of Claude Code installation and agent directories."""

from pathlib import Path
from typing import List, Optional, Tuple
from rich.console import Console
from rich.panel import Panel

console = Console()


def find_claude_code_executable() -> Optional[Path]:
    """Find Claude Code executable using multiple strategies.

    Delegates to Pathfinder for centralized executable discovery.
    """
    from .pathfinder import get_pathfinder

    pf = get_pathfinder()
    return pf.find_executable("claude-code")


def find_claude_code_config_dir() -> Optional[Path]:
    """Find Claude Code configuration directory.

    Delegates to Pathfinder for centralized config directory resolution.
    """
    from .pathfinder import get_pathfinder

    pf = get_pathfinder()
    return pf.config_dir("claude-code")


def find_agent_directories() -> List[Tuple[Path, str]]:
    """
    Find all agent directories with their types.
    Returns list of (directory_path, type) tuples.

    Delegates to Pathfinder for centralized directory resolution.
    """
    from .pathfinder import get_pathfinder

    pf = get_pathfinder()
    return pf.all_agents_dirs("claude-code")


def discover_claude_code_info() -> dict:
    """Discover comprehensive Claude Code installation information."""
    info = {
        "executable": None,
        "executable_path": None,
        "config_dir": None,
        "agent_directories": [],
        "installation_type": "unknown",
    }
    
    # Find executable
    claude_exe = find_claude_code_executable()
    if claude_exe:
        info["executable"] = str(claude_exe)
        info["executable_path"] = str(claude_exe.resolve())
        
        # Determine installation type
        exe_str = str(claude_exe)
        if "node_modules" in exe_str or ".npm" in exe_str:
            info["installation_type"] = "npm-global"
        elif "venv" in exe_str or ".venv" in exe_str or "env" in exe_str:
            info["installation_type"] = "virtualenv"
        elif "conda" in exe_str or "anaconda" in exe_str or "miniconda" in exe_str:
            info["installation_type"] = "conda"
        elif exe_str.startswith("/usr"):
            info["installation_type"] = "system"
        elif exe_str.startswith(str(Path.home())):
            info["installation_type"] = "user"
        else:
            info["installation_type"] = "custom"
    
    # Find config directory
    config_dir = find_claude_code_config_dir()
    if config_dir:
        info["config_dir"] = str(config_dir)
    
    # Find agent directories
    agent_dirs = find_agent_directories()
    info["agent_directories"] = [
        {"path": str(path), "type": agent_type}
        for path, agent_type in agent_dirs
    ]
    
    return info


def display_discovery_info(info: dict):
    """Display discovered Claude Code information in a nice format."""
    from rich.table import Table
    from rich import box
    
    console.print()
    console.print(Panel.fit(
        "[bold cyan]Claude Code Discovery Results[/bold cyan]",
        border_style="cyan"
    ))
    console.print()
    
    # Installation info
    table = Table(title="Installation Information", box=box.ROUNDED, show_header=True)
    table.add_column("Property", width=20, style="cyan")
    table.add_column("Value", width=60)
    
    if info["executable"]:
        table.add_row("Executable", info["executable"])
        table.add_row("Full Path", info["executable_path"])
        table.add_row("Installation Type", info["installation_type"])
    else:
        table.add_row("Executable", "[red]Not found[/red]")
        table.add_row("Installation Type", "[yellow]Unknown[/yellow]")
    
    if info["config_dir"]:
        table.add_row("Config Directory", info["config_dir"])
    else:
        table.add_row("Config Directory", "[yellow]Using default: ~/.claude[/yellow]")
    
    console.print(table)
    console.print()
    
    # Agent directories
    if info["agent_directories"]:
        agent_table = Table(title="Agent Directories", box=box.ROUNDED, show_header=True)
        agent_table.add_column("Type", width=10, justify="center")
        agent_table.add_column("Path", width=70)
        agent_table.add_column("Agents", width=8, justify="right")
        
        for agent_dir_info in info["agent_directories"]:
            agent_path = Path(agent_dir_info["path"])
            agent_type = agent_dir_info["type"]
            agent_count = len(list(agent_path.glob("*.md"))) if agent_path.exists() else 0
            
            type_style = "green" if agent_type == "user" else "blue"
            type_text = f"[{type_style}]{agent_type.title()}[/{type_style}]"
            
            agent_table.add_row(
                type_text,
                str(agent_path),
                str(agent_count)
            )
        
        console.print(agent_table)
    else:
        console.print("[yellow]No agent directories found[/yellow]")
        console.print("\n[dim]Run with --discover to see search locations[/dim]")
    
    console.print()

