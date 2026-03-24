# Contract: Preflight API

**Branch**: `002-preflight-check` | **Date**: 2026-03-11

## Public API — `agent_transfer.utils.preflight`

### Collector (source-side)

```python
def collect_inventory(
    agents: list[Path],
    skills: list[Path],
    hooks: list[Path],
    configs: list[Path],
    platform: str = "claude-code",
) -> TransferManifest:
    """Scan agents, skills, hooks, configs and build a complete dependency manifest.

    Args:
        agents: Paths to agent .md files to include
        skills: Paths to skill directories to include
        hooks: Paths to hook files/directories to include
        configs: Paths to config files to include
        platform: Source platform slug

    Returns:
        TransferManifest with all auto-detected + author-declared dependencies
    """
```

### Manifest I/O

```python
def write_manifest(manifest: TransferManifest, path: Path) -> None:
    """Write manifest to JSON file."""

def read_manifest(path: Path) -> TransferManifest:
    """Read manifest from JSON file. Raises ValueError on invalid schema."""

def read_manifest_from_archive(archive_path: Path) -> Optional[TransferManifest]:
    """Extract and read manifest.json from a tar.gz archive.
    Returns None if no manifest found (legacy archive)."""
```

### Checker (target-side)

```python
def run_preflight_checks(
    manifest: TransferManifest,
) -> ReadinessReport:
    """Run all dependency checks against the local environment.

    Checks (in order):
    1. MCP server configuration
    2. CLI tool availability (PATH lookup)
    3. Environment variable presence (NEVER values)
    4. Git repo directory existence
    5. Compiled binary existence + architecture match
    6. Skill tree existence + system deps
    7. Docker availability
    8. Python/Node package availability
    9. Sourced file existence

    Returns:
        ReadinessReport with per-dependency GREEN/YELLOW/RED status
    """
```

### Report

```python
def display_readiness_report(report: ReadinessReport) -> None:
    """Print Rich-formatted readiness report to terminal."""

def report_to_json(report: ReadinessReport) -> str:
    """Serialize report to JSON string for --json flag."""
```

## CLI Contract

### New command: `preflight`

```
agent-transfer preflight <archive>    # Check archive against local env
agent-transfer preflight --self       # Audit local env (no archive needed)
agent-transfer preflight --json       # Machine-readable output
```

**Exit codes**:
- `0` — All GREEN or YELLOW (safe to import)
- `1` — Any RED items (import would have issues)

### Modified command: `export`

```
agent-transfer export [existing flags]
```

**Change**: Export now automatically runs `collect_inventory()` and bundles `manifest.json` at archive root. No new flags needed.

### Modified command: `import`

```
agent-transfer import <archive> [existing flags] [--force]
```

**Change**: Import now reads `manifest.json` (if present), runs `run_preflight_checks()`, displays report, and:
- All GREEN: Proceeds silently
- Any YELLOW: Shows warning, proceeds
- Any RED: Shows report, prompts user to continue/abort (unless `--force`)
- No manifest: Shows "legacy archive" warning, proceeds

## Manifest JSON Schema (v2.0)

```json
{
  "$schema": "manifest-v2.0",
  "manifest_version": "2.0",
  "created_at": "ISO 8601",
  "source_platform": "string",
  "source_os": "string",
  "source_arch": "string",
  "source_home": "string",
  "contents": {
    "agents": ["string"],
    "skills": ["string"],
    "hooks": ["string"],
    "configs": ["string"]
  },
  "dependencies": {
    "mcp_servers": [{"id": "string", "install_type": "string", ...}],
    "git_repos": [{"name": "string", "repo_url": "string", ...}],
    "compiled_binaries": [{"name": "string", "arch": "string", ...}],
    "skill_trees": [{"name": "string", "install_path": "string", ...}],
    "cli_tools": [{"name": "string", ...}],
    "env_vars": [{"name": "string", "critical": "boolean", ...}],
    "docker": [{"type": "string", ...}],
    "python_packages": [{"name": "string", ...}],
    "sourced_files": [{"path": "string", ...}]
  }
}
```

## `.preflight.yml` Schema

```yaml
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
```
