"""Tool compatibility checker for agent imports.

Checks if tools referenced in agents exist on the target system.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()

# Built-in Claude Code tools that are always available
BUILTIN_TOOLS = {
    # File operations
    "Read", "Write", "Edit", "MultiEdit", "Glob", "Grep", "LS",
    # Shell operations
    "Bash", "BashOutput", "KillBash", "KillShell",
    # Web operations
    "WebFetch", "WebSearch",
    # Notebook operations
    "NotebookEdit",
    # Task management
    "TodoWrite", "Task",
    # MCP generic
    "ListMcpResourcesTool", "ReadMcpResourceTool",
    # Other
    "AskUserQuestion", "Skill", "SlashCommand",
}


@dataclass
class ToolCompatibility:
    """Compatibility report for an agent's tools."""
    agent_name: str
    agent_path: str
    all_tools: List[str] = field(default_factory=list)
    builtin_tools: List[str] = field(default_factory=list)
    mcp_tools: List[str] = field(default_factory=list)
    available_mcp_tools: List[str] = field(default_factory=list)
    missing_mcp_tools: List[str] = field(default_factory=list)
    unknown_tools: List[str] = field(default_factory=list)

    @property
    def is_compatible(self) -> bool:
        """Check if all tools are available."""
        return len(self.missing_mcp_tools) == 0 and len(self.unknown_tools) == 0

    @property
    def compatibility_score(self) -> float:
        """Calculate compatibility score (0-100)."""
        if not self.all_tools:
            return 100.0
        available = len(self.builtin_tools) + len(self.available_mcp_tools)
        return (available / len(self.all_tools)) * 100


def find_mcp_config() -> Optional[Path]:
    """Find Claude Code MCP configuration file."""
    # Check common locations for MCP config
    config_locations = [
        Path.home() / ".claude" / "mcp_servers.json",
        Path.home() / ".claude" / "mcp.json",
        Path.home() / ".config" / "claude" / "mcp_servers.json",
        Path(".claude") / "mcp_servers.json",
        Path("mcp_servers.json"),
    ]

    for path in config_locations:
        if path.exists():
            return path

    return None


def get_available_mcp_servers() -> Set[str]:
    """Get list of configured MCP server IDs."""
    config_path = find_mcp_config()
    if not config_path:
        return set()

    try:
        with open(config_path, 'r') as f:
            config = json.load(f)

        # MCP config can have different structures
        servers = set()

        # Format 1: {"servers": {"server-id": {...}}}
        if "servers" in config:
            servers.update(config["servers"].keys())

        # Format 2: {"mcpServers": {"server-id": {...}}}
        if "mcpServers" in config:
            servers.update(config["mcpServers"].keys())

        # Format 3: Direct dict of servers
        if not servers and isinstance(config, dict):
            # Check if keys look like server configs
            for key, val in config.items():
                if isinstance(val, dict) and ("command" in val or "url" in val):
                    servers.add(key)

        return servers
    except (json.JSONDecodeError, IOError):
        return set()


def parse_mcp_tool_name(tool: str) -> Tuple[Optional[str], str]:
    """Parse MCP tool name into (server_id, tool_name).

    MCP tools follow the pattern: mcp__{server_id}__{tool_name}

    Returns:
        Tuple of (server_id, tool_name) or (None, tool) if not MCP
    """
    if tool.startswith("mcp__"):
        parts = tool.split("__", 2)
        if len(parts) >= 3:
            return parts[1], parts[2]
        elif len(parts) == 2:
            return parts[1], ""
    return None, tool


def extract_tools_from_agent(agent_path: Path) -> List[str]:
    """Extract tools list from agent file."""
    try:
        content = agent_path.read_text(encoding='utf-8')

        # Find tools in YAML frontmatter
        match = re.search(r'^---\s*\n.*?^tools:\s*(.+?)$.*?\n---', content,
                         re.MULTILINE | re.DOTALL)
        if match:
            tools_line = match.group(1).strip()
            # Handle multi-line tools (YAML list or comma-separated)
            tools = [t.strip() for t in tools_line.split(',')]
            return [t for t in tools if t]

        return []
    except (IOError, UnicodeDecodeError):
        return []


