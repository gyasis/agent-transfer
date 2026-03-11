# Data Model: Preflight Check

**Branch**: `002-preflight-check` | **Date**: 2026-03-11

## Core Entities

### TransferManifest

The root document bundled in export archives. Describes everything the target machine needs.

**Attributes**:
- `manifest_version`: str — Schema version (currently "2.0")
- `created_at`: str — ISO 8601 timestamp
- `source_platform`: str — Platform slug (e.g., "claude-code")
- `source_os`: str — OS name (e.g., "linux")
- `source_arch`: str — CPU architecture (e.g., "x86_64")
- `source_home`: str — Home directory path on source machine
- `contents`: ContentsInventory — What's in the archive
- `dependencies`: DependencyGraph — What the target needs

### ContentsInventory

Itemized list of what's physically in the archive.

**Attributes**:
- `agents`: list[str] — Agent filenames
- `skills`: list[str] — Skill directory names
- `hooks`: list[str] — Hook file paths (relative)
- `configs`: list[str] — Config file names

### DependencyGraph

All external requirements organized by category.

**Attributes**:
- `mcp_servers`: list[McpServerDep]
- `git_repos`: list[GitRepoDep]
- `compiled_binaries`: list[BinaryDep]
- `skill_trees`: list[SkillTreeDep]
- `cli_tools`: list[CliToolDep]
- `env_vars`: list[EnvVarDep]
- `docker`: list[DockerDep]
- `python_packages`: list[PackageDep]
- `sourced_files`: list[SourcedFileDep]

### McpServerDep

An MCP server dependency with installation provenance.

**Attributes**:
- `id`: str — Server identifier (e.g., "graphiti")
- `install_type`: str — One of: "npm-on-demand", "bun-on-demand", "git-repo-python-venv", "git-repo-uv", "git-repo-node", "remote-sse", "docker", "unknown"
- `repo_url`: Optional[str] — Git remote URL if applicable
- `local_path`: Optional[str] — Expected local path
- `package`: Optional[str] — npm/bun package name if on-demand
- `endpoint`: Optional[str] — Remote SSE endpoint if applicable
- `setup_commands`: list[str] — Commands to set up from scratch
- `runtime`: str — Required runtime ("node", "python", "uv", "bun", "docker")
- `auth_required`: bool — Whether auth tokens are needed
- `env_vars`: list[str] — Env var names from server config `env` block
- `required_by`: list[str] — Agent/skill names that need this server

### GitRepoDep

A git repository that needs to be cloned on the target.

**Attributes**:
- `name`: str — Repository name
- `repo_url`: str — Git remote URL
- `local_path`: str — Expected clone path (tilde-prefixed)
- `setup_method`: str — One of: "python-venv", "uv", "npm", "cargo", "docker", "pip"
- `setup_commands`: list[str] — Ordered setup commands
- `required_by`: list[str] — What depends on this repo

### BinaryDep

A compiled binary with architecture metadata.

**Attributes**:
- `name`: str — Binary name
- `path`: str — Expected path (tilde-prefixed)
- `arch`: str — Source architecture (e.g., "x86_64")
- `os`: str — Source OS
- `source_lang`: Optional[str] — "rust", "go", "c", etc.
- `build_command`: Optional[str] — How to recompile
- `source_repo`: Optional[str] — Git URL for source code
- `required_by`: list[str]

### SkillTreeDep

A self-contained skill installation tree.

**Attributes**:
- `name`: str — Skill tree name (e.g., "dev-kid")
- `install_path`: str — Root install path (tilde-prefixed)
- `install_script`: Optional[str] — Relative path to install script
- `system_deps`: list[str] — Required system tools (with optional version hints)
- `optional_deps`: list[str] — Optional tools
- `compiled_binaries`: list[str] — Relative paths to binaries within the tree
- `env_vars_set`: list[str] — Env vars the tree sets
- `path_additions`: list[str] — PATH entries the tree requires
- `required_by`: list[str]

### CliToolDep

A CLI tool expected on the system PATH.

**Attributes**:
- `name`: str — Tool name (e.g., "jq", "uv", "node")
- `version_hint`: Optional[str] — Version requirement (e.g., ">=18")
- `install_hint`: Optional[str] — Installation command
- `optional`: bool — Whether the tool is optional
- `required_by`: list[str]

### EnvVarDep

An environment variable dependency.

**Attributes**:
- `name`: str — Variable name (NEVER the value)
- `description`: Optional[str] — What it's for (from `.preflight.yml`)
- `critical`: bool — Whether missing it causes hard failure
- `required_by`: list[str]

### DockerDep

A Docker/container dependency.

**Attributes**:
- `type`: str — "compose", "image", or "dockerfile"
- `file`: Optional[str] — Path to Dockerfile or compose file
- `image`: Optional[str] — Docker image name
- `services`: list[str] — Compose service names
- `required_by`: list[str]

### PackageDep

A Python or Node package dependency.

**Attributes**:
- `name`: str — Package name
- `version_hint`: Optional[str]
- `ecosystem`: str — "python" or "node"
- `required_by`: list[str]

### SourcedFileDep

A file sourced/imported by a script.

**Attributes**:
- `path`: str — File path (may be tilde-prefixed)
- `required_by`: list[str]

---

## Checker Output Entities

### CheckResult

Result of checking a single dependency.

**Attributes**:
- `dependency`: DependencyEntry (any of the above types)
- `status`: str — "GREEN", "YELLOW", "RED"
- `message`: str — Human-readable explanation
- `remediation`: Optional[str] — Actionable fix command/instruction

### ReadinessReport

Aggregated results of all checks.

**Attributes**:
- `manifest`: TransferManifest — The manifest that was checked
- `target_os`: str — Target machine OS
- `target_arch`: str — Target machine architecture
- `results`: dict[str, list[CheckResult]] — Results keyed by category name
- `overall_status`: str — "PASS", "WARN", "FAIL"
- `green_count`: int
- `yellow_count`: int
- `red_count`: int
- `manual_checklist`: list[str] — Items requiring human verification

---

## Relationships

```
TransferManifest
  ├── ContentsInventory
  └── DependencyGraph
        ├── McpServerDep ──references──▶ GitRepoDep (via repo_url)
        ├── GitRepoDep
        ├── BinaryDep
        ├── SkillTreeDep ──contains──▶ BinaryDep (via compiled_binaries)
        ├── CliToolDep
        ├── EnvVarDep
        ├── DockerDep
        ├── PackageDep
        └── SourcedFileDep

ReadinessReport
  ├── TransferManifest (input)
  └── CheckResult[] (per dependency)
```

## PreflightConfig (`.preflight.yml`)

Optional author-provided dependency declaration merged with auto-detection.

**Attributes**:
- `dependencies`: dict — Same categories as DependencyGraph but author-declared
  - `cli_tools`: list[dict] — name, install_hint, version_hint
  - `env_vars`: list[dict] — name, description
  - `packages`: list[dict] — name, ecosystem
- `notes`: list[str] — Human-readable notes for the Manual Checklist
