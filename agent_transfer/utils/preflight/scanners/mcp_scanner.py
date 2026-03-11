"""MCP server dependency scanner.

Extracts MCP server dependencies from Claude Code agent configs and
MCP settings files.  Detects install type, resolves git URLs from local
paths, and extracts env-var names (never values -- R8 compliance).

Python >= 3.8 compatible.
"""

import configparser
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from agent_transfer.utils.preflight.manifest import McpServerDep

# Patterns that signal authentication is required when found in env-var names.
_AUTH_PATTERNS = re.compile(r"KEY|TOKEN|SECRET|AUTH", re.IGNORECASE)

# Regex to pull server IDs from tool declarations like ``mcp__serverid__toolname``.
_TOOL_DECL_RE = re.compile(r"mcp__([A-Za-z0-9_-]+)__[A-Za-z0-9_]+")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_mcp_server_ids(agent_content: str) -> List[str]:
    """Extract unique MCP server IDs from agent markdown tool declarations.

    Scans *agent_content* for patterns of the form
    ``mcp__<server_id>__<tool_name>`` and returns a deduplicated, sorted list
    of server IDs.

    Parameters
    ----------
    agent_content:
        Raw text content of an agent markdown or configuration file.

    Returns
    -------
    List[str]
        Sorted list of unique server IDs found in the content.
    """
    ids = sorted(set(_TOOL_DECL_RE.findall(agent_content)))
    return ids


def scan_mcp_servers(
    mcp_config: dict,
    required_by: str = "",
) -> List[McpServerDep]:
    """Scan an MCP server config dict and return a list of ``McpServerDep``.

    The *mcp_config* dict is expected to follow the Claude Code MCP settings
    schema::

        {
          "mcpServers": {
            "<server_id>": {
              "command": "npx",
              "args": ["-y", "@modelcontextprotocol/server-github"],
              "env": {"GITHUB_TOKEN": "..."}
            },
            ...
          }
        }

    Parameters
    ----------
    mcp_config:
        Parsed JSON/YAML config dict.  Accepts both the top-level wrapper
        (with ``mcpServers`` key) and a flat dict of server entries.
    required_by:
        Label indicating which agent/config file references these servers.

    Returns
    -------
    List[McpServerDep]
        One entry per server found in *mcp_config*.
    """
    servers = _normalize_server_dict(mcp_config)
    results = []  # type: List[McpServerDep]
    for server_id, server_cfg in servers.items():
        dep = _build_server_dep(server_id, server_cfg, required_by)
        results.append(dep)
    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize_server_dict(mcp_config: dict) -> dict:
    """Return the ``{server_id: config}`` mapping regardless of nesting."""
    if "mcpServers" in mcp_config:
        return dict(mcp_config["mcpServers"])
    # Heuristic: if every value is a dict, treat as flat server map.
    if mcp_config and all(isinstance(v, dict) for v in mcp_config.values()):
        return dict(mcp_config)
    return {}


def _build_server_dep(
    server_id: str,
    cfg: dict,
    required_by: str,
) -> McpServerDep:
    """Construct a single ``McpServerDep`` from a server config block."""
    command = cfg.get("command", "")
    args = cfg.get("args", [])  # type: List[str]
    env = cfg.get("env", {})  # type: Dict[str, str]

    install_type, package, runtime = _detect_install_type(command, args, cfg)
    repo_url = _resolve_repo_url(command, args)
    local_path = _detect_local_path(command, args)
    endpoint = cfg.get("url") or cfg.get("endpoint") or None
    env_var_names = _extract_env_var_names(env)
    auth_required = _detect_auth_required(env_var_names)

    required_by_list = [required_by] if required_by else []

    return McpServerDep(
        id=server_id,
        install_type=install_type,
        repo_url=repo_url,
        local_path=local_path,
        package=package,
        endpoint=endpoint,
        runtime=runtime,
        auth_required=auth_required,
        env_vars=env_var_names,
        required_by=required_by_list,
    )


