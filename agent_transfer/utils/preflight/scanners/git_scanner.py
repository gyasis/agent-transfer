"""Git repository scanner.

Extracts remote origin URLs from .git/config files and detects
the setup method (pip, uv, npm, cargo, docker) from repo contents.
"""

import configparser
from pathlib import Path
from typing import List, Optional

from agent_transfer.utils.preflight.manifest import GitRepoDep


def extract_git_remote(git_dir: Path) -> Optional[str]:
    """Extract remote origin URL from a .git/config file.

    Args:
        git_dir: Path to the .git directory (not the repo root).

    Returns:
        The remote origin URL string, or None if it cannot be read.
    """
    config_path = git_dir / "config"
    if not config_path.is_file():
        return None

    parser = configparser.ConfigParser()
    try:
        parser.read(str(config_path), encoding="utf-8")
    except (configparser.Error, OSError):
        return None

    section = 'remote "origin"'
    if not parser.has_section(section):
        return None

    return parser.get(section, "url", fallback=None)


def detect_setup_method(repo_path: Path) -> str:
    """Detect the setup method for a git repository based on its contents.

    Checks for language-specific project files in priority order:
    Cargo.toml -> pyproject.toml (uv) -> pyproject.toml -> package.json
    -> Dockerfile -> requirements.txt -> fallback to pip.

    Args:
        repo_path: Path to the repository root directory.

    Returns:
        A string identifier for the setup method.
    """
    if (repo_path / "Cargo.toml").is_file():
        return "cargo"

    pyproject = repo_path / "pyproject.toml"
    if pyproject.is_file():
        try:
            content = pyproject.read_text(encoding="utf-8")
            if "uv" in content:
                return "uv"
        except OSError:
            pass
        return "python-venv"

    if (repo_path / "package.json").is_file():
        return "npm"

    if (repo_path / "Dockerfile").is_file():
        return "docker"

    if (repo_path / "requirements.txt").is_file():
        return "pip"

    return "pip"


def scan_git_repo(repo_path: Path, required_by: str = "") -> Optional[GitRepoDep]:
    """Scan a directory for git repo info.

    Args:
        repo_path: Path to a directory that may contain a .git folder.
        required_by: An identifier for what depends on this repo.

    Returns:
        A GitRepoDep dataclass instance, or None if the directory is not
        a git repository or has no readable remote.
    """
    repo_path = Path(repo_path)
    git_dir = repo_path / ".git"
    if not git_dir.is_dir():
        return None

    remote_url = extract_git_remote(git_dir)
    if remote_url is None:
        return None

    setup_method = detect_setup_method(repo_path)
    required = [required_by] if required_by else []

    return GitRepoDep(
        name=repo_path.name,
        repo_url=remote_url,
        local_path=str(repo_path),
        setup_method=setup_method,
        required_by=required,
    )


def scan_git_repos(repo_paths: list, required_by: str = "") -> List[GitRepoDep]:
    """Scan multiple directories for git repos.

    Args:
        repo_paths: List of paths (str or Path) to check.
        required_by: An identifier for what depends on these repos.

    Returns:
        A list of GitRepoDep instances for directories that are valid
        git repositories with a readable remote origin.
    """
    results = []  # type: List[GitRepoDep]
    for path in repo_paths:
        dep = scan_git_repo(Path(path), required_by=required_by)
        if dep is not None:
            results.append(dep)
    return results
