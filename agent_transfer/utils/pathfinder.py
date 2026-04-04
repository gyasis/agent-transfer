"""Centralized path resolution for platform-agnostic agent transfer.

This module is the sole authority for resolving filesystem paths across all
supported AI agent platforms. Every other module should call pathfinder
instead of constructing paths directly.

Usage:
    from agent_transfer.utils.pathfinder import get_pathfinder

    pf = get_pathfinder()
    agents = pf.agents_dir("claude-code")  # -> Path("~/.claude/agents")
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class PathProfile:
    """Defines a platform's filesystem layout.

    Each supported AI agent platform has a PathProfile that describes
    where its configuration, agents, skills, hooks, and executables live.
    """

    slug: str
    config_dir: str  # Relative to home: e.g. ".claude"
    agents_subdir: Optional[str] = None  # Relative to config_dir
    skills_subdir: Optional[str] = None
    hooks_subdir: Optional[str] = None
    rules_subdir: Optional[str] = None  # e.g. "rules" -> ~/.claude/rules/
    config_files: List[str] = field(default_factory=list)
    home_root_configs: List[str] = field(default_factory=list)  # Files at ~/ root
    instruction_files: List[str] = field(default_factory=list)  # e.g. ["CLAUDE.md"]
    executable_names: List[str] = field(default_factory=list)
    project_level: bool = False
    project_config_dir: Optional[str] = None
    env_override_var: Optional[str] = None
    search_paths: List[str] = field(default_factory=list)


# ── Built-in profiles ──────────────────────────────────────────────

BUILTIN_PROFILES: List[PathProfile] = [
    PathProfile(
        slug="claude-code",
        config_dir=".claude",
        agents_subdir="agents",
        skills_subdir="skills",
        hooks_subdir="hooks",
        rules_subdir="rules",
        config_files=["mcp.json", "settings.json", "settings.local.json",
                       "keybindings.json"],
        home_root_configs=[".claude.json"],
        instruction_files=["CLAUDE.md"],
        executable_names=["claude"],
        project_level=True,
        project_config_dir=".claude",
        env_override_var="CLAUDE_CONFIG_DIR",
    ),
    PathProfile(
        slug="codex",
        config_dir=".codex",
        agents_subdir=None,
        skills_subdir=None,
        hooks_subdir=None,
        config_files=["config.toml"],
        executable_names=["codex"],
        project_level=False,
        env_override_var="CODEX_CONFIG_DIR",
    ),
    PathProfile(
        slug="gemini-cli",
        config_dir=".gemini",
        agents_subdir="agents",
        skills_subdir="skills",
        hooks_subdir=None,
        config_files=["settings.json"],
        executable_names=["gemini"],
        project_level=False,
        env_override_var="GEMINI_CONFIG_DIR",
    ),
    PathProfile(
        slug="goose",
        config_dir=os.path.join(".config", "goose"),
        agents_subdir=None,
        skills_subdir="recipes",
        hooks_subdir=None,
        config_files=["profiles.yaml"],
        executable_names=["goose"],
        project_level=False,
        env_override_var="GOOSE_CONFIG_DIR",
    ),
    PathProfile(
        slug="opencode",
        config_dir=".opencode",
        agents_subdir="agents",
        skills_subdir="plugins",
        hooks_subdir=None,
        config_files=["opencode.json"],
        executable_names=["opencode"],
        project_level=True,
        project_config_dir=".opencode",
        env_override_var="OPENCODE_CONFIG_DIR",
    ),
]


class PathProfileRegistry:
    """Collection of registered path profiles, keyed by platform slug."""

    def __init__(self) -> None:
        self._profiles: Dict[str, PathProfile] = {}
        self._load_builtin_profiles()
        self._load_entry_points()

    def _load_builtin_profiles(self) -> None:
        for profile in BUILTIN_PROFILES:
            self._profiles[profile.slug] = profile

    def _load_entry_points(self) -> None:
        """Scan agent_transfer.path_profiles entry point group."""
        try:
            # Python 3.9+ has importlib.metadata in stdlib
            from importlib.metadata import entry_points

            try:
                # Python 3.12+ or 3.9+ with keyword arg
                eps = entry_points(group="agent_transfer.path_profiles")
            except TypeError:
                # Python 3.8: entry_points() returns a dict
                eps = entry_points().get("agent_transfer.path_profiles", [])

            for ep in eps:
                profile = ep.load()
                if isinstance(profile, PathProfile):
                    self._profiles[profile.slug] = profile
        except (ImportError, Exception):
            # No entry points or importlib.metadata not available
            pass

    def register(self, profile: PathProfile) -> None:
        self._profiles[profile.slug] = profile

    def get(self, slug: str) -> PathProfile:
        if slug not in self._profiles:
            valid = ", ".join(sorted(self._profiles.keys()))
            raise KeyError(
                f"Unknown platform '{slug}'. Valid platforms: {valid}"
            )
        return self._profiles[slug]

    def list_slugs(self) -> List[str]:
        return sorted(self._profiles.keys())


class Pathfinder:
    """Centralized path resolver for all supported AI agent platforms."""

    def __init__(self, project_search_depth: int = 5) -> None:
        self.registry = PathProfileRegistry()
        self.project_search_depth = project_search_depth
        self._cache: Dict[str, object] = {}

    # ── Directory resolution ────────────────────────────────────────

    def config_dir(self, slug: str) -> Path:
        """Return absolute path to the platform's config directory.

        Checks environment variable override first, falls back to default.
        """
        cache_key = f"config_dir:{slug}"
        if cache_key in self._cache:
            return self._cache[cache_key]  # type: ignore[return-value]

        profile = self.registry.get(slug)

        # Check env override
        if profile.env_override_var:
            override = os.environ.get(profile.env_override_var)
            if override:
                result = Path(override)
                self._cache[cache_key] = result
                return result

        result = Path.home() / profile.config_dir
        self._cache[cache_key] = result
        return result

    def agents_dir(self, slug: str) -> Optional[Path]:
        profile = self.registry.get(slug)
        if profile.agents_subdir is None:
            return None
        return self.config_dir(slug) / profile.agents_subdir

    def skills_dir(self, slug: str) -> Optional[Path]:
        profile = self.registry.get(slug)
        if profile.skills_subdir is None:
            return None
        return self.config_dir(slug) / profile.skills_subdir

    def hooks_dir(self, slug: str) -> Optional[Path]:
        profile = self.registry.get(slug)
        if profile.hooks_subdir is None:
            return None
        return self.config_dir(slug) / profile.hooks_subdir

    def rules_dir(self, slug: str) -> Optional[Path]:
        profile = self.registry.get(slug)
        if profile.rules_subdir is None:
            return None
        return self.config_dir(slug) / profile.rules_subdir

    def config_files(self, slug: str) -> List[Path]:
        profile = self.registry.get(slug)
        base = self.config_dir(slug)
        return [base / f for f in profile.config_files]

    def home_root_config_files(self, slug: str) -> List[Path]:
        """Return config files that live at ~/ root (not inside config_dir)."""
        profile = self.registry.get(slug)
        return [Path.home() / f for f in profile.home_root_configs]

    def instruction_files(self, slug: str) -> List[Path]:
        """Return instruction files (e.g. CLAUDE.md) inside config_dir."""
        profile = self.registry.get(slug)
        base = self.config_dir(slug)
        return [base / f for f in profile.instruction_files]

    def project_instruction_file(
        self, slug: str, start_dir: Optional[Path] = None
    ) -> Optional[Path]:
        """Find project-level instruction file (e.g. <project>/CLAUDE.md)."""
        profile = self.registry.get(slug)
        if not profile.instruction_files:
            return None
        current = (start_dir or Path.cwd()).resolve()
        for _ in range(self.project_search_depth):
            for fname in profile.instruction_files:
                candidate = current / fname
                if candidate.is_file():
                    return candidate
            parent = current.parent
            if parent == current:
                break
            current = parent
        return None

    # ── Project-level resolution ────────────────────────────────────

    def _search_upward(
        self, subdir: Optional[str], slug: str, start_dir: Optional[Path] = None
    ) -> Optional[Path]:
        """Search upward from start_dir for a project-level directory."""
        profile = self.registry.get(slug)
        if not profile.project_level or not profile.project_config_dir:
            return None
        if subdir is None:
            return None

        current = (start_dir or Path.cwd()).resolve()
        for _ in range(self.project_search_depth):
            candidate = current / profile.project_config_dir / subdir
            if candidate.is_dir():
                return candidate
            parent = current.parent
            if parent == current:
                break  # Reached filesystem root
            current = parent
        return None

    def project_agents_dir(
        self, slug: str, start_dir: Optional[Path] = None
    ) -> Optional[Path]:
        profile = self.registry.get(slug)
        return self._search_upward(profile.agents_subdir, slug, start_dir)

    def project_skills_dir(
        self, slug: str, start_dir: Optional[Path] = None
    ) -> Optional[Path]:
        profile = self.registry.get(slug)
        return self._search_upward(profile.skills_subdir, slug, start_dir)

    def all_agents_dirs(self, slug: str) -> List[Tuple[Path, str]]:
        result: List[Tuple[Path, str]] = []
        user = self.agents_dir(slug)
        if user is not None:
            result.append((user, "user"))
        project = self.project_agents_dir(slug)
        if project is not None:
            result.append((project, "project"))
        return result

    def all_skills_dirs(self, slug: str) -> List[Tuple[Path, str]]:
        result: List[Tuple[Path, str]] = []
        user = self.skills_dir(slug)
        if user is not None:
            result.append((user, "user"))
        project = self.project_skills_dir(slug)
        if project is not None:
            result.append((project, "project"))
        return result

    # ── Executable discovery ────────────────────────────────────────

    def find_executable(self, slug: str) -> Optional[Path]:
        cache_key = f"executable:{slug}"
        if cache_key in self._cache:
            return self._cache[cache_key]  # type: ignore[return-value]

        profile = self.registry.get(slug)
        result = self._find_executable_uncached(profile)
        self._cache[cache_key] = result
        return result

    def _find_executable_uncached(self, profile: PathProfile) -> Optional[Path]:
        """Ordered search for a platform executable."""
        for name in profile.executable_names:
            # 1. PATH via shutil.which
            found = shutil.which(name)
            if found:
                return Path(found)

            # 2. Environment variable override
            if profile.env_override_var:
                override = os.environ.get(profile.env_override_var)
                if override:
                    candidate = Path(override).parent / "bin" / name
                    if candidate.is_file() and os.access(candidate, os.X_OK):
                        return candidate

            # 3-5. npm/nvm paths (only for platforms that use node tooling)
            if self._uses_node_tooling(profile):
                npm_result = self._search_npm_nvm(name)
                if npm_result:
                    return npm_result

            # 6. Virtual environment
            venv = os.environ.get("VIRTUAL_ENV")
            if venv:
                candidate = Path(venv) / "bin" / name
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    return candidate

            # 7. Conda environment
            conda = os.environ.get("CONDA_PREFIX")
            if conda:
                candidate = Path(conda) / "bin" / name
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    return candidate

            # 8. System paths
            for sys_path in ["/usr/local/bin", "/usr/bin"]:
                candidate = Path(sys_path) / name
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    return candidate

            # 9. Custom search paths from profile
            for custom in profile.search_paths:
                candidate = Path(custom) / name
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    return candidate

        return None

    @staticmethod
    def _uses_node_tooling(profile: PathProfile) -> bool:
        """Check if a platform typically uses npm/nvm installed executables."""
        return profile.slug in ("claude-code", "codex")

    @staticmethod
    def _search_npm_nvm(name: str) -> Optional[Path]:
        """Search npm global and nvm paths for an executable."""
        home = Path.home()

        # npm global paths
        for npm_dir in [
            home / ".npm-global" / "bin",
            home / ".local" / "share" / "npm" / "bin",
        ]:
            candidate = npm_dir / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate

        # npm prefix
        try:
            result = subprocess.run(
                ["npm", "config", "get", "prefix"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                candidate = Path(result.stdout.strip()) / "bin" / name
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    return candidate
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

        # nvm paths
        nvm_dir = home / ".nvm" / "versions" / "node"
        if nvm_dir.is_dir():
            # Search newest version first
            versions = sorted(nvm_dir.iterdir(), reverse=True)
            for version_dir in versions:
                candidate = version_dir / "bin" / name
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    return candidate

        return None

    # ── Path remapping ──────────────────────────────────────────────

    def remap_path(
        self, path: Path, source_home: str, target_home: str
    ) -> Path:
        """Remap a path from one machine's home directory to another's."""
        path_str = str(path)
        source = str(source_home)
        target = str(target_home)

        # Normalize separators for cross-OS compatibility
        # (Windows exports use '\\', Linux uses '/')
        norm_path = path_str.replace("\\", "/")
        norm_source = source.replace("\\", "/")

        # No-op cases
        if not path.is_absolute() and not norm_path.startswith(norm_source):
            return path
        if norm_source == target.replace("\\", "/"):
            return path

        # Check if path starts with source home
        if not (norm_path.startswith(norm_source + "/") or norm_path == norm_source):
            return path

        # Replace prefix using normalized form
        relative = norm_path[len(norm_source):]
        return Path(target + relative)

    # ── Cross-platform translation ──────────────────────────────────

    def translate_path(
        self, path: str, from_platform: str, to_platform: str
    ) -> Tuple[str, Optional[str]]:
        """Translate a platform-specific path to another platform's structure.

        Returns (translated_path, warning) where warning is None on success.
        """
        from_profile = self.registry.get(from_platform)
        to_profile = self.registry.get(to_platform)
        home = str(Path.home())

        # Build mapping of (expanded_dir, dir_type) for source platform
        source_dirs = self._build_dir_map(from_profile, home)

        # Expand leading ~ only (not embedded tildes)
        if path.startswith("~/"):
            expanded = home + path[1:]
        elif path == "~":
            expanded = home
        else:
            expanded = path

        # Find longest matching prefix
        best_match = ""
        best_type = ""
        for dir_path, dir_type in source_dirs:
            if expanded.startswith(dir_path) and len(dir_path) > len(best_match):
                best_match = dir_path
                best_type = dir_type

        if not best_match:
            return (path, f"Path does not match any known {from_platform} directory")

        # Get the equivalent target directory
        target_dir = self._get_dir_for_type(to_profile, best_type, home)
        if target_dir is None:
            return (
                path,
                f"Platform '{to_platform}' has no equivalent for "
                f"'{best_type}' directory",
            )

        # Swap prefix
        relative = expanded[len(best_match):]
        result = target_dir + relative

        # Collapse home back to ~
        if result.startswith(home):
            result = "~" + result[len(home):]

        return (result, None)

    def _build_dir_map(
        self, profile: PathProfile, home: str
    ) -> List[Tuple[str, str]]:
        """Build (expanded_path, type) pairs for a profile's directories."""
        base = os.path.join(home, profile.config_dir)
        dirs: List[Tuple[str, str]] = [(base, "config")]

        if profile.agents_subdir:
            dirs.append((os.path.join(base, profile.agents_subdir), "agents"))
        if profile.skills_subdir:
            dirs.append((os.path.join(base, profile.skills_subdir), "skills"))
        if profile.hooks_subdir:
            dirs.append((os.path.join(base, profile.hooks_subdir), "hooks"))
        if profile.rules_subdir:
            dirs.append((os.path.join(base, profile.rules_subdir), "rules"))

        return dirs

    @staticmethod
    def _get_dir_for_type(
        profile: PathProfile, dir_type: str, home: str
    ) -> Optional[str]:
        """Get the expanded path for a directory type in a profile."""
        base = os.path.join(home, profile.config_dir)
        if dir_type == "config":
            return base
        if dir_type == "agents" and profile.agents_subdir:
            return os.path.join(base, profile.agents_subdir)
        if dir_type == "skills" and profile.skills_subdir:
            return os.path.join(base, profile.skills_subdir)
        if dir_type == "hooks" and profile.hooks_subdir:
            return os.path.join(base, profile.hooks_subdir)
        if dir_type == "rules" and profile.rules_subdir:
            return os.path.join(base, profile.rules_subdir)
        return None

    # ── Utilities ───────────────────────────────────────────────────

    def validate_path(self, path: Path) -> bool:
        return path.exists() and os.access(path, os.R_OK)

    def ensure_dir(self, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        return path

    def register_profile(self, profile: PathProfile) -> None:
        self.registry.register(profile)
        self.clear_cache()

    def supported_platforms(self) -> List[str]:
        return self.registry.list_slugs()

    def clear_cache(self) -> None:
        self._cache.clear()


# ── Module singleton ────────────────────────────────────────────────

_instance: Optional[Pathfinder] = None


def get_pathfinder() -> Pathfinder:
    """Return the module-level Pathfinder singleton."""
    global _instance
    if _instance is None:
        _instance = Pathfinder()
    return _instance


def _reset_pathfinder() -> None:
    """Reset the singleton. For test use only."""
    global _instance
    _instance = None


__all__ = [
    "PathProfile",
    "PathProfileRegistry",
    "Pathfinder",
    "get_pathfinder",
]
