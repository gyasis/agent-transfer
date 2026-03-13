"""Scanner for author-provided .preflight.yml declarations.

Reads a `.preflight.yml` file that authors place alongside their agent/skill
to declare additional dependencies that cannot be auto-detected by other
scanners (e.g. CLI tools invoked dynamically, env vars used at runtime).

Expected schema::

    dependencies:
      cli_tools:
        - name: string
          install_hint: string (optional)
          version_hint: string (optional)
      env_vars:
        - name: string
          description: string (optional)
      packages:
        - name: string
          ecosystem: string  # "python" or "node"
    notes:
      - string  # Added to Manual Checklist in report
"""

import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

import yaml

from agent_transfer.utils.preflight.manifest import (
    CliToolDep,
    EnvVarDep,
    PackageDep,
)

logger = logging.getLogger(__name__)


@dataclass
class PreflightConfig:
    """Parsed result of a .preflight.yml file."""

    cli_tools: List[CliToolDep] = field(default_factory=list)
    env_vars: List[EnvVarDep] = field(default_factory=list)
    packages: List[PackageDep] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def _parse_cli_tools(raw: Any, required_by: str) -> List[CliToolDep]:
    """Parse the cli_tools list from YAML data."""
    if not isinstance(raw, list):
        logger.warning(".preflight.yml: dependencies.cli_tools is not a list, skipping")
        return []

    results: List[CliToolDep] = []
    for item in raw:
        if isinstance(item, str):
            # Allow shorthand: just a tool name string
            results.append(
                CliToolDep(
                    name=item,
                    required_by=[required_by] if required_by else [],
                )
            )
        elif isinstance(item, dict):
            name = item.get("name")
            if not name or not isinstance(name, str):
                logger.warning(
                    ".preflight.yml: cli_tools entry missing 'name', skipping: %r",
                    item,
                )
                continue
            results.append(
                CliToolDep(
                    name=name,
                    version_hint=_str_or_none(item.get("version_hint")),
                    install_hint=_str_or_none(item.get("install_hint")),
                    required_by=[required_by] if required_by else [],
                )
            )
        else:
            logger.warning(
                ".preflight.yml: unexpected cli_tools entry type %s, skipping",
                type(item).__name__,
            )
    return results


def _parse_env_vars(raw: Any, required_by: str) -> List[EnvVarDep]:
    """Parse the env_vars list from YAML data."""
    if not isinstance(raw, list):
        logger.warning(".preflight.yml: dependencies.env_vars is not a list, skipping")
        return []

    results: List[EnvVarDep] = []
    for item in raw:
        if isinstance(item, str):
            results.append(
                EnvVarDep(
                    name=item,
                    required_by=[required_by] if required_by else [],
                )
            )
        elif isinstance(item, dict):
            name = item.get("name")
            if not name or not isinstance(name, str):
                logger.warning(
                    ".preflight.yml: env_vars entry missing 'name', skipping: %r",
                    item,
                )
                continue
            results.append(
                EnvVarDep(
                    name=name,
                    description=_str_or_none(item.get("description")),
                    required_by=[required_by] if required_by else [],
                )
            )
        else:
            logger.warning(
                ".preflight.yml: unexpected env_vars entry type %s, skipping",
                type(item).__name__,
            )
    return results


def _parse_packages(raw: Any, required_by: str) -> List[PackageDep]:
    """Parse the packages list from YAML data."""
    if not isinstance(raw, list):
        logger.warning(".preflight.yml: dependencies.packages is not a list, skipping")
        return []

    valid_ecosystems = {"python", "node"}
    results: List[PackageDep] = []
    for item in raw:
        if isinstance(item, str):
            results.append(
                PackageDep(
                    name=item,
                    required_by=[required_by] if required_by else [],
                )
            )
        elif isinstance(item, dict):
            name = item.get("name")
            if not name or not isinstance(name, str):
                logger.warning(
                    ".preflight.yml: packages entry missing 'name', skipping: %r",
                    item,
                )
                continue
            ecosystem = item.get("ecosystem", "python")
            if not isinstance(ecosystem, str):
                ecosystem = "python"
            if ecosystem not in valid_ecosystems:
                logger.warning(
                    ".preflight.yml: unknown ecosystem %r for package %r, "
                    "defaulting to 'python'",
                    ecosystem,
                    name,
                )
                ecosystem = "python"
            results.append(
                PackageDep(
                    name=name,
                    ecosystem=ecosystem,
                    required_by=[required_by] if required_by else [],
                )
            )
        else:
            logger.warning(
                ".preflight.yml: unexpected packages entry type %s, skipping",
                type(item).__name__,
            )
    return results


def _parse_notes(raw: Any) -> List[str]:
    """Parse the notes list from YAML data."""
    if not isinstance(raw, list):
        logger.warning(".preflight.yml: notes is not a list, skipping")
        return []

    results: List[str] = []
    for item in raw:
        if isinstance(item, str):
            results.append(item)
        else:
            # Coerce non-string scalars to str; skip complex types
            if isinstance(item, (int, float, bool)):
                results.append(str(item))
            else:
                logger.warning(
                    ".preflight.yml: unexpected notes entry type %s, skipping",
                    type(item).__name__,
                )
    return results


def _str_or_none(value: Any) -> Optional[str]:
    """Convert a value to str if truthy, else None."""
    if value is None:
        return None
    if isinstance(value, str):
        return value if value else None
    return str(value)


def read_preflight_yml(file_path: Path, required_by: str = "") -> PreflightConfig:
    """Read and parse a .preflight.yml file.

    Args:
        file_path: Path to the .preflight.yml file.
        required_by: Identifier for what component requires these
            dependencies (e.g. "skills/my-skill"). Propagated into
            each dependency's ``required_by`` list.

    Returns:
        A :class:`PreflightConfig` with parsed dependencies and notes.
        If the file is missing, malformed, or has unexpected structure,
        returns an empty config (never raises).
    """
    config = PreflightConfig()

    if not file_path.exists():
        return config

    try:
        raw_text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning(".preflight.yml: could not read %s: %s", file_path, exc)
        warnings.warn(
            f"Could not read {file_path}: {exc}",
            stacklevel=2,
        )
        return config

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        logger.warning(".preflight.yml: malformed YAML in %s: %s", file_path, exc)
        warnings.warn(
            f"Malformed YAML in {file_path}: {exc}",
            stacklevel=2,
        )
        return config

    if not isinstance(data, dict):
        logger.warning(
            ".preflight.yml: top-level value in %s is not a mapping", file_path
        )
        return config

    # --- Parse dependencies section ---
    deps = data.get("dependencies")
    if isinstance(deps, dict):
        cli_raw = deps.get("cli_tools")
        if cli_raw is not None:
            config.cli_tools = _parse_cli_tools(cli_raw, required_by)

        env_raw = deps.get("env_vars")
        if env_raw is not None:
            config.env_vars = _parse_env_vars(env_raw, required_by)

        pkg_raw = deps.get("packages")
        if pkg_raw is not None:
            config.packages = _parse_packages(pkg_raw, required_by)
    elif deps is not None:
        logger.warning(
            ".preflight.yml: 'dependencies' in %s is not a mapping, skipping",
            file_path,
        )

    # --- Parse notes section ---
    notes_raw = data.get("notes")
    if notes_raw is not None:
        config.notes = _parse_notes(notes_raw)

    return config
