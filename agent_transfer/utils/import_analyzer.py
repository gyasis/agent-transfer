"""
Import archive analysis and change detection module.

This module provides functionality for analyzing agent import archives,
comparing them with local agents, and generating detailed previews of
changes before performing imports.
"""

import hashlib
import tarfile
import tempfile
from pathlib import Path
from typing import Optional, Dict, List
import difflib

from ..models import Agent, AgentComparison, ImportPreview
from .parser import parse_agent_file


def analyze_import_archive(archive_path: str) -> ImportPreview:
    """
    Analyze an import archive and compare with local agents.

    Extracts the archive to a temporary directory, parses all agents,
    and compares each with local versions to detect new, changed, or
    identical agents.

    Args:
        archive_path: Path to the tar.gz archive file

    Returns:
        ImportPreview with all comparisons and summary statistics

    Raises:
        FileNotFoundError: If archive does not exist
        tarfile.TarError: If archive is invalid or corrupted
    """
    archive_path_obj = Path(archive_path)
    if not archive_path_obj.exists():
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    comparisons = []
    metadata = {}

    # Extract archive to temp directory and analyze
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Extract archive with error handling
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(temp_path)
        except tarfile.TarError as e:
            raise RuntimeError(
                f"Failed to extract archive. File may be corrupted."
            ) from e

        # Read metadata if present
        metadata_file = temp_path / "metadata.txt"
        if metadata_file.exists():
            metadata = _parse_metadata_file(metadata_file)

        # Find and parse all agents from archive
        archive_agents = []

        # Parse user agents
        user_agents_dir = temp_path / "user-agents"
        if user_agents_dir.exists():
            user_agents = _find_agents_in_directory(user_agents_dir, "user")
            archive_agents.extend(user_agents)

        # Parse project agents
        project_agents_dir = temp_path / "project-agents"
        if project_agents_dir.exists():
            project_agents = _find_agents_in_directory(project_agents_dir, "project")
            archive_agents.extend(project_agents)

        # Compare each archive agent with local version
        for archive_agent in archive_agents:
            local_path = find_local_agent_path(
                archive_agent.name,
                archive_agent.agent_type
            )

            local_agent = None
            if local_path:
                try:
                    local_agent = parse_agent_file(local_path)
                except Exception:
                    # If parsing fails, treat as if no local agent exists
                    pass

            comparison = compare_agents(archive_agent, local_agent)
            comparisons.append(comparison)

    # Handle empty archive
    if not comparisons:
        from rich.console import Console
        console = Console()
        console.print("[yellow]Archive is empty (no agents found)[/yellow]")

    # Calculate summary statistics
    new_count = sum(1 for c in comparisons if c.status == "NEW")
    changed_count = sum(1 for c in comparisons if c.status == "CHANGED")
    identical_count = sum(1 for c in comparisons if c.status == "IDENTICAL")

    # Count user vs project agents
    user_count = sum(1 for c in comparisons if c.agent.agent_type == "user")
    project_count = sum(1 for c in comparisons if c.agent.agent_type == "project")

    return ImportPreview(
        archive_path=archive_path,
        metadata=metadata,
        comparisons=comparisons,
        user_agents_count=user_count,
        project_agents_count=project_count,
        new_count=new_count,
        changed_count=changed_count,
        identical_count=identical_count
    )


def compare_agents(
    archive_agent: Agent,
    local_agent: Optional[Agent]
) -> AgentComparison:
    """
    Compare an archive agent with its local version.

    Uses SHA256 hashing for efficient content comparison. If agents
    differ, generates a detailed diff summary showing additions,
    deletions, and modifications.

    Args:
        archive_agent: Agent from the import archive
        local_agent: Local agent (None if doesn't exist)

    Returns:
        AgentComparison with status and diff information
    """
    # New agent if no local version exists
    if local_agent is None:
        return AgentComparison(
            agent=archive_agent,
            status="NEW",
            local_path=None,
            local_content=None,
            archive_content=archive_agent.full_content or "",
            diff_summary=None
        )

    # Get local path for comparison display
    local_path = find_local_agent_path(archive_agent.name, archive_agent.agent_type)

    # Compare content hashes (handle None content)
    archive_content = archive_agent.full_content or ""
    local_content = local_agent.full_content or ""

    archive_hash = _compute_content_hash(archive_content)
    local_hash = _compute_content_hash(local_content)

    if archive_hash == local_hash:
        # Identical agents
        return AgentComparison(
            agent=archive_agent,
            status="IDENTICAL",
            local_path=local_path,
            local_content=local_content,
            archive_content=archive_content,
            diff_summary=None
        )
    else:
        # Changed agent - generate diff
        diff_summary = generate_diff_summary(local_content, archive_content)

        return AgentComparison(
            agent=archive_agent,
            status="CHANGED",
            local_path=local_path,
            local_content=local_content,
            archive_content=archive_content,
            diff_summary=diff_summary
        )


