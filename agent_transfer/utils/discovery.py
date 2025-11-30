"""Deep discovery of Claude Code installation and agent directories."""

import os
import subprocess
import shutil
from pathlib import Path
from typing import List, Optional, Tuple
from rich.console import Console
from rich.panel import Panel

console = Console()


def find_claude_code_executable() -> Optional[Path]:
    """Find Claude Code executable using multiple strategies."""
    # Strategy 1: Check PATH
    claude_path = shutil.which("claude")
    if claude_path:
        return Path(claude_path)
    
    # Strategy 2: Check common npm global locations
    npm_global_paths = [
        Path.home() / ".npm-global" / "bin" / "claude",
        Path.home() / ".local" / "share" / "npm" / "bin" / "claude",
        Path("/usr/local/bin/claude"),
        Path("/usr/bin/claude"),
    ]
    
    for path in npm_global_paths:
        if path.exists() and path.is_file():
            return path
    
    # Strategy 3: Check npm global prefix
    try:
        result = subprocess.run(
            ["npm", "config", "get", "prefix"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            npm_prefix = Path(result.stdout.strip())
            claude_path = npm_prefix / "bin" / "claude"
            if claude_path.exists():
                return claude_path
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass
    
    # Strategy 4: Check nvm/node paths
    nvm_paths = [
        Path.home() / ".nvm" / "versions" / "node" / "*" / "bin" / "claude",
        Path.home() / ".config" / "nvm" / "versions" / "node" / "*" / "bin" / "claude",
    ]
    
    for pattern in nvm_paths:
        for path in Path(pattern.parent.parent).glob("*/bin/claude"):
            if path.exists():
                return path
    
    # Strategy 5: Check if running in a virtual environment
    venv_bin = os.environ.get("VIRTUAL_ENV")
    if venv_bin:
        venv_path = Path(venv_bin) / "bin" / "claude"
        if venv_path.exists():
            return venv_path
    
    # Strategy 6: Check conda environments
    conda_env = os.environ.get("CONDA_PREFIX")
    if conda_env:
        conda_path = Path(conda_env) / "bin" / "claude"
        if conda_path.exists():
            return conda_path
    
    # Strategy 7: Search common installation directories
    search_dirs = [
        Path.home() / ".local" / "bin",
        Path("/opt") / "claude-code" / "bin",
        Path("/usr/local/bin"),
    ]
    
    for search_dir in search_dirs:
        if search_dir.exists():
            claude_path = search_dir / "claude"
            if claude_path.exists():
                return claude_path
    
    return None


def find_claude_code_config_dir() -> Optional[Path]:
    """Find Claude Code configuration directory."""
    # Claude Code stores config in ~/.claude by default
    # But we should also check relative to installation
    
    # Standard location
    standard_config = Path.home() / ".claude"
    if standard_config.exists():
        return standard_config
    
    # Check if there's a config in the installation directory
    claude_exe = find_claude_code_executable()
    if claude_exe:
        # Claude Code might store config relative to executable
        possible_configs = [
            claude_exe.parent.parent / ".claude",
            claude_exe.parent / ".claude",
            Path.home() / ".config" / "claude-code",
            Path.home() / ".claude-code",
        ]
        
        for config_path in possible_configs:
            if config_path.exists():
                return config_path
    
    # Return standard location even if it doesn't exist yet
    return standard_config


def find_agent_directories() -> List[Tuple[Path, str]]:
    """
    Find all agent directories with their types.
    Returns list of (directory_path, type) tuples.
    """
    agent_dirs = []
    
    # Find Claude Code config directory
    config_dir = find_claude_code_config_dir()
    
    # User-level agents (in ~/.claude/agents)
    if config_dir:
        user_agents_dir = config_dir / "agents"
        if user_agents_dir.exists() and user_agents_dir.is_dir():
            agent_dirs.append((user_agents_dir, "user"))
    
    # Also check standard location
    standard_user_agents = Path.home() / ".claude" / "agents"
    if standard_user_agents.exists() and standard_user_agents.is_dir():
        if (standard_user_agents, "user") not in agent_dirs:
            agent_dirs.append((standard_user_agents, "user"))
    
    # Project-level agents (in .claude/agents relative to current/project directory)
    # But NOT the user-level ~/.claude/agents directory
    user_agents_path = Path.home() / ".claude" / "agents"
    current_dir = Path.cwd()
    for _ in range(5):  # Check up to 5 levels up
        project_agents_dir = current_dir / ".claude" / "agents"
        # Skip if this is the user-level agents directory
        if project_agents_dir.exists() and project_agents_dir.is_dir():
            if project_agents_dir.resolve() != user_agents_path.resolve():
                agent_dirs.append((project_agents_dir, "project"))
            break
        current_dir = current_dir.parent
        if current_dir == current_dir.parent:  # Reached root
            break
    
    # Check if Claude Code is installed in a virtual environment
    # and look for project agents relative to that
    claude_exe = find_claude_code_executable()
    if claude_exe:
        # If Claude is in a venv, check the venv's project directory
        venv_base = claude_exe.parent.parent
        if "venv" in str(venv_base) or "env" in str(venv_base) or ".venv" in str(venv_base):
            # Look for .claude in the venv's parent (likely the project root)
            venv_project = venv_base.parent
            venv_agents = venv_project / ".claude" / "agents"
            if venv_agents.exists() and venv_agents.is_dir():
                if (venv_agents, "project") not in agent_dirs:
                    agent_dirs.append((venv_agents, "project"))
    
    return agent_dirs


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
        console.print("\n[dim]Searched locations:[/dim]")
        console.print(f"  - {Path.home() / '.claude' / 'agents'}")
        console.print(f"  - {Path.cwd() / '.claude' / 'agents'}")
    
    console.print()

