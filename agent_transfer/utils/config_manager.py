"""MCP config export/import for Claude Code.

Reads MCP server definitions from BOTH:
  - ~/.claude/mcp.json (dedicated MCP config)
  - ~/.claude/settings.json (hooks, env, plugins — may also contain mcpServers)

On export: merges both sources, redacts secrets, detects runtimes.
On import: writes mcp.json for servers, merges hooks/env into settings.json.
"""

import json
import os
import re
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()

# Patterns that look like secrets/API keys
SECRET_PATTERNS = [
    re.compile(r'sk-[a-zA-Z0-9_-]{20,}'),      # OpenAI keys
    re.compile(r'[a-zA-Z0-9]{32,}'),             # Generic long tokens
    re.compile(r'key["\']?\s*[:=]\s*["\'][^"\']{16,}', re.IGNORECASE),
]

# Env var names that typically contain secrets
SECRET_ENV_KEYS = {
    'OPENAI_API_KEY', 'AZURE_API_KEY', 'ANTHROPIC_API_KEY',
    'API_KEY', 'SECRET_KEY', 'TOKEN', 'PASSWORD', 'CREDENTIALS',
    'AWS_SECRET_ACCESS_KEY', 'GITHUB_TOKEN', 'GITLAB_TOKEN',
    'SNOWFLAKE_PASSWORD', 'DATABASE_PASSWORD', 'DB_PASSWORD',
}

# Known runtime commands and how to check/install them
RUNTIME_INFO = {
    'uv': {'check': 'uv --version', 'install': 'curl -LsSf https://astral.sh/uv/install.sh | sh'},
    'npx': {'check': 'npx --version', 'install': 'npm install -g npx (requires Node.js)'},
    'node': {'check': 'node --version', 'install': 'Install Node.js from https://nodejs.org'},
    'bunx': {'check': 'bunx --version', 'install': 'curl -fsSL https://bun.sh/install | bash'},
    'bun': {'check': 'bun --version', 'install': 'curl -fsSL https://bun.sh/install | bash'},
    'docker': {'check': 'docker --version', 'install': 'Install Docker from https://docs.docker.com/get-docker/'},
    'uvx': {'check': 'uvx --version', 'install': 'curl -LsSf https://astral.sh/uv/install.sh | sh'},
    'python': {'check': 'python --version', 'install': 'Install Python from https://python.org'},
    'python3': {'check': 'python3 --version', 'install': 'Install Python from https://python.org'},
    'pip': {'check': 'pip --version', 'install': 'python -m ensurepip'},
}


def _is_secret_key(key: str) -> bool:
    """Check if an env var key name likely contains a secret."""
    key_upper = key.upper()
    for secret_key in SECRET_ENV_KEYS:
        if secret_key in key_upper:
            return True
    return False


def _redact_value(value: str) -> str:
    """Redact a secret value, keeping first/last 4 chars."""
    if len(value) <= 12:
        return '***REDACTED***'
    return value[:4] + '***REDACTED***' + value[-4:]


def _remap_path(path_str: str, source_home: str, target_home: str) -> str:
    """Remap absolute paths from source to target home directory.

    Delegates to Pathfinder.remap_path for consistent cross-module behavior.
    """
    from .pathfinder import get_pathfinder

    pf = get_pathfinder()
    result = pf.remap_path(Path(path_str), source_home, target_home)
    return str(result)