def _detect_install_type(
    command: str,
    args: List[str],
    cfg: dict,
) -> Tuple[str, Optional[str], str]:
    """Return ``(install_type, package, runtime)`` based on command+args.

    Detection order mirrors the spec priority list.
    """
    cmd_lower = command.lower()
    cmd_base = os.path.basename(command).lower()

    # npx → npm-on-demand
    if cmd_base == "npx" or "npx" in cmd_lower:
        package = _extract_npx_package(args)
        return ("npm-on-demand", package, "node")

    # bunx → bun-on-demand
    if cmd_base == "bunx" or "bunx" in cmd_lower:
        package = args[0] if args else None
        return ("bun-on-demand", package, "node")

    # python / uv → git-repo-python-venv or git-repo-uv
    if "python" in cmd_lower or cmd_base == "uv" or "uv" in cmd_lower:
        local = _detect_local_path(command, args)
        if cmd_base == "uv" or "uv" in cmd_lower:
            return ("git-repo-uv", None, "python")
        return ("git-repo-python-venv", None, "python")

    # node → git-repo-node
    if "node" in cmd_lower:
        return ("git-repo-node", None, "node")

    # docker
    if "docker" in cmd_lower:
        return ("docker", None, "docker")

    # remote SSE endpoint
    if cfg.get("url") or cfg.get("endpoint"):
        endpoint = cfg.get("url") or cfg.get("endpoint")
        return ("remote-sse", None, "remote")

    return ("unknown", None, "node")


def _extract_npx_package(args: List[str]) -> Optional[str]:
    """Extract the package name from npx args.

    Handles both ``npx <package>`` and ``npx -y <package>`` forms, as well
    as other flags that precede the package name.
    """
    # Skip known npx flags to find the actual package argument.
    skip_flags = {"-y", "--yes", "-p", "--package", "-q", "--quiet"}
    for arg in args:
        if arg in skip_flags:
            continue
        if arg.startswith("-"):
            continue
        return arg
    return None


def _detect_local_path(command: str, args: List[str]) -> Optional[str]:
    """Return the first argument that looks like a local filesystem path."""
    candidates = [command] + list(args)
    for candidate in candidates:
        if not candidate or candidate.startswith("-"):
            continue
        p = Path(candidate)
        # Heuristic: treat as local path if it's absolute or contains os.sep
        # and actually exists on disk.
        if p.is_absolute() and p.exists():
            return str(p)
    return None


def _resolve_repo_url(command: str, args: List[str]) -> Optional[str]:
    """If a local git repo path is found among command/args, extract remote URL."""
    candidates = [command] + list(args)
    for candidate in candidates:
        if not candidate or candidate.startswith("-"):
            continue
        git_config = Path(candidate) / ".git" / "config"
        if git_config.is_file():
            url = _read_git_remote_url(git_config)
            if url:
                return url
        # Also check parent directories (command might point to a script
        # inside the repo).
        parent = Path(candidate)
        for _ in range(5):
            parent = parent.parent
            gc = parent / ".git" / "config"
            if gc.is_file():
                url = _read_git_remote_url(gc)
                if url:
                    return url
                break
    return None


def _read_git_remote_url(git_config_path: Path) -> Optional[str]:
    """Read ``remote.origin.url`` from a ``.git/config`` file.

    Uses ``configparser`` with the section name ``'remote "origin"'``.
    """
    parser = configparser.ConfigParser()
    try:
        parser.read(str(git_config_path), encoding="utf-8")
    except (configparser.Error, OSError):
        return None

    section = 'remote "origin"'
    if parser.has_section(section):
        return parser.get(section, "url", fallback=None)
    return None


def _extract_env_var_names(env: dict) -> List[str]:
    """Return sorted list of env-var *names* (never values -- R8 compliance)."""
    if not env or not isinstance(env, dict):
        return []
    return sorted(env.keys())


def _detect_auth_required(env_var_names: List[str]) -> bool:
    """Return ``True`` if any env var name contains KEY, TOKEN, SECRET, or AUTH."""
    for name in env_var_names:
        if _AUTH_PATTERNS.search(name):
            return True
    return False
