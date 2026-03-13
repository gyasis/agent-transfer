"""Inventory collector -- composes all scanners to build a TransferManifest.

Scans agent markdown files, skill directories, hook scripts, and MCP config
files using the six dedicated scanners.  Produces a complete
:class:`TransferManifest` ready for serialization into ``manifest.json``.

Python >= 3.8 compatible.  Uses pathlib throughout (R6).
"""

from __future__ import annotations

import json
import logging
import os
import platform as _platform_mod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from agent_transfer.utils.preflight.manifest import (
    BinaryDep,
    CliToolDep,
    ContentsInventory,
    DependencyGraph,
    DockerDep,
    EnvVarDep,
    GitRepoDep,
    McpServerDep,
    PackageDep,
    SkillTreeDep,
    SourcedFileDep,
    TransferManifest,
)
from agent_transfer.utils.preflight.scanners.binary_scanner import (
    is_elf_binary,
    scan_binary,
)
from agent_transfer.utils.preflight.scanners.docker_scanner import scan_docker
from agent_transfer.utils.preflight.scanners.git_scanner import scan_git_repo
from agent_transfer.utils.preflight.scanners.mcp_scanner import (
    extract_mcp_server_ids,
    scan_mcp_servers,
)
from agent_transfer.utils.preflight.scanners.preflight_yml import read_preflight_yml
from agent_transfer.utils.preflight.scanners.script_scanner import scan_scripts

logger = logging.getLogger(__name__)

