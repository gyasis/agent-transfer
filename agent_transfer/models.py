"""Data models for agent transfer."""

from dataclasses import dataclass, field
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
class Skill:
    """Represents a Claude Code skill."""
    name: str
    description: str
    skill_path: str
    skill_type: str  # 'user' or 'project'
    allowed_tools: Optional[List[str]] = None
    model: Optional[str] = None
    context: Optional[str] = None
    agent: Optional[str] = None
    file_count: int = 0
    total_size_bytes: int = 0
    has_scripts: bool = False
    script_files: Optional[List[str]] = None
    skill_md_content: Optional[str] = None
    has_requirements_txt: bool = False
    has_pyproject_toml: bool = False
    has_uv_lock: bool = False

    def __post_init__(self):
        if self.allowed_tools is None:
            self.allowed_tools = []
        if self.script_files is None:
            self.script_files = []


@dataclass
class SkillComparison:
    """Represents a comparison between archive and local skill."""
    skill: Skill                                    # Skill from archive
    status: str                                     # 'NEW', 'CHANGED', 'IDENTICAL'
    local_path: Optional[Path] = None               # Path to existing local skill
    local_files: Optional[Dict[str, str]] = None    # Local file hashes
    archive_files: Optional[Dict[str, str]] = None  # Archive file hashes
    added_files: List[str] = field(default_factory=list)      # Files only in archive
    removed_files: List[str] = field(default_factory=list)    # Files only in local
    modified_files: List[str] = field(default_factory=list)   # Files with different hashes
    diff_summary: Optional[str] = None              # "+5 -3 ~2" format

    def __post_init__(self):
        if self.local_files is None:
            self.local_files = {}
        if self.archive_files is None:
            self.archive_files = {}


@dataclass
class ImportPreview:
    """Pre-import analysis of an archive."""
    archive_path: str
    metadata: Dict[str, str]                     # From metadata.txt
    comparisons: List[AgentComparison]           # All agent comparisons
    skill_comparisons: List[SkillComparison]     # All skill comparisons
    user_agents_count: int = 0
    project_agents_count: int = 0
    new_count: int = 0
    changed_count: int = 0
    identical_count: int = 0
    user_skills_count: int = 0
    project_skills_count: int = 0
    skill_new_count: int = 0
    skill_changed_count: int = 0
    skill_identical_count: int = 0

    def __post_init__(self):
        if not hasattr(self, 'skill_comparisons'):
            self.skill_comparisons = []

