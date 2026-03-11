# PRD: Preflight Check — Agentic Transfer Readiness Validation

**Author:** Gyasi Sutton
**Date:** 2026-03-11
**Status:** Draft
**Parent PRD:** `prd/agent-transfer-v2-platform-agnostic.md`
**Depends on:** Pathfinder Module (`agent_transfer/utils/pathfinder.py`)

---

## 1. Problem Statement

When transferring agents, skills, and configurations between machines using `agent-transfer`, the **target machine is often unprepared**. Common failures after import:

1. **Missing MCP servers** — Agents reference `mcp__graphiti__search_nodes` but the target has no Graphiti server configured. The agent loads but silently fails at runtime.
2. **Missing CLI tools** — Skills reference `snowsql`, `gh`, `uv`, `node`, `jq` in their scripts, but those aren't installed on the target. Skills appear imported but break on first use.
3. **Missing environment variables** — Hooks and scripts depend on `SNOWFLAKE_ACCOUNT`, `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, etc. No warning until runtime failure.
4. **Script dependencies** — Skills contain bash scripts that `source` other files, use `pip install`, or reference absolute paths from the source machine.
5. **Hook dependencies** — Pre/post tool hooks reference executables or scripts that don't exist on the target.
6. **No feedback loop** — The user exports from Machine A, imports on Machine B, and only discovers problems days later when something breaks mid-task.

### What exists today

- `tool_checker.py` checks MCP tool availability for agents (partial — tools only, not scripts/env/CLI)
- `check-ready` CLI command validates skill archives (partial — checks skill structure, not runtime deps)
- `validate-tools` CLI command checks agent tool compatibility (partial — MCP servers only)

These are fragments. There is no **unified preflight system** that inventories everything on the source, bundles a manifest with the export, and validates everything on the target before committing the import.

---

## 2. Vision

A **two-sided readiness system** that makes transfers reliable:

**Source side (export):** Automatically inventories all dependencies — MCP servers, CLI tools, env vars, script imports, hooks — and bundles a machine-readable **transfer manifest** (`manifest.json`) into the export archive.

**Target side (import):** Before writing any files, reads the manifest, checks every dependency against the local environment, and produces a **readiness report** — green/yellow/red for each dependency. Blocks import (or warns) on red items. Offers remediation hints for missing dependencies.

**As a Claude Code skill:** `agent-transfer preflight` can be run standalone at any time to audit the current machine's readiness to receive a specific archive — or to audit what would need to exist on a target machine if you exported right now.

```
Machine A (source)                    Machine B (target)
┌─────────────────────┐               ┌─────────────────────┐
│  agent-transfer     │               │  agent-transfer     │
│  export             │               │  import             │
│       │             │               │       │             │
│       ▼             │               │       ▼             │
│  ┌──────────┐       │               │  ┌──────────┐       │
│  │ Inventory │       │               │  │ Preflight│       │
│  │ Collector │       │               │  │ Checker  │       │
│  └────┬─────┘       │               │  └────┬─────┘       │
│       ▼             │               │       ▼             │
│  manifest.json      │   scp/git     │  Readiness Report   │
│  (in archive)  ─────┼──────────────▶│  ✅ MCP: 12/12      │
│                     │               │  ⚠️  CLI: 8/10       │
│                     │               │  ❌ Env: 3/7         │
│                     │               │  → "Install snowsql" │
└─────────────────────┘               └─────────────────────┘
```

---

## 3. Scope

### In Scope

- **Inventory collector** — Scans agents, skills, hooks, and configs to extract all external dependencies
- **Transfer manifest** (`manifest.json`) — Machine-readable dependency list bundled with exports
- **Preflight checker** — Validates target environment against manifest before import
- **Readiness report** — Rich terminal output with green/yellow/red status per dependency
- **Remediation hints** — Actionable suggestions for each missing dependency
- **CLI integration** — `agent-transfer preflight <archive>` command and pre-import hook
- **Claude Code skill** — `/preflight` skill for interactive readiness checking

### Out of Scope

- Automatic installation of missing dependencies (too risky — just report and suggest)
- Cross-platform conversion validation (that's the IR/AIM system from v2 PRD)
- Network-based validation (checking remote machine — only checks local)
- MCP server health checks (only checks if configured, not if running)

---

## 4. Dependency Categories

### 4.1 MCP Servers (with installation provenance)

MCP servers aren't just config entries — they have **installation methods** that the target machine must replicate. The manifest must capture HOW each server is installed, not just that it exists.

**Real-world MCP installation types observed:**

| Type | Example | What target needs |
|------|---------|-------------------|
| **npm on-demand** | `npx -y @modelcontextprotocol/server-sequential-thinking` | `node` + `npx` (auto-downloads) |
| **bun on-demand** | `bunx -y @upstash/context7-mcp@latest` | `bun` runtime |
| **Remote SSE** | `npx mcp-remote https://mcp.atlassian.com/v1/sse` | `node` + network access + auth tokens |
| **Git repo + Python venv** | `~/dev/gemini-mcp/.venv/bin/python server.py` | `git clone` repo + `python -m venv` + `pip install` |
| **Git repo + uv + FastMCP** | `uv run --directory ~/dev/tableau-mcp fastmcp run` | `git clone` repo + `uv` installed |
| **Git repo + Node.js** | `node ~/dev/tools/playwright-mcp/cli.js` | `git clone` repo + `npm install` |
| **Docker container** | `docker run -p 8080:8080 mcp-server` | `docker` + image pull |