def read_mcp_json(claude_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Read ~/.claude/mcp.json — MCP server definitions."""
    if claude_dir is None:
        from .pathfinder import get_pathfinder
        claude_dir = get_pathfinder().config_dir("claude-code")

    mcp_path = claude_dir / 'mcp.json'
    if not mcp_path.exists():
        return {}

    with open(mcp_path) as f:
        return json.load(f)


def read_settings_json(claude_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Read ~/.claude/settings.json — hooks, env, plugins, etc."""
    if claude_dir is None:
        from .pathfinder import get_pathfinder
        claude_dir = get_pathfinder().config_dir("claude-code")

    settings_path = claude_dir / 'settings.json'
    if not settings_path.exists():
        return {}

    with open(settings_path) as f:
        return json.load(f)


def read_settings_local_json(claude_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Read ~/.claude/settings.local.json — permissions."""
    if claude_dir is None:
        from .pathfinder import get_pathfinder
        claude_dir = get_pathfinder().config_dir("claude-code")

    path = claude_dir / 'settings.local.json'
    if not path.exists():
        return {}

    with open(path) as f:
        return json.load(f)


def read_claude_json(home: Optional[Path] = None) -> Dict[str, Any]:
    """Read ~/.claude.json — the canonical MCP config in current Claude Code versions.

    This is distinct from ~/.claude/mcp.json (a legacy stub on most installs).
    See ARCHITECTURE.md / CLAUDE.md "MCP CONFIG LOCATION".
    """
    home = home or Path.home()
    path = home / '.claude.json'
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def get_all_mcp_servers(claude_dir: Optional[Path] = None) -> Dict[str, Dict]:
    """Get MCP servers from ALL three known sources, merged by priority.

    Sources (lowest → highest precedence):
      1. ~/.claude/settings.json `mcpServers` key
      2. ~/.claude/mcp.json (legacy)
      3. ~/.claude.json (canonical in current Claude Code) — wins on duplicates
    """
    settings_data = read_settings_json(claude_dir)
    mcp_data = read_mcp_json(claude_dir)
    claude_json_data = read_claude_json()

    servers: Dict[str, Dict] = {}
    if 'mcpServers' in settings_data:
        servers.update(settings_data['mcpServers'])
    if 'mcpServers' in mcp_data:
        servers.update(mcp_data['mcpServers'])
    if 'mcpServers' in claude_json_data:
        servers.update(claude_json_data['mcpServers'])
    return servers


def redact_secrets(servers: Dict[str, Dict], redact: bool = True) -> Dict[str, Dict]:
    """Redact secret values from MCP server env vars.

    Returns a deep copy with secrets redacted.
    """
    if not redact:
        return deepcopy(servers)

    result = deepcopy(servers)
    for name, config in result.items():
        env = config.get('env', {})
        for key, value in env.items():
            if _is_secret_key(key) and isinstance(value, str):
                env[key] = _redact_value(value)
    return result


def detect_runtimes(servers: Dict[str, Dict]) -> Dict[str, Dict[str, Any]]:
    """Detect which runtimes are needed and if they're available.

    Returns: {runtime_name: {needed: bool, available: bool, servers: [...]}}
    """
    runtimes: Dict[str, Dict[str, Any]] = {}

    for server_name, config in servers.items():
        cmd = config.get('command', '')
        # Extract the base command name (handle full paths)
        base_cmd = Path(cmd).name if '/' in cmd else cmd

        if base_cmd not in runtimes:
            runtimes[base_cmd] = {
                'needed': True,
                'available': False,
                'servers': [],
                'install_hint': RUNTIME_INFO.get(base_cmd, {}).get('install', f'Install {base_cmd}'),
            }
        runtimes[base_cmd]['servers'].append(server_name)

    # Check availability
    for runtime in runtimes:
        runtimes[runtime]['available'] = shutil.which(runtime) is not None

    return runtimes


def remap_paths(
    servers: Dict[str, Dict],
    source_home: str,
    target_home: Optional[str] = None
) -> Dict[str, Dict]:
    """Remap absolute paths in server configs from source to target home.

    Remaps: command, args, cwd
    """
    if target_home is None:
        target_home = str(Path.home())

    result = deepcopy(servers)
    for name, config in result.items():
        # Remap command
        if 'command' in config:
            config['command'] = _remap_path(config['command'], source_home, target_home)

        # Remap args
        if 'args' in config:
            config['args'] = [
                _remap_path(a, source_home, target_home) if isinstance(a, str) else a
                for a in config['args']
            ]

        # Remap cwd
        if 'cwd' in config:
            config['cwd'] = _remap_path(config['cwd'], source_home, target_home)

    return result


def export_config(
    output_file: Optional[str] = None,
    redact: bool = True,
    include_hooks: bool = True,
    include_settings: bool = True,
    include_permissions: bool = False,
) -> str:
    """Export Claude Code MCP config to a JSON file.

    Reads from both mcp.json and settings.json, packages into a single
    portable config file.

    Args:
        output_file: Output path (auto-named if None)
        redact: Redact API keys/secrets (default True)
        include_hooks: Include hooks from settings.json
        include_settings: Include env/plugins from settings.json
        include_permissions: Include permissions from settings.local.json

    Returns:
        Path to created config file
    """
    from .pathfinder import get_pathfinder
    claude_dir = get_pathfinder().config_dir("claude-code")

    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"claude-config-export_{timestamp}.json"

    # Gather data
    settings_data = read_settings_json(claude_dir)
    servers = get_all_mcp_servers(claude_dir)

    # Build export structure
    export_data: Dict[str, Any] = {
        '_metadata': {
            'created': datetime.now().isoformat(),
            'export_version': '1.0',
            'source_system': os.uname().sysname if hasattr(os, 'uname') else os.name,
            'source_user': os.getenv('USER') or os.getenv('USERNAME') or 'unknown',
            'source_home': str(Path.home()),
            'secrets_redacted': redact,
            'server_count': len(servers),
        },
        'mcpServers': redact_secrets(servers, redact=redact),
    }

    # Include hooks
    if include_hooks and 'hooks' in settings_data:
        export_data['hooks'] = settings_data['hooks']

    # Include env, plugins, other settings
    if include_settings:
        for key in ('env', 'alwaysThinkingEnabled', 'effortLevel',
                     'enabledPlugins', 'extraKnownMarketplaces'):
            if key in settings_data:
                export_data[key] = settings_data[key]

    # Include permissions
    if include_permissions:
        local_data = read_settings_local_json(claude_dir)
        if local_data:
            export_data['permissions'] = local_data.get('permissions', {})

    # Detect runtimes needed (shallow — runtime presence check)
    runtimes = detect_runtimes(servers)
    export_data['_runtimes'] = {
        name: {
            'available_on_source': info['available'],
            'servers': info['servers'],
            'install_hint': info['install_hint'],
        }
        for name, info in runtimes.items()
    }

    # Per-server classification (deep — class, capture, rewrite, install_steps)
    # See mcp_classifier.py for the 7-class taxonomy and ARCHITECTURE.md for spec.
    try:
        from dataclasses import asdict as _asdict
        from .mcp_classifier import classify_servers, summarize
        classifications = classify_servers(servers)
        export_data['_classification'] = {
            'summary': summarize(classifications),
            'servers': {c.name: _asdict(c) for c in classifications},
        }
    except Exception as exc:  # don't block export if classifier has a bug
        export_data['_classification'] = {'error': f'classifier failed: {exc!r}'}

    # Write
    output_path = Path(output_file)
    with open(output_path, 'w') as f:
        json.dump(export_data, f, indent=2)

    return str(output_path.absolute())


def import_config(
    input_file: str,
    write_mcp: bool = True,
    write_settings: bool = True,
    merge_hooks: bool = True,
    remap: bool = True,
    dry_run: bool = False,
    selected_servers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Import Claude Code MCP config from an exported JSON file.

    Writes MCP servers to mcp.json and hooks/settings to settings.json.

    Args:
        input_file: Path to exported config JSON
        write_mcp: Write MCP servers to mcp.json
        write_settings: Write hooks/env to settings.json
        merge_hooks: Merge hooks (True) or replace (False)
        remap: Remap paths from source home to target home
        dry_run: Preview changes without writing
        selected_servers: Only import these servers (None = all)

    Returns:
        Dict with import results
    """
    input_path = Path(input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"Config file not found: {input_file}")

    with open(input_path) as f:
        config_data = json.load(f)

    metadata = config_data.get('_metadata', {})
    source_home = metadata.get('source_home', '')
    target_home = str(Path.home())
    secrets_redacted = metadata.get('secrets_redacted', False)

    results: Dict[str, Any] = {
        'servers_added': 0,
        'servers_updated': 0,
        'servers_skipped': 0,
        'hooks_merged': False,
        'settings_merged': False,
        'warnings': [],
        'runtimes_missing': [],
    }

    # Get servers from export
    incoming_servers = config_data.get('mcpServers', {})

    # Filter to selected servers if specified
    if selected_servers:
        incoming_servers = {
            k: v for k, v in incoming_servers.items()
            if k in selected_servers
        }

    # Remap paths
    if remap and source_home:
        incoming_servers = remap_paths(incoming_servers, source_home, target_home)

    # Check for redacted secrets
    if secrets_redacted:
        for name, config in incoming_servers.items():
            for key, value in config.get('env', {}).items():
                if isinstance(value, str) and '***REDACTED***' in value:
                    results['warnings'].append(
                        f"Server '{name}' env '{key}' has a redacted secret — "
                        f"you'll need to fill it in manually after import"
                    )

    # Check runtimes
    runtimes = detect_runtimes(incoming_servers)
    for runtime, info in runtimes.items():
        if not info['available']:
            results['runtimes_missing'].append({
                'runtime': runtime,
                'servers': info['servers'],
                'install_hint': info['install_hint'],
            })

    from .pathfinder import get_pathfinder
    claude_dir = get_pathfinder().config_dir("claude-code")
    claude_dir.mkdir(parents=True, exist_ok=True)

    if dry_run:
        results['servers_would_add'] = len(incoming_servers)
        return results

    # --- Write MCP servers to mcp.json ---
    if write_mcp and incoming_servers:
        mcp_path = claude_dir / 'mcp.json'
        existing_mcp = read_mcp_json(claude_dir)
        existing_servers = existing_mcp.get('mcpServers', {})

        for name, config in incoming_servers.items():
            if name in existing_servers:
                existing_servers[name] = config
                results['servers_updated'] += 1
            else:
                existing_servers[name] = config
                results['servers_added'] += 1

        # Write back
        mcp_output = {'mcpServers': existing_servers}
        with open(mcp_path, 'w') as f:
            json.dump(mcp_output, f, indent=2)

    # --- Merge hooks/settings into settings.json ---
    if write_settings:
        settings_path = claude_dir / 'settings.json'
        existing_settings = read_settings_json(claude_dir)

        # Merge hooks
        if merge_hooks and 'hooks' in config_data:
            incoming_hooks = config_data['hooks']
            existing_hooks = existing_settings.get('hooks', {})

            for hook_type, hook_list in incoming_hooks.items():
                if hook_type not in existing_hooks:
                    existing_hooks[hook_type] = hook_list
                # If already exists, don't overwrite — user's hooks take priority
                # They can use --no-merge-hooks to replace entirely

            existing_settings['hooks'] = existing_hooks
            results['hooks_merged'] = True

        # Merge env
        if 'env' in config_data:
            existing_env = existing_settings.get('env', {})
            for key, value in config_data['env'].items():
                if key not in existing_env:
                    existing_env[key] = value
            existing_settings['env'] = existing_env
            results['settings_merged'] = True

        # Merge plugins
        if 'enabledPlugins' in config_data:
            existing_plugins = existing_settings.get('enabledPlugins', {})
            existing_plugins.update(config_data['enabledPlugins'])
            existing_settings['enabledPlugins'] = existing_plugins

        # Write settings back
        with open(settings_path, 'w') as f:
            json.dump(existing_settings, f, indent=2)

    return results


def display_config_preview(config_data: Dict[str, Any]) -> None:
    """Display a rich preview of config data before import."""
    metadata = config_data.get('_metadata', {})
    servers = config_data.get('mcpServers', {})

    # Metadata panel
    console.print(Panel(
        f"[bold]Source:[/bold] {metadata.get('source_user', '?')}@{metadata.get('source_system', '?')}\n"
        f"[bold]Home:[/bold] {metadata.get('source_home', '?')}\n"
        f"[bold]Created:[/bold] {metadata.get('created', '?')}\n"
        f"[bold]Secrets:[/bold] {'Redacted' if metadata.get('secrets_redacted') else 'Included'}\n"
        f"[bold]Servers:[/bold] {len(servers)}",
        title="Config Export Info",
        border_style="cyan"
    ))

    # Server table
    table = Table(title=f"MCP Servers ({len(servers)})", box=box.ROUNDED)
    table.add_column("#", width=3, justify="right")
    table.add_column("Name", style="cyan", width=25)
    table.add_column("Command", width=20)
    table.add_column("Env Vars", width=15)
    table.add_column("Has CWD", width=8, justify="center")

    for idx, (name, config) in enumerate(sorted(servers.items()), 1):
        cmd = config.get('command', '?')
        cmd_base = Path(cmd).name if '/' in cmd else cmd
        env_count = len(config.get('env', {}))
        env_str = f"{env_count} vars" if env_count else "[dim]none[/dim]"
        has_cwd = "[green]Yes[/green]" if config.get('cwd') else "[dim]No[/dim]"

        # Check for redacted secrets
        has_redacted = any(
            '***REDACTED***' in str(v)
            for v in config.get('env', {}).values()
        )
        if has_redacted:
            env_str += " [yellow](redacted)[/yellow]"

        table.add_row(str(idx), name, cmd_base, env_str, has_cwd)

    console.print(table)

    # Hooks info
    if 'hooks' in config_data:
        hooks = config_data['hooks']
        hook_types = list(hooks.keys())
        console.print(f"\n[bold]Hooks:[/bold] {len(hook_types)} types — {', '.join(hook_types)}")

    # Runtime warnings
    runtimes = config_data.get('_runtimes', {})
    missing = [name for name, info in runtimes.items() if not info.get('available_on_source')]
    if missing:
        console.print(f"\n[yellow]Runtimes not available on source:[/yellow] {', '.join(missing)}")


def display_import_results(results: Dict[str, Any]) -> None:
    """Display import results with rich formatting."""
    lines = []
    if results.get('servers_added', 0) > 0:
        lines.append(f"[green]Servers added:[/green] {results['servers_added']}")
    if results.get('servers_updated', 0) > 0:
        lines.append(f"[yellow]Servers updated:[/yellow] {results['servers_updated']}")
    if results.get('servers_skipped', 0) > 0:
        lines.append(f"[dim]Servers skipped:[/dim] {results['servers_skipped']}")
    if results.get('hooks_merged'):
        lines.append("[green]Hooks merged into settings.json[/green]")
    if results.get('settings_merged'):
        lines.append("[green]Env/plugins merged into settings.json[/green]")

    console.print(Panel(
        "\n".join(lines) if lines else "[dim]No changes made[/dim]",
        title="Import Complete",
        border_style="green"
    ))

    # Warnings
    for warning in results.get('warnings', []):
        console.print(f"[yellow]Warning:[/yellow] {warning}")

    # Missing runtimes
    for rt in results.get('runtimes_missing', []):
        console.print(
            f"[red]Missing runtime:[/red] {rt['runtime']} "
            f"(needed by: {', '.join(rt['servers'])})"
        )
        console.print(f"  [dim]Install: {rt['install_hint']}[/dim]")


# ============================================================================
# AgentBridge MVP (003) — T016 / FR-006
# ============================================================================
# Capability-shaped output — emit a list of AssetEntry alongside the existing
# config dict. The new bridge/compose.py walks ~/.claude/ and calls this
# helper to convert raw filesystem paths into manifest-ready AssetEntry.
#
# Constitution: R4 (wrap, don't rewrite) — no existing callers are touched.
#               R5 (backward compat) — additive only.

import hashlib as _hashlib  # noqa: E402
import os as _os  # noqa: E402
from typing import List as _List, Optional as _Optional, Dict as _Dict  # noqa: E402


def _sha256_of(path: Path) -> str:
    h = _hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except OSError:
        return "0" * 64
    return h.hexdigest()


def _file_mode(path: Path) -> int:
    try:
        return _os.stat(path).st_mode & 0o7777
    except OSError:
        return 0o644


def emit_asset_entries(
    paths: _List[Path],
    risk_for: _Optional[_Dict[str, str]] = None,
    conflict_for: _Optional[_Dict[str, str]] = None,
    home: _Optional[Path] = None,
) -> _List[_Dict]:
    """Convert a list of filesystem paths to dicts shaped like AssetEntry.

    Args:
        paths: Absolute paths to bundle.
        risk_for: Optional override map { abs_path_str -> "green"|"yellow"|"red" }.
                  If absent or missing a key, default risk is "yellow" for files
                  inside ~/.claude/ and "red" for ~/bin scripts.
        conflict_for: Optional override map { abs_path_str -> conflict_policy }.
                      Defaults: "merge" for *.json/*.md inside ~/.claude/, "ask"
                      for ~/bin scripts, "overwrite" for everything else.
        home: Override of $HOME for portability in tests.

    Returns:
        List of dicts compatible with bridge.models.AssetEntry. Caller is
        responsible for converting to the Pydantic model.
    """
    home = home or Path.home()
    risk_for = risk_for or {}
    conflict_for = conflict_for or {}
    home_str = str(home)
    bin_dirs = (str(home / "bin"), str(home / ".local" / "bin"))

    out: _List[_Dict] = []
    for p in paths:
        abs_str = str(p.resolve())
        if any(abs_str.startswith(b + "/") for b in bin_dirs):
            default_risk = "red"
            default_conflict = "ask"
        elif abs_str.endswith(".json") or abs_str.endswith(".md"):
            default_risk = "yellow"
            default_conflict = "merge"
        else:
            default_risk = "yellow"
            default_conflict = "overwrite"

        # Make destination path home-relative for portability.
        if abs_str.startswith(home_str + "/"):
            dest_path = "~" + abs_str[len(home_str):]
        else:
            dest_path = abs_str

        out.append({
            "path": _os.path.relpath(abs_str, home_str) if abs_str.startswith(home_str + "/") else _os.path.basename(abs_str),
            "dest_path": dest_path,
            "risk": risk_for.get(abs_str, default_risk),
            "conflict": conflict_for.get(abs_str, default_conflict),
            "sha256": _sha256_of(p),
            "mode_bits": _file_mode(p),
            "notes": None,
        })
    return out