def generate_diff_summary(existing: str, incoming: str) -> str:
    """
    Generate a concise diff summary between two content versions.

    Uses difflib to analyze line-by-line differences and produces
    a summary in the format: "+5 -3 ~2" indicating lines added,
    removed, and changed.

    Args:
        existing: Current local content
        incoming: New content from archive

    Returns:
        Diff summary string (e.g., "+5 -3 ~2")
    """
    existing_lines = existing.splitlines(keepends=True)
    incoming_lines = incoming.splitlines(keepends=True)

    # Use unified diff to detect changes
    diff = list(difflib.unified_diff(
        existing_lines,
        incoming_lines,
        lineterm=""
    ))

    # Count changes (skip diff headers)
    added = 0
    removed = 0

    for line in diff:
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1

    # Calculate "changed" lines as overlapping adds/removes
    # This is a heuristic: min of adds and removes represents modifications
    changed = min(added, removed)
    pure_added = added - changed
    pure_removed = removed - changed

    # Build summary string
    parts = []
    if pure_added > 0:
        parts.append(f"+{pure_added}")
    if pure_removed > 0:
        parts.append(f"-{pure_removed}")
    if changed > 0:
        parts.append(f"~{changed}")

    return " ".join(parts) if parts else "no changes"


def find_local_agent_path(agent_name: str, agent_type: str) -> Optional[Path]:
    """
    Find the local path for an agent by name and type.

    Args:
        agent_name: Name of the agent (without .md extension)
        agent_type: Either "user" or "project"

    Returns:
        Path to local agent file if it exists, None otherwise
    """
    if agent_type == "user":
        # User agents live in ~/.claude/agents/
        user_agents_dir = Path.home() / ".claude" / "agents"
        agent_path = user_agents_dir / f"{agent_name}.md"
    elif agent_type == "project":
        # Project agents live in .claude/agents/ (current directory)
        project_agents_dir = Path.cwd() / ".claude" / "agents"
        agent_path = project_agents_dir / f"{agent_name}.md"
    else:
        return None

    return agent_path if agent_path.exists() else None


def _compute_content_hash(content: str) -> str:
    """
    Compute SHA256 hash of content for fast comparison.

    Args:
        content: String content to hash

    Returns:
        Hexadecimal hash string
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _find_agents_in_directory(directory: Path, agent_type: str) -> List[Agent]:
    """
    Find and parse all agent files in a directory.

    Args:
        directory: Directory containing agent .md files
        agent_type: Type to assign ('user' or 'project')

    Returns:
        List of parsed Agent objects
    """
    agents = []

    if directory.exists() and directory.is_dir():
        for agent_file in directory.glob('*.md'):
            try:
                agent = parse_agent_file(agent_file)
                if agent:
                    agent.agent_type = agent_type
                    agents.append(agent)
            except Exception:
                # Skip files that fail to parse
                continue

    return agents


def _parse_metadata_file(metadata_path: Path) -> Dict[str, str]:
    """
    Parse metadata.txt file from archive.

    Args:
        metadata_path: Path to metadata.txt file

    Returns:
        Dictionary of metadata key-value pairs
    """
    metadata = {}

    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if ":" in line:
                    key, value = line.split(":", 1)
                    metadata[key.strip()] = value.strip()
    except Exception:
        # Return empty dict if parsing fails
        pass

    return metadata
