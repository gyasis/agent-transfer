"""Parse agent files and find agents."""

import re
import yaml
from pathlib import Path
from typing import List, Optional

from ..models import Agent
from .discovery import find_agent_directories


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
        return None


def find_all_agents() -> List[Agent]:
    """Find all agents using deep discovery of Claude Code installation."""
    agents = []
    
    # Use discovery to find all agent directories
    agent_dirs = find_agent_directories()
    
    for agent_dir_path, agent_type in agent_dirs:
        if agent_dir_path.exists() and agent_dir_path.is_dir():
            for agent_file in agent_dir_path.glob('*.md'):
                agent = parse_agent_file(agent_file)
                if agent:
                    agent.agent_type = agent_type
                    agents.append(agent)
    
    return agents

