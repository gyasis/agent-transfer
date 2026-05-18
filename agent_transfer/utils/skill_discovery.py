"""Deep discovery of Claude Code skill directories."""

import os
import stat
from pathlib import Path
from typing import List, Tuple, Dict, Any


def find_flat_skill_files(home: Path | None = None) -> List[Tuple[Path, str]]:
    """Q2 (v1.2 skill format drift) — return flat `name.md` skills.

    A flat skill is a single Markdown file directly under
    `~/.claude/skills/` (or `./.claude/skills/`), with no companion
    scripts or sibling assets. The contract for these is identical
    to a folder-shape `name/SKILL.md` except there's no script-bundle
    surface. Bundle them by copying the single .md verbatim.

    Returns a list of (skill_md_path, type) where type is 'user'|'project'.
    Folder-shape skills are NOT included here — call
    `find_skill_directories()` for those.
    """
    from .pathfinder import get_pathfinder

    pf = get_pathfinder()
    out: List[Tuple[Path, str]] = []
    seen: set[Path] = set()

    home = home or Path.home()
    user_base = pf.skills_dir("claude-code")
    if user_base is not None and user_base.is_dir():
        for p in user_base.iterdir():
            # Flat: .md file directly under skills/, NOT inside a subdir.
            if p.is_file() and p.suffix == ".md" and p.name != "SKILL.md":
                rp = p.resolve()
                if rp not in seen:
                    seen.add(rp)
                    out.append((p, "user"))

    # Project-level walk (same depth bound as find_skill_directories).
    user_resolved = user_base.resolve() if user_base and user_base.exists() else None
    cur = Path.cwd()
    for _ in range(5):
        proj_base = cur / ".claude" / "skills"
        if proj_base.exists() and proj_base.is_dir():
            if proj_base.resolve() != user_resolved:
                for p in proj_base.iterdir():
                    if p.is_file() and p.suffix == ".md" and p.name != "SKILL.md":
                        rp = p.resolve()
                        if rp not in seen:
                            seen.add(rp)
                            out.append((p, "project"))
        if cur == cur.parent:
            break
        cur = cur.parent

    return out


def find_skill_directories() -> List[Tuple[Path, str]]:
    """
    Find all skill directories with their types.
    Returns list of (skill_directory_path, type) tuples.

    Searches:
    - User-level: ~/.claude/skills/<skill-name>/ (if SKILL.md exists)
    - Project-level: ./.claude/skills/<skill-name>/ (up to 5 levels up from cwd)

    NOTE: This only returns FOLDER-shape skills. For flat single-file
    skills (`~/.claude/skills/name.md`) see `find_flat_skill_files()`.

    Returns:
        List of (skill_dir_path, type) where type is 'user' or 'project'
    """
    from .pathfinder import get_pathfinder

    pf = get_pathfinder()
    skill_dirs = []
    seen_paths = set()

    # User-level skills
    user_skills_base = pf.skills_dir("claude-code")
    if user_skills_base is not None and user_skills_base.exists() and user_skills_base.is_dir():
        for skill_dir in user_skills_base.iterdir():
            if skill_dir.is_dir():
                skill_md = skill_dir / "SKILL.md"
                if skill_md.exists() and skill_md.is_file():
                    resolved_path = skill_dir.resolve()
                    if resolved_path not in seen_paths:
                        seen_paths.add(resolved_path)
                        skill_dirs.append((skill_dir, "user"))

    # Project-level skills — but NOT the user-level directory
    user_skills_resolved = (
        user_skills_base.resolve() if user_skills_base is not None and user_skills_base.exists() else None
    )
    current_dir = Path.cwd()

    for _ in range(5):  # Check up to 5 levels up
        project_skills_base = current_dir / ".claude" / "skills"

        # Skip if this is the user-level skills directory
        if project_skills_base.exists() and project_skills_base.is_dir():
            resolved_base = project_skills_base.resolve()
            if resolved_base != user_skills_resolved:
                for skill_dir in project_skills_base.iterdir():
                    if skill_dir.is_dir():
                        skill_md = skill_dir / "SKILL.md"
                        if skill_md.exists() and skill_md.is_file():
                            resolved_path = skill_dir.resolve()
                            if resolved_path not in seen_paths:
                                seen_paths.add(resolved_path)
                                skill_dirs.append((skill_dir, "project"))

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
