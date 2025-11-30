"""Data models for agent transfer."""

from dataclasses import dataclass
from typing import List, Optional


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