**Source:** Parse agent `.md` files for `mcp__<server>__<tool>` patterns. Then cross-reference against MCP config files (`mcp.json`, `settings.json`, `.gemini/settings.json`) to extract:
- Server ID
- Command + args (reveals installation type)
- Git repo URL (if local path, resolve via `.git/config` remote)
- Required runtimes (`node`, `python`, `uv`, `bun`, `docker`)
- Environment variables in `env` block

**Check on target:**
1. Is the MCP server ID configured? (existing `tool_checker.py` logic)
2. If not configured, can we suggest how to install it? (git clone URL + setup commands)
3. Are the required runtimes available? (`node`, `uv`, `python`, `bun`, `docker`)

**Severity:** RED if agent references tools from unconfigured server. YELLOW if server configured but runtime deps unclear.

### 4.2 Git Repository Dependencies

Many MCP servers and skill trees live in **cloned git repos**. The manifest must capture repo URLs so the target machine can clone them.

**Source:** For each MCP server or skill that references a local path under `~/dev/`:
- Read `<path>/.git/config` to extract `[remote "origin"]` URL
- Detect setup method: presence of `pyproject.toml` (uv/pip), `package.json` (npm), `Cargo.toml` (cargo), `Dockerfile` (docker)
- Detect virtualenv: `.venv/`, `venv/`, `node_modules/`

**Manifest entry:**
```json
{
  "name": "gemini-mcp",
  "repo_url": "https://github.com/gyasis/gemini-mcp.git",
  "local_path": "~/dev/gemini-mcp",
  "setup_method": "python-venv",
  "setup_commands": ["git clone https://github.com/gyasis/gemini-mcp.git", "cd gemini-mcp && python -m venv .venv && pip install -e ."],
  "required_by": ["gemini-mcp MCP server"]
}
```

**Check on target:** Does `local_path` exist? If not, provide `git clone` + setup commands.
**Severity:** RED if required by an MCP server that agents depend on. YELLOW if optional.

### 4.3 Compiled Binaries and Architecture