# Script extensions that the script scanner supports.
_SCRIPT_SUFFIXES: Set[str] = {".sh", ".py", ".js"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def collect_inventory(
    agents: List[Path],
    skills: List[Path],
    hooks: List[Path],
    configs: List[Path],
    platform: str = "claude-code",
) -> TransferManifest:
    """Scan all provided paths and build a complete :class:`TransferManifest`.

    Parameters
    ----------
    agents:
        Paths to agent ``.md`` files.  Frontmatter is parsed for tool
        declarations; the body is scanned for ``mcp__<id>__<tool>``
        references.
    skills:
        Paths to skill *directories*.  Each is scanned for scripts,
        binaries, ``.preflight.yml``, ``.git``, and Docker artifacts.
    hooks:
        Paths to hook files or directories.  Files are scanned for
        script dependencies; directories have their contents scanned
        recursively (one level).
    configs:
        Paths to MCP config JSON files (e.g. ``mcp.json``,
        ``settings.json``).  Parsed and passed to the MCP scanner.
    platform:
        Platform identifier written into the manifest
        (default ``"claude-code"``).

    Returns
    -------
    TransferManifest
        Fully populated manifest ready for serialization.
    """
    # Accumulators for the dependency graph.
    mcp_servers: Dict[str, McpServerDep] = {}
    git_repos: Dict[str, GitRepoDep] = {}
    binaries: Dict[str, BinaryDep] = {}
    skill_trees: Dict[str, SkillTreeDep] = {}
    cli_tools: Dict[str, CliToolDep] = {}
    env_vars: Dict[str, EnvVarDep] = {}
    docker_deps: List[DockerDep] = []
    packages: Dict[str, PackageDep] = {}
    sourced_files: Dict[str, SourcedFileDep] = {}

    # Contents inventory lists (relative-ish names for the archive).
    agent_names: List[str] = []
    skill_names: List[str] = []
    hook_names: List[str] = []
    config_names: List[str] = []

    # ------------------------------------------------------------------
    # 1. Agents (.md files)
    # ------------------------------------------------------------------
    for agent_path in agents:
        agent_path = Path(agent_path)
        if not agent_path.is_file():
            logger.warning("Agent path is not a file, skipping: %s", agent_path)
            continue

        label = agent_path.stem
        agent_names.append(agent_path.name)

        try:
            content = agent_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("Could not read agent file %s: %s", agent_path, exc)
            continue

        # Extract MCP server IDs from tool declarations in the body.
        server_ids = extract_mcp_server_ids(content)
        for sid in server_ids:
            if sid not in mcp_servers:
                mcp_servers[sid] = McpServerDep(
                    id=sid,
                    required_by=[label],
                )
            else:
                _merge_required_by(mcp_servers[sid], label)

    # ------------------------------------------------------------------
    # 2. Skills (directories)
    # ------------------------------------------------------------------
    for skill_dir in skills:
        skill_dir = Path(skill_dir)
        if not skill_dir.is_dir():
            logger.warning("Skill path is not a directory, skipping: %s", skill_dir)
            continue

        label = skill_dir.name
        skill_names.append(label)

        # Collect all scannable files in the skill directory.
        script_files: List[Path] = []
        binary_candidates: List[Path] = []

        for child in _iter_files(skill_dir):
            if child.suffix.lower() in _SCRIPT_SUFFIXES:
                script_files.append(child)
            elif child.is_file() and _is_executable(child):
                binary_candidates.append(child)

        # 2a. Script scanning (CLI tools, env vars, packages, sourced files).
        script_results = scan_scripts(script_files, required_by=label)
        _merge_cli_tools(cli_tools, script_results["cli_tools"])
        _merge_env_vars(env_vars, script_results["env_vars"])
        _merge_packages(packages, script_results["packages"])
        _merge_sourced_files(sourced_files, script_results["sourced_files"])

        # 2b. Binary scanning.
        for bp in binary_candidates:
            dep = scan_binary(bp, required_by=label)
            if dep is not None:
                _merge_binary(binaries, dep)

        # 2c. .preflight.yml declarations.
        preflight_path = skill_dir / ".preflight.yml"
        if preflight_path.is_file():
            pf_config = read_preflight_yml(preflight_path, required_by=label)
            _merge_cli_tools(cli_tools, pf_config.cli_tools)
            _merge_env_vars(env_vars, pf_config.env_vars)
            _merge_packages(packages, pf_config.packages)

        # 2d. Git repo detection.
        git_dep = scan_git_repo(skill_dir, required_by=label)
        if git_dep is not None:
            _merge_git_repo(git_repos, git_dep)

        # 2e. Docker scanning.
        docker_results = scan_docker(
            skill_dir,
            script_files=script_files,
            required_by=label,
        )
        docker_deps.extend(docker_results)

        # 2f. Build a SkillTreeDep summary.
        skill_tree = _build_skill_tree(
            skill_dir,
            label=label,
            script_results=script_results,
            pf_path=preflight_path,
            binary_candidates=binary_candidates,
        )
        skill_trees[label] = skill_tree

    # ------------------------------------------------------------------
    # 3. Hooks (files or directories)
    # ------------------------------------------------------------------
    for hook_path in hooks:
        hook_path = Path(hook_path)
        if hook_path.is_file():
            label = hook_path.stem
            hook_names.append(hook_path.name)

            if hook_path.suffix.lower() in _SCRIPT_SUFFIXES:
                results = scan_scripts([hook_path], required_by=label)
                _merge_cli_tools(cli_tools, results["cli_tools"])
                _merge_env_vars(env_vars, results["env_vars"])
                _merge_packages(packages, results["packages"])
                _merge_sourced_files(sourced_files, results["sourced_files"])

        elif hook_path.is_dir():
            label = hook_path.name
            hook_names.append(label)

            script_files = [
                f
                for f in _iter_files(hook_path)
                if f.suffix.lower() in _SCRIPT_SUFFIXES
            ]
            if script_files:
                results = scan_scripts(script_files, required_by=label)
                _merge_cli_tools(cli_tools, results["cli_tools"])
                _merge_env_vars(env_vars, results["env_vars"])
                _merge_packages(packages, results["packages"])
                _merge_sourced_files(sourced_files, results["sourced_files"])
        else:
            logger.warning("Hook path does not exist, skipping: %s", hook_path)

    # ------------------------------------------------------------------
    # 4. MCP configs (JSON files)
    # ------------------------------------------------------------------
    for config_path in configs:
        config_path = Path(config_path)
        if not config_path.is_file():
            logger.warning("Config path is not a file, skipping: %s", config_path)
            continue

        config_names.append(config_path.name)
        label = config_path.stem

        mcp_config = _load_json_safe(config_path)
        if mcp_config is None:
            continue

        server_deps = scan_mcp_servers(mcp_config, required_by=label)
        for dep in server_deps:
            if dep.id in mcp_servers:
                _merge_mcp_server(mcp_servers[dep.id], dep)
            else:
                mcp_servers[dep.id] = dep

    # ------------------------------------------------------------------
    # 5. Platform metadata
    # ------------------------------------------------------------------
    source_os = _platform_mod.system().lower()
    source_arch = _platform_mod.machine()
    source_home = str(Path.home())

    # ------------------------------------------------------------------
    # 6. Assemble the manifest
    # ------------------------------------------------------------------
    manifest = TransferManifest(
        manifest_version="2.0",
        created_at=datetime.now(timezone.utc).isoformat(),
        source_platform=platform,
        source_os=source_os,
        source_arch=source_arch,
        source_home=source_home,
        contents=ContentsInventory(
            agents=sorted(agent_names),
            skills=sorted(skill_names),
            hooks=sorted(hook_names),
            configs=sorted(config_names),
        ),
        dependencies=DependencyGraph(
            mcp_servers=sorted(mcp_servers.values(), key=lambda d: d.id),
            git_repos=sorted(git_repos.values(), key=lambda d: d.name),
            compiled_binaries=sorted(binaries.values(), key=lambda d: d.name),
            skill_trees=sorted(skill_trees.values(), key=lambda d: d.name),
            cli_tools=sorted(cli_tools.values(), key=lambda d: d.name),
            env_vars=sorted(env_vars.values(), key=lambda d: d.name),
            docker=docker_deps,
            python_packages=sorted(
                [p for p in packages.values() if p.ecosystem == "python"],
                key=lambda d: d.name,
            ),
            sourced_files=sorted(sourced_files.values(), key=lambda d: d.path),
        ),
    )

    return manifest


# ---------------------------------------------------------------------------
# Deduplication helpers
# ---------------------------------------------------------------------------


def deduplicate_dependencies(graph: DependencyGraph) -> DependencyGraph:
    """Return a new :class:`DependencyGraph` with duplicates merged.

    Useful when combining manifests from multiple sources.  Items are
    keyed by their identity field (``id``, ``name``, or ``path``), and
    ``required_by`` lists are merged across duplicates.

    Parameters
    ----------
    graph:
        The dependency graph to deduplicate.

    Returns
    -------
    DependencyGraph
        A new graph with all duplicate entries merged.
    """
    mcp_map: Dict[str, McpServerDep] = {}
    for dep in graph.mcp_servers:
        if dep.id in mcp_map:
            _merge_mcp_server(mcp_map[dep.id], dep)
        else:
            mcp_map[dep.id] = dep

    git_map: Dict[str, GitRepoDep] = {}
    for dep in graph.git_repos:
        if dep.name in git_map:
            _merge_required_by(git_map[dep.name], dep.required_by)
        else:
            git_map[dep.name] = dep

    bin_map: Dict[str, BinaryDep] = {}
    for dep in graph.compiled_binaries:
        if dep.name in bin_map:
            _merge_required_by(bin_map[dep.name], dep.required_by)
        else:
            bin_map[dep.name] = dep

    skill_map: Dict[str, SkillTreeDep] = {}
    for dep in graph.skill_trees:
        if dep.name in skill_map:
            _merge_required_by(skill_map[dep.name], dep.required_by)
        else:
            skill_map[dep.name] = dep

    cli_map: Dict[str, CliToolDep] = {}
    for dep in graph.cli_tools:
        _merge_cli_tool_into(cli_map, dep)

    env_map: Dict[str, EnvVarDep] = {}
    for dep in graph.env_vars:
        _merge_env_var_into(env_map, dep)

    pkg_map: Dict[str, PackageDep] = {}
    for dep in graph.python_packages:
        _merge_package_into(pkg_map, dep)

    src_map: Dict[str, SourcedFileDep] = {}
    for dep in graph.sourced_files:
        _merge_sourced_file_into(src_map, dep)

    # Docker deps don't have a natural dedup key, keep as-is.
    return DependencyGraph(
        mcp_servers=sorted(mcp_map.values(), key=lambda d: d.id),
        git_repos=sorted(git_map.values(), key=lambda d: d.name),
        compiled_binaries=sorted(bin_map.values(), key=lambda d: d.name),
        skill_trees=sorted(skill_map.values(), key=lambda d: d.name),
        cli_tools=sorted(cli_map.values(), key=lambda d: d.name),
        env_vars=sorted(env_map.values(), key=lambda d: d.name),
        docker=list(graph.docker),
        python_packages=sorted(pkg_map.values(), key=lambda d: d.name),
        sourced_files=sorted(src_map.values(), key=lambda d: d.path),
    )


# ---------------------------------------------------------------------------
# Internal helpers -- merge / dedup
# ---------------------------------------------------------------------------


def _merge_required_by(target: Any, source: Any) -> None:
    """Merge ``required_by`` entries from *source* into *target* in-place.

    *source* can be a single string label, a list of strings, or an object
    with a ``required_by`` attribute.
    """
    if isinstance(source, str):
        entries = [source]
    elif isinstance(source, list):
        entries = source
    else:
        entries = getattr(source, "required_by", [])
    for entry in entries:
        if entry and entry not in target.required_by:
            target.required_by.append(entry)


def _merge_mcp_server(existing: McpServerDep, incoming: McpServerDep) -> None:
    """Merge an incoming McpServerDep into an existing one.

    The incoming entry can fill in fields that the existing entry lacks
    (e.g. when the agent scan only captured the ID but the config scan
    provides install_type, env_vars, etc.).
    """
    _merge_required_by(existing, incoming)

    # Prefer non-default / non-empty values from the incoming dep.
    if incoming.install_type != "unknown" and existing.install_type == "unknown":
        existing.install_type = incoming.install_type
    if incoming.repo_url and not existing.repo_url:
        existing.repo_url = incoming.repo_url
    if incoming.local_path and not existing.local_path:
        existing.local_path = incoming.local_path
    if incoming.package and not existing.package:
        existing.package = incoming.package
    if incoming.endpoint and not existing.endpoint:
        existing.endpoint = incoming.endpoint
    if incoming.runtime != "node" and existing.runtime == "node":
        existing.runtime = incoming.runtime
    if incoming.auth_required:
        existing.auth_required = True
    # Merge env_vars lists (names only).
    for var in incoming.env_vars:
        if var not in existing.env_vars:
            existing.env_vars.append(var)
    existing.env_vars.sort()


def _merge_cli_tools(target: Dict[str, CliToolDep], incoming: List[CliToolDep]) -> None:
    """Merge a list of CLI tool deps into *target* dict, deduplicating by name."""
    for dep in incoming:
        _merge_cli_tool_into(target, dep)


def _merge_cli_tool_into(target: Dict[str, CliToolDep], dep: CliToolDep) -> None:
    if dep.name in target:
        _merge_required_by(target[dep.name], dep)
        # Prefer non-None hints.
        if dep.version_hint and not target[dep.name].version_hint:
            target[dep.name].version_hint = dep.version_hint
        if dep.install_hint and not target[dep.name].install_hint:
            target[dep.name].install_hint = dep.install_hint
    else:
        target[dep.name] = dep


def _merge_env_vars(target: Dict[str, EnvVarDep], incoming: List[EnvVarDep]) -> None:
    for dep in incoming:
        _merge_env_var_into(target, dep)


def _merge_env_var_into(target: Dict[str, EnvVarDep], dep: EnvVarDep) -> None:
    if dep.name in target:
        _merge_required_by(target[dep.name], dep)
        if dep.description and not target[dep.name].description:
            target[dep.name].description = dep.description
        if dep.critical:
            target[dep.name].critical = True
    else:
        target[dep.name] = dep


def _merge_packages(target: Dict[str, PackageDep], incoming: List[PackageDep]) -> None:
    for dep in incoming:
        _merge_package_into(target, dep)


def _merge_package_into(target: Dict[str, PackageDep], dep: PackageDep) -> None:
    # Key by (name, ecosystem) to avoid merging python and node packages
    # with the same name.
    key = f"{dep.ecosystem}:{dep.name}"
    if key in target:
        _merge_required_by(target[key], dep)
    else:
        target[key] = dep


def _merge_sourced_files(
    target: Dict[str, SourcedFileDep], incoming: List[SourcedFileDep]
) -> None:
    for dep in incoming:
        _merge_sourced_file_into(target, dep)


def _merge_sourced_file_into(
    target: Dict[str, SourcedFileDep], dep: SourcedFileDep
) -> None:
    if dep.path in target:
        _merge_required_by(target[dep.path], dep)
    else:
        target[dep.path] = dep


def _merge_binary(target: Dict[str, BinaryDep], dep: BinaryDep) -> None:
    key = dep.path or dep.name
    if key in target:
        _merge_required_by(target[key], dep)
    else:
        target[key] = dep


def _merge_git_repo(target: Dict[str, GitRepoDep], dep: GitRepoDep) -> None:
    if dep.name in target:
        _merge_required_by(target[dep.name], dep)
    else:
        target[dep.name] = dep


# ---------------------------------------------------------------------------
# Internal helpers -- scanning
# ---------------------------------------------------------------------------


def _iter_files(directory: Path, max_depth: int = 3) -> List[Path]:
    """Recursively list files under *directory* up to *max_depth* levels.

    Skips hidden directories (starting with ``.``) except ``.preflight.yml``.
    """
    results: List[Path] = []
    _walk(directory, results, current_depth=0, max_depth=max_depth)
    return results


def _walk(
    directory: Path,
    accumulator: List[Path],
    current_depth: int,
    max_depth: int,
) -> None:
    if current_depth > max_depth:
        return
    try:
        entries = sorted(directory.iterdir())
    except OSError:
        return
    for entry in entries:
        if entry.is_file():
            accumulator.append(entry)
        elif entry.is_dir() and not entry.name.startswith("."):
            _walk(entry, accumulator, current_depth + 1, max_depth)


def _is_executable(path: Path) -> bool:
    """Return True if *path* is an executable file (not a script)."""
    if path.suffix.lower() in _SCRIPT_SUFFIXES:
        return False
    try:
        return os.access(path, os.X_OK)
    except OSError:
        return False


def _load_json_safe(path: Path) -> Optional[dict]:
    """Load a JSON file, returning None on any error."""
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        if isinstance(data, dict):
            return data
        logger.warning("JSON file %s did not contain a mapping", path)
        return None
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not load JSON from %s: %s", path, exc)
        return None


def _build_skill_tree(
    skill_dir: Path,
    label: str,
    script_results: Dict[str, list],
    pf_path: Path,
    binary_candidates: List[Path],
) -> SkillTreeDep:
    """Build a :class:`SkillTreeDep` summary for one skill directory."""
    install_script: Optional[str] = None
    for candidate_name in ("install.sh", "setup.sh", "install.py", "setup.py"):
        candidate = skill_dir / candidate_name
        if candidate.is_file():
            install_script = str(candidate)
            break

    # Compiled binaries found in the skill.
    compiled = [bp.name for bp in binary_candidates if is_elf_binary(bp)]

    # Env vars from script scan and preflight.yml.
    env_set: List[str] = [dep.name for dep in script_results.get("env_vars", [])]

    # PATH additions: look for a ``bin/`` subdirectory.
    path_additions: List[str] = []
    bin_dir = skill_dir / "bin"
    if bin_dir.is_dir():
        path_additions.append(str(bin_dir))

    # System deps from .preflight.yml (if present).
    system_deps: List[str] = []
    optional_deps: List[str] = []
    if pf_path.is_file():
        pf_config = read_preflight_yml(pf_path, required_by=label)
        system_deps = [t.name for t in pf_config.cli_tools if not t.optional]
        optional_deps = [t.name for t in pf_config.cli_tools if t.optional]

    return SkillTreeDep(
        name=label,
        install_path=str(skill_dir),
        install_script=install_script,
        system_deps=sorted(system_deps),
        optional_deps=sorted(optional_deps),
        compiled_binaries=sorted(compiled),
        env_vars_set=sorted(set(env_set)),
        path_additions=path_additions,
        required_by=[],
    )
