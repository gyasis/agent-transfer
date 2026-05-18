"""Parse skill files and find skills."""

import re
import yaml
from pathlib import Path
from typing import List, Optional, Dict, Any

from ..models import Skill
from .skill_discovery import find_skill_directories, get_skill_directory_info


def parse_skill_md(skill_md_path: Path) -> Optional[Dict[str, Any]]:
    """
    Parse a SKILL.md file and extract metadata.

    Args:
        skill_md_path: Path to SKILL.md file

    Returns:
        Dict with metadata fields and full_content, or None if parsing fails

    Fields extracted:
        - name: Skill name
        - description: Skill description
        - allowed-tools: List of allowed tools (from string or list)
        - model: Claude model to use
        - context: Context information
        - agent: Associated agent
        - version: Skill version
        - full_content: Complete file content
    """
    try:
        with open(skill_md_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract YAML frontmatter using same pattern as parser.py
        yaml_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
        if not yaml_match:
            # No frontmatter - return minimal metadata
            return {
                "name": skill_md_path.parent.name,
                "description": "No description available",
                "allowed_tools": [],
                "model": None,
                "context": None,
                "agent": None,
                "version": None,
                "full_content": content,
            }

        yaml_content = yaml_match.group(1)
        body_content = yaml_match.group(2)

        try:
            metadata = yaml.safe_load(yaml_content) or {}
        except yaml.YAMLError:
            metadata = {}

        # Extract description from body if not in frontmatter
        description = metadata.get("description", "")
        if not description:
            # Try to extract first paragraph from body
            first_line = body_content.strip().split("\n")[0]
            if first_line and len(first_line) < 200:
                description = first_line
            else:
                description = "No description available"

        # Parse allowed-tools (NOTE: field is "allowed-tools", not "tools"!)
        # Can be string (comma-separated) or list
        allowed_tools_raw = metadata.get("allowed-tools", "")
        if isinstance(allowed_tools_raw, str):
            allowed_tools = [
                t.strip() for t in allowed_tools_raw.split(",") if t.strip()
            ]
        elif isinstance(allowed_tools_raw, list):
            allowed_tools = allowed_tools_raw
        else:
            allowed_tools = []

        return {
            "name": metadata.get("name", skill_md_path.parent.name),
            "description": description,
            "allowed_tools": allowed_tools,
            "model": metadata.get("model"),
            "context": metadata.get("context"),
            "agent": metadata.get("agent"),
            "version": metadata.get("version"),
            "full_content": content,
        }
    except Exception:
        return None


def detect_dependencies(skill_dir: Path) -> Dict[str, Any]:
    """
    Detect dependency files in a skill directory.

    Args:
        skill_dir: Path to skill directory

    Returns:
        Dict with:
        - has_requirements_txt: Boolean
        - has_pyproject_toml: Boolean
        - has_uv_lock: Boolean
        - python_files: List of .py file paths
    """
    python_files = list(skill_dir.glob("*.py"))

    return {
        "has_requirements_txt": (skill_dir / "requirements.txt").exists(),
        "has_pyproject_toml": (skill_dir / "pyproject.toml").exists(),
        "has_uv_lock": (skill_dir / "uv.lock").exists(),
        "python_files": [str(f) for f in python_files],
    }


def parse_skill_directory(skill_dir: Path) -> Optional[Skill]:
    """
    Parse a complete skill directory and create a Skill object.

    Args:
        skill_dir: Path to skill directory

    Returns:
        Skill object or None if parsing fails

    Note:
        skill_type is NOT set by this function - caller should set it
        based on discovery results
    """
    skill_md_path = skill_dir / "SKILL.md"

    if not skill_md_path.exists():
        return None

    # Parse SKILL.md metadata
    metadata = parse_skill_md(skill_md_path)
    if not metadata:
        return None

    # Get directory information
    dir_info = get_skill_directory_info(skill_dir)

    # Detect dependencies
    deps = detect_dependencies(skill_dir)

    # Create Skill object
    # Note: skill_type will be set by caller
    return Skill(
        name=metadata["name"],
        description=metadata["description"],
        skill_path=str(skill_dir),
        skill_type="unknown",  # Will be set by caller
        allowed_tools=metadata["allowed_tools"],
        model=metadata["model"],
        context=metadata["context"],
        agent=metadata["agent"],
        file_count=dir_info["file_count"],
        total_size_bytes=dir_info["total_size"],
        has_scripts=dir_info["has_scripts"],
        script_files=[str(f) for f in dir_info["script_files"]],
        skill_md_content=metadata["full_content"],
        has_requirements_txt=deps["has_requirements_txt"],
        has_pyproject_toml=deps["has_pyproject_toml"],
        has_uv_lock=deps["has_uv_lock"],
    )


def parse_flat_skill_file(skill_md_path):
    """Q2 — parse a flat single-file skill (`~/.claude/skills/name.md`).

    Differs from `parse_skill_directory` in that there's no sibling
    `scripts/`, `requirements.txt`, etc. — file_count=1, total_size is
    the .md's size, has_scripts=False.
    """
    from pathlib import Path

    skill_md_path = Path(skill_md_path)
    if not skill_md_path.exists() or not skill_md_path.is_file():
        return None
    metadata = parse_skill_md(skill_md_path)
    if not metadata:
        return None
    return Skill(
        name=metadata["name"] or skill_md_path.stem,
        description=metadata["description"],
        skill_path=str(skill_md_path),
        skill_type="unknown",
        allowed_tools=metadata["allowed_tools"],
        model=metadata["model"],
        context=metadata["context"],
        agent=metadata["agent"],
        file_count=1,
        total_size_bytes=skill_md_path.stat().st_size,
        has_scripts=False,
        script_files=[],
        skill_md_content=metadata["full_content"],
        has_requirements_txt=False,
        has_pyproject_toml=False,
        has_uv_lock=False,
    )


def find_all_skills() -> List[Skill]:
    """
    Find all skills using deep discovery of Claude Code installation.

    Returns BOTH folder-shape skills (`name/SKILL.md`) AND flat single-
    file skills (`name.md`). Q2 from the PRD §5 list — historically only
    folder-shape skills were enumerated, silently dropping any flat
    skill at export time.

    Returns:
        List of Skill objects.
    """
    from .skill_discovery import find_flat_skill_files

    skills: List[Skill] = []
    seen_names: set[str] = set()

    # Folder-shape skills first (richer metadata wins on conflict).
    for skill_dir_path, skill_type in find_skill_directories():
        if skill_dir_path.exists() and skill_dir_path.is_dir():
            skill = parse_skill_directory(skill_dir_path)
            if skill:
                skill.skill_type = skill_type
                skills.append(skill)
                seen_names.add(skill.name)

    # Flat skills: only add if no folder-shape skill with the same name
    # already won. This handles the rare case of dual-shape co-existence
    # (e.g. both `name.md` AND `name/SKILL.md` — folder wins).
    for skill_md_path, skill_type in find_flat_skill_files():
        skill = parse_flat_skill_file(skill_md_path)
        if skill and skill.name not in seen_names:
            skill.skill_type = skill_type
            skills.append(skill)
            seen_names.add(skill.name)

    return skills
