"""Deep discovery of Claude Code skill directories."""

import os
import stat
from pathlib import Path
from typing import List, Tuple, Dict, Any


def find_skill_directories() -> List[Tuple[Path, str]]:
    """
    Find all skill directories with their types.
    Returns list of (skill_directory_path, type) tuples.

    Searches:
    - User-level: ~/.claude/skills/<skill-name>/ (if SKILL.md exists)
    - Project-level: ./.claude/skills/<skill-name>/ (up to 5 levels up from cwd)

    Returns:
        List of (skill_dir_path, type) where type is 'user' or 'project'
    """
    skill_dirs = []
    seen_paths = set()

    # User-level skills (in ~/.claude/skills/<skill-name>/)
    user_skills_base = Path.home() / ".claude" / "skills"
    if user_skills_base.exists() and user_skills_base.is_dir():
        for skill_dir in user_skills_base.iterdir():
            if skill_dir.is_dir():
                skill_md = skill_dir / "SKILL.md"
                if skill_md.exists() and skill_md.is_file():
                    resolved_path = skill_dir.resolve()
                    if resolved_path not in seen_paths:
                        seen_paths.add(resolved_path)
                        skill_dirs.append((skill_dir, "user"))

    # Project-level skills (in .claude/skills/<skill-name>/ relative to current/project directory)
    # But NOT the user-level ~/.claude/skills directory
    user_skills_resolved = (
        user_skills_base.resolve() if user_skills_base.exists() else None
    )
    current_dir = Path.cwd()

    for _ in range(5):  # Check up to 5 levels up
        project_skills_base = current_dir / ".claude" / "skills"

        # Skip if this is the user-level skills directory
        if project_skills_base.exists() and project_skills_base.is_dir():
            resolved_base = project_skills_base.resolve()
            if resolved_base != user_skills_resolved:
                # Iterate through skill directories
                for skill_dir in project_skills_base.iterdir():
                    if skill_dir.is_dir():
                        skill_md = skill_dir / "SKILL.md"
                        if skill_md.exists() and skill_md.is_file():
                            resolved_path = skill_dir.resolve()
                            if resolved_path not in seen_paths:
                                seen_paths.add(resolved_path)
                                skill_dirs.append((skill_dir, "project"))

        # Move up one directory level
        current_dir = current_dir.parent
        if current_dir == current_dir.parent:  # Reached root
            break

    return skill_dirs


def get_skill_directory_info(skill_dir: Path) -> Dict[str, Any]:
    """
    Get information about a skill directory.

    Args:
        skill_dir: Path to the skill directory

    Returns:
        Dict with:
        - file_count: Total number of files (recursively)
        - total_size: Total size in bytes
        - has_scripts: Boolean indicating if scripts are present
        - script_files: List of script file paths
        - all_files: List of all file paths
    """
    all_files = []
    script_files = []
    total_size = 0
    script_extensions = {".py", ".sh", ".js", ".rb", ".pl", ".lua", ".bash"}

    # Recursively walk through the skill directory
    for root, _dirs, files in os.walk(skill_dir):
        root_path = Path(root)
        for file in files:
            file_path = root_path / file

            # Skip if not a file or if it's a symlink
            if not file_path.is_file():
                continue

            all_files.append(file_path)

            # Calculate size
            try:
                total_size += file_path.stat().st_size
            except (OSError, PermissionError):
                pass

            # Check if it's a script
            is_script = False

            # Check extension
            if file_path.suffix.lower() in script_extensions:
                is_script = True
            else:
                # Check executable bit on Unix-like systems
                try:
                    file_stat = file_path.stat()
                    if file_stat.st_mode & stat.S_IXUSR:
                        is_script = True
                except (OSError, PermissionError):
                    pass

            if is_script:
                script_files.append(file_path)

    return {
        "file_count": len(all_files),
        "total_size": total_size,
        "has_scripts": len(script_files) > 0,
        "script_files": script_files,
        "all_files": all_files,
    }
