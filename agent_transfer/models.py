"""Data models for agent transfer."""

from dataclasses import dataclass
from typing import List, Optional, Dict
from pathlib import Path


@dataclass
class Agent:
    """Represents a Claude Code agent."""
    name: str
    description: str
    file_path: str
    agent_type: str  # 'user' or 'project'
    tools: Optional[List[str]] = None
    permission_mode: Optional[str] = None
    model: Optional[str] = None
    full_content: Optional[str] = None

    def __post_init__(self):
        if self.tools is None:
            self.tools = []


@dataclass
class AgentComparison:
    """Represents a comparison between archive and local agent."""
    agent: Agent                         # Agent from archive
    status: str                          # 'NEW', 'CHANGED', 'IDENTICAL'
    local_path: Optional[Path] = None    # Path to existing local agent
    local_content: Optional[str] = None  # Current local content
    archive_content: str = ""            # Incoming content from archive
    diff_summary: Optional[str] = None   # "+5 -3 ~2" format


@dataclass
class ImportPreview:
    """Pre-import analysis of an archive."""
    archive_path: str
    metadata: Dict[str, str]             # From metadata.txt
    comparisons: List[AgentComparison]   # All agent comparisons
    user_agents_count: int = 0
    project_agents_count: int = 0
    new_count: int = 0
    changed_count: int = 0
    identical_count: int = 0