Skills may include **compiled binaries** that are architecture-dependent (e.g., dev-kid's Rust `task-watchdog`).

**Real-world example:** `~/.dev-kid/rust-watchdog/target/release/task-watchdog` is an ELF x86-64 binary. Transferring to ARM Linux or macOS requires recompilation from source.

**Source:** Scan skill directories for:
- ELF/Mach-O binaries (detect via `file` command or magic bytes)
- `Cargo.toml` (Rust — needs `cargo build --release`)
- Go binaries (needs `go build`)
- Any file with execute permissions that isn't a script

**Manifest entry:**
```json
{
  "name": "task-watchdog",
  "type": "compiled-binary",
  "arch": "x86-64",
  "os": "linux",
  "source_lang": "rust",
  "build_command": "cargo build --release",
  "source_available": false,
  "required_by": ["dev-kid watchdog-start"]
}
```

**Check on target:**
1. Does binary exist at expected path?
2. Architecture match? (`uname -m` on target vs manifest `arch`)
3. If mismatch: Is source code available for recompilation? Is compiler installed?

**Severity:** RED if architecture mismatch and no source. YELLOW if mismatch but source + compiler available.

### 4.4 CLI Tools

**Source:** Parse skill scripts (`.sh`, `.py`, `.js`) for external commands. Detect via:
- Shebang lines (`#!/usr/bin/env node`)
- Direct invocations (`snowsql`, `gh`, `jq`, `uv`, `npm`, `docker`, `cargo`)
- `command -v` / `which` checks in scripts
- Version requirements (e.g., `python3 >= 3.7` from install scripts)

**Check:** `shutil.which()` on target for each CLI tool.
**Severity:** RED if skill script requires missing tool. YELLOW if referenced in optional path.

### 4.5 Environment Variables

**Source:** Parse scripts and configs for `$VAR`, `${VAR}`, `os.environ["VAR"]`, `process.env.VAR`. Also extract from MCP server `env` blocks in config files.
**Check:** `os.environ.get()` on target.
**Severity:** RED for known-critical vars (API keys, connection strings). YELLOW for others.
**Privacy:** NEVER log variable values — only names and presence/absence.

### 4.6 Skill Tree Dependencies (self-contained installations)

Some skills are **entire installation trees** with their own directory structures, scripts, templates, and compiled binaries (e.g., `~/.dev-kid/` with `cli/`, `scripts/`, `skills/`, `templates/`, `rust-watchdog/`).

**Source:** Detect skill trees by:
- Skills that reference a `*_ROOT` env var (e.g., `DEV_KID_ROOT`)
- Skills with `install.sh` or `setup.sh` scripts
- Skills with nested subdirectories beyond a single SKILL.md

**Manifest entry:**
```json
{
  "name": "dev-kid",
  "type": "skill-tree",
  "install_path": "~/.dev-kid",
  "install_script": "scripts/install.sh",
  "system_deps": ["bash", "git", "python3>=3.7", "jq"],
  "optional_deps": ["cargo"],
  "compiled_binaries": ["rust-watchdog/target/release/task-watchdog"],
  "env_vars_set": ["DEV_KID_ROOT"],
  "required_by": ["devkid.execute", "devkid.orchestrate"]
}
```

**Check on target:** Does install path exist? Run `install.sh --check` if available. Validate system deps.
**Severity:** RED if skill tree missing entirely. YELLOW if present but deps incomplete.

### 4.7 Docker/Container Dependencies

**Source:** Scan for `Dockerfile`, `docker-compose.yml`, `docker-compose.yaml` in skill directories and MCP server repos. Also detect `docker run` commands in scripts.
**Check:** `docker` CLI available? `docker compose` available? Required images pullable?
**Severity:** RED if docker required but not installed. YELLOW if docker present but images not pre-pulled.

### 4.8 Script Dependencies

**Source:** Parse bash scripts for `source`, `.` (dot-source), `pip install`, `npm install`, `import` in Python scripts.
**Check:** File existence for sourced files. Package availability for pip/npm.
**Severity:** YELLOW — scripts may have conditional paths.

### 4.9 Hooks

**Source:** Parse `.claude/hooks/` for pre/post tool hooks. Extract referenced executables and scripts.
**Check:** Executable existence and permissions on target.
**Severity:** RED if hook executable missing (hook will silently fail).

### 4.10 Path References

**Source:** Scan for absolute paths in configs and scripts (already handled by pathfinder's `remap_path`).
**Check:** Flag any absolute paths that don't exist on target after remapping.
**Severity:** YELLOW — pathfinder should handle most of these.

---

## 5. Transfer Manifest Format

```json
{
  "manifest_version": "2.0",
  "created_at": "2026-03-11T14:30:00Z",
  "source_platform": "claude-code",
  "source_os": "linux",
  "source_arch": "x86_64",
  "source_home": "/home/gyasi",

  "contents": {
    "agents": ["architect-reviewer.md", "python-pro.md"],
    "skills": ["speckit/", "devkid/", "session-review/"],
    "hooks": ["pre-tool-use/batch-guard.js"],
    "configs": ["mcp_servers.json", "settings.json"]
  },

  "dependencies": {
    "mcp_servers": [
      {
        "id": "graphiti",
        "install_type": "git-repo-python",
        "repo_url": "https://github.com/gyasis/graphiti-mcp.git",
        "local_path": "~/dev/tools/graphiti-mcp",
        "setup_commands": ["git clone <repo>", "cd graphiti-mcp && uv sync"],
        "runtime": "uv",
        "required_by": ["architect-reviewer.md"]
      },
      {
        "id": "context7-mcp",
        "install_type": "npm-on-demand",
        "package": "@upstash/context7-mcp@latest",
        "runtime": "bun",
        "required_by": ["python-pro.md"]
      },
      {
        "id": "gemini-mcp",
        "install_type": "git-repo-python",
        "repo_url": "https://github.com/gyasis/gemini-mcp.git",
        "local_path": "~/dev/gemini-mcp",
        "setup_commands": ["git clone <repo>", "cd gemini-mcp && python -m venv .venv && pip install -e ."],
        "runtime": "python",
        "required_by": ["gemini-mcp agents"]
      },
      {
        "id": "playwright",
        "install_type": "git-repo-node",
        "repo_url": "https://github.com/gyasis/playwright-mcp.git",
        "local_path": "~/dev/tools/playwright-mcp",
        "setup_commands": ["git clone <repo>", "cd playwright-mcp && npm install"],
        "runtime": "node",
        "required_by": ["frontend-developer.md"]
      },
      {
        "id": "atlassian-remote",
        "install_type": "remote-sse",
        "endpoint": "https://mcp.atlassian.com/v1/sse",
        "runtime": "node",
        "auth_required": true,
        "required_by": ["jira-issue-workspace.md"]
      }
    ],

    "git_repos": [
      {
        "name": "gemini-mcp",
        "repo_url": "https://github.com/gyasis/gemini-mcp.git",
        "local_path": "~/dev/gemini-mcp",
        "setup_method": "python-venv",
        "setup_commands": ["git clone https://github.com/gyasis/gemini-mcp.git", "cd gemini-mcp && python -m venv .venv && pip install -e ."],
        "required_by": ["gemini-mcp MCP server"]
      },
      {
        "name": "tableau-mcp",
        "repo_url": "https://gitlab.com/proddev4/data/tableau-mcp.git",
        "local_path": "~/dev/tableau-mcp",
        "setup_method": "uv",
        "setup_commands": ["git clone https://gitlab.com/proddev4/data/tableau-mcp.git", "cd tableau-mcp && uv sync"],
        "required_by": ["tableau-mcp MCP server"]
      }
    ],

    "compiled_binaries": [
      {
        "name": "task-watchdog",
        "path": "~/.dev-kid/rust-watchdog/target/release/task-watchdog",
        "arch": "x86_64",
        "os": "linux",
        "source_lang": "rust",
        "build_command": "cargo build --release",
        "source_repo": null,
        "required_by": ["dev-kid watchdog-start"]
      }
    ],

    "skill_trees": [
      {
        "name": "dev-kid",
        "install_path": "~/.dev-kid",
        "install_script": "scripts/install.sh",
        "system_deps": ["bash", "git", "python3>=3.7", "jq"],
        "optional_deps": ["cargo"],
        "compiled_binaries": ["rust-watchdog/target/release/task-watchdog"],
        "env_vars_set": ["DEV_KID_ROOT"],
        "path_additions": ["$HOME/.dev-kid/cli"],
        "required_by": ["devkid.execute", "devkid.orchestrate", "devkid.checkpoint"]
      }
    ],

    "cli_tools": [
      {"name": "node", "version_hint": ">=18", "required_by": ["batch-guard.js", "playwright MCP"]},
      {"name": "bun", "required_by": ["context7-mcp"]},
      {"name": "uv", "required_by": ["speckit/", "tableau-mcp", "athena-lightrag"]},
      {"name": "snowsql", "required_by": ["sentry/"]},
      {"name": "gh", "required_by": ["devkid/"]},
      {"name": "jq", "required_by": ["dev-kid"]},
      {"name": "docker", "required_by": [], "optional": true}
    ],

    "env_vars": [
      {"name": "ANTHROPIC_API_KEY", "required_by": ["*"], "critical": true},
      {"name": "SNOWFLAKE_ACCOUNT", "required_by": ["sentry/"], "critical": false},
      {"name": "GITHUB_TOKEN", "required_by": ["devkid/"], "critical": false},
      {"name": "GEMINI_API_KEY", "required_by": ["gemini-mcp"], "critical": false},
      {"name": "TABLEAU_SERVER", "required_by": ["tableau-mcp"], "critical": false}
    ],

    "python_packages": [
      {"name": "rich", "required_by": ["agent-transfer"]},
      {"name": "tiktoken", "required_by": ["session-review/"]}
    ],

    "docker": [
      {
        "type": "compose",
        "file": "docker-compose.yml",
        "services": ["neo4j", "graphiti-api"],
        "required_by": ["graphiti MCP server"]
      }
    ],

    "sourced_files": [
      {"path": "~/.claude/hooks/batch-guard/batch-guard-lib.js", "required_by": ["batch-guard.js"]}
    ]
  }
}
```

---

## 6. User Stories

### US1: Export with manifest (P1)

As a developer exporting my Claude Code setup, I want `agent-transfer export` to automatically scan all included agents, skills, and hooks for external dependencies and bundle a `manifest.json` in the archive, so the target machine knows exactly what's needed.

**Acceptance criteria:**
- Export produces archive containing `manifest.json` at root
- Manifest lists all MCP servers referenced by included agents
- Manifest lists all CLI tools found in included skill scripts
- Manifest lists all environment variables found in included scripts/configs
- Manifest includes source platform, OS, and home directory for path remapping

### US2: Import with preflight check (P1)

As a developer importing an agent-transfer archive on a new machine, I want the import process to automatically read `manifest.json`, check my local environment, and show me a readiness report before writing any files, so I can fix issues before they cause silent runtime failures.

**Acceptance criteria:**
- Import reads `manifest.json` from archive before extracting
- Readiness report shows green/yellow/red status for each dependency
- RED items show remediation hints (e.g., "Install snowsql: brew install snowflake-snowsql")
- Import warns but proceeds on YELLOW items
- Import blocks on RED items unless `--force` flag is used
- If no manifest exists (legacy archive), import proceeds with a warning

### US3: Standalone preflight command (P1)

As a developer, I want to run `agent-transfer preflight <archive>` to check readiness without actually importing, so I can prepare my machine before committing to the import.

**Acceptance criteria:**
- `agent-transfer preflight backup.tar.gz` reads manifest and runs all checks
- Output shows dependency-by-dependency status with colors
- Exit code 0 if all green/yellow, exit code 1 if any red
- `--json` flag outputs machine-readable report

### US4: Self-audit mode (P2)

As a developer, I want to run `agent-transfer preflight --self` to audit my current machine's setup and see what dependencies my agents/skills require, so I know what a target machine would need if I exported right now.

**Acceptance criteria:**
- Scans local agents, skills, hooks without needing an archive
- Produces the same readiness report format
- Useful for documenting "what this machine needs" for team onboarding

### US5: Claude Code skill integration (P2)

As a Claude Code user, I want a `/preflight` skill that runs readiness checks interactively and explains issues in natural language, so I get agentic assistance fixing problems rather than just a static report.

**Acceptance criteria:**
- `/preflight` skill available in Claude Code
- Skill reads manifest or scans local setup
- Provides conversational remediation guidance
- Can suggest commands to fix issues

---

## 7. Architecture

### Component Design

```
agent_transfer/utils/
├── preflight/
│   ├── __init__.py           # Public API
│   ├── collector.py          # Inventory collector (source-side)
│   │   ├── scan_agents()     # Extract MCP tool refs from agent .md files
│   │   ├── scan_skills()     # Parse skill scripts for CLI/env/package deps
│   │   ├── scan_hooks()      # Parse hook scripts for executables
│   │   └── scan_configs()    # Parse config files for references
│   ├── manifest.py           # Manifest read/write/validate
│   │   ├── ManifestBuilder   # Builds manifest from collector output
│   │   └── Manifest          # Dataclass for parsed manifest
│   ├── checker.py            # Preflight checker (target-side)
│   │   ├── check_mcp()       # Validate MCP server availability
│   │   ├── check_cli()       # Validate CLI tool availability
│   │   ├── check_env()       # Validate env var presence
│   │   ├── check_packages()  # Validate Python/Node package availability
│   │   └── check_paths()     # Validate path references after remap
│   ├── report.py             # Rich terminal report + JSON output
│   └── remediation.py        # Hint database for common missing deps
```

### Integration Points

- **Export flow:** `cli.py:export()` → `collector.scan_*()` → `ManifestBuilder` → bundle in archive
- **Import flow:** `cli.py:import_cmd()` → extract `manifest.json` → `checker.check_*()` → `report` → proceed or block
- **Standalone:** `cli.py:preflight()` → extract manifest OR scan local → `checker` → `report`
- **Pathfinder:** Uses `get_pathfinder()` for all path resolution and platform detection
- **Tool checker:** Extends existing `tool_checker.py` MCP validation (reuse, don't duplicate)

---

## 8. Success Criteria

- Zero silent runtime failures after import when preflight passes green
- Users can prepare a target machine from the readiness report alone (no tribal knowledge)
- Export archives are self-documenting — manifest explains everything inside
- Preflight adds < 2 seconds to import time for typical archives (< 50 agents/skills)
- Legacy archives (no manifest) import with a warning, not an error

---

## 9. Constraints

- **R3 (Linux only):** First implementation targets Linux. macOS/Windows path patterns detected but not actively tested.
- **R4 (Wrap Don't Rewrite):** Extends existing `tool_checker.py` and `check-ready` CLI — doesn't replace them.
- **R5 (Backward Compatibility):** Archives without `manifest.json` must still import normally.
- **R6 (No hardcoded paths):** All path resolution through pathfinder.
- **R9 (Plugin Architecture):** Dependency scanners should be extensible (new scanner for new dependency types).
- **Security:** NEVER log or display environment variable values. Only names and presence.

---

## 10. Design Philosophy: Best-Effort + Guidance

**We cannot catch every dependency.** Scripts can dynamically construct commands, download tools at runtime, or reference resources that only exist in specific network environments. The goal is:

1. **Catch 80-90% of dependencies automatically** — MCP servers, CLI tools, env vars, git repos, compiled binaries
2. **For the rest, provide guidance** — the readiness report includes a "Manual Checklist" section for things the user should verify themselves
3. **Allow user annotations** — a `.preflight.yml` file in skill/hook directories where authors can declare dependencies that automated scanning can't detect

### `.preflight.yml` (optional, author-provided)

Skill and MCP server authors can include a `.preflight.yml` in their directory to declare dependencies explicitly:

```yaml
# ~/.claude/skills/sentry/.preflight.yml
dependencies:
  cli_tools:
    - name: snowsql
      install_hint: "brew install snowflake-snowsql"
      version_hint: ">=1.2"
  env_vars:
    - name: SNOWFLAKE_ACCOUNT
      description: "Snowflake account identifier"
    - name: SNOWFLAKE_USER
      description: "Snowflake username"
  notes:
    - "Requires Snowflake network access (not air-gapped)"
    - "Run 'snowsql -c herself_dev' to verify connection"
```

The collector reads `.preflight.yml` files and merges them with auto-detected dependencies. This handles cases where automated scanning falls short.

---

## 11. Risks

| Risk | Mitigation |
|------|------------|
| Script parsing misses dependencies | Best-effort parsing + `.preflight.yml` for author-declared deps + "Manual Checklist" in report |
| Too many false-positive YELLOWs annoy users | Tune severity thresholds; allow `.preflight-ignore` file |
| Manifest bloats archive size | Manifest is JSON text, typically < 10KB even with git repos |
| Env var scanning exposes secrets | Only scan names, never values; document this guarantee |
| Circular dependency with tool_checker | Preflight imports tool_checker, not the reverse |
| Private git repos need auth | Manifest includes repo URL; user handles auth (SSH keys, tokens) — preflight just reports "needs clone" |
| Architecture mismatch for binaries | Detect via `uname -m` comparison; suggest recompilation if source available |
| Docker not available on target | Report as RED with install hint; don't assume Docker is universal |
| Dynamic/runtime dependencies | Can't catch everything — `.preflight.yml` and Manual Checklist fill the gaps |