def check_tool_compatibility(agent_path: Path) -> ToolCompatibility:
    """Check tool compatibility for a single agent.

    Args:
        agent_path: Path to agent markdown file

    Returns:
        ToolCompatibility report
    """
    agent_name = agent_path.stem
    tools = extract_tools_from_agent(agent_path)

    report = ToolCompatibility(
        agent_name=agent_name,
        agent_path=str(agent_path),
        all_tools=tools
    )

    # Get available MCP servers
    available_servers = get_available_mcp_servers()

    for tool in tools:
        server_id, tool_name = parse_mcp_tool_name(tool)

        if server_id is not None:
            # It's an MCP tool
            report.mcp_tools.append(tool)
            if server_id in available_servers:
                report.available_mcp_tools.append(tool)
            else:
                report.missing_mcp_tools.append(tool)
        elif tool in BUILTIN_TOOLS:
            report.builtin_tools.append(tool)
        else:
            # Unknown tool - might be custom or new
            report.unknown_tools.append(tool)

    return report


def check_all_agents(agent_dirs: List[Path]) -> List[ToolCompatibility]:
    """Check tool compatibility for all agents.

    Args:
        agent_dirs: List of directories containing agent files

    Returns:
        List of compatibility reports
    """
    reports = []

    for agent_dir in agent_dirs:
        if not agent_dir.exists():
            continue

        for agent_file in agent_dir.glob("*.md"):
            report = check_tool_compatibility(agent_file)
            reports.append(report)

    return reports


def display_compatibility_report(reports: List[ToolCompatibility]) -> None:
    """Display tool compatibility report using Rich."""
    if not reports:
        console.print("[yellow]No agents found to check.[/yellow]")
        return

    # Summary
    total = len(reports)
    compatible = sum(1 for r in reports if r.is_compatible)
    incompatible = total - compatible

    console.print(Panel(
        f"[bold]Tool Compatibility Check[/bold]\n\n"
        f"Total Agents: {total}\n"
        f"[green]Compatible: {compatible}[/green]\n"
        f"[red]Incompatible: {incompatible}[/red]",
        title="Summary",
        box=box.ROUNDED
    ))

    # Available MCP servers
    servers = get_available_mcp_servers()
    if servers:
        console.print(f"\n[cyan]Available MCP Servers:[/cyan] {', '.join(sorted(servers))}")
    else:
        console.print("\n[yellow]No MCP servers configured.[/yellow]")

    # Detailed table for agents with issues
    issues = [r for r in reports if not r.is_compatible]

    if issues:
        console.print("\n")
        table = Table(title="Agents with Missing Tools", box=box.ROUNDED)
        table.add_column("Agent", style="cyan")
        table.add_column("Score", justify="right")
        table.add_column("Missing MCP Tools", style="red")
        table.add_column("Unknown Tools", style="yellow")

        for report in issues:
            missing = ", ".join(report.missing_mcp_tools[:3])
            if len(report.missing_mcp_tools) > 3:
                missing += f" (+{len(report.missing_mcp_tools) - 3} more)"

            unknown = ", ".join(report.unknown_tools[:3])
            if len(report.unknown_tools) > 3:
                unknown += f" (+{len(report.unknown_tools) - 3} more)"

            score = f"{report.compatibility_score:.0f}%"
            score_style = "green" if report.compatibility_score >= 80 else "yellow" if report.compatibility_score >= 50 else "red"

            table.add_row(
                report.agent_name,
                f"[{score_style}]{score}[/{score_style}]",
                missing or "-",
                unknown or "-"
            )

        console.print(table)

        # Show missing MCP servers
        all_missing_servers = set()
        for report in issues:
            for tool in report.missing_mcp_tools:
                server_id, _ = parse_mcp_tool_name(tool)
                if server_id:
                    all_missing_servers.add(server_id)

        if all_missing_servers:
            console.print("\n[bold red]Missing MCP Servers:[/bold red]")
            for server in sorted(all_missing_servers):
                console.print(f"  • {server}")
            console.print("\n[dim]Install missing servers or remove tools from agents.[/dim]")

    else:
        console.print("\n[green]✓ All agents are compatible![/green]")


def get_missing_servers(reports: List[ToolCompatibility]) -> Set[str]:
    """Get set of all missing MCP server IDs from reports."""
    missing = set()
    for report in reports:
        for tool in report.missing_mcp_tools:
            server_id, _ = parse_mcp_tool_name(tool)
            if server_id:
                missing.add(server_id)
    return missing
