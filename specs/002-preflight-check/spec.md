# Feature Specification: Preflight Transfer Readiness Validation

**Feature Branch**: `002-preflight-check`
**Created**: 2026-03-11
**Status**: Draft
**Input**: PRD at `prd/preflight-check.md`

## User Scenarios & Testing

### User Story 1 - Standalone Preflight Check (Priority: P1)

A developer receives an agent-transfer archive from a colleague and wants to know if their machine is ready to import it before committing. They run `agent-transfer preflight backup.tar.gz` and see a color-coded readiness report showing which MCP servers, CLI tools, environment variables, git repos, and compiled binaries are present or missing, with remediation hints for each missing item.

**Why this priority**: This is the core value proposition — the user can assess readiness independently of the import flow. It's the simplest entry point (read-only, no side effects) and validates all the underlying scanner and checker logic that US2 and US3 build on.

**Independent Test**: Can be fully tested by creating a mock archive with a known `manifest.json`, running `agent-transfer preflight` against it, and verifying the report output matches expected green/yellow/red statuses for each dependency category.

**Acceptance Scenarios**:

1. **Given** an archive with `manifest.json` listing 3 MCP servers (2 configured locally, 1 not), **When** the user runs `agent-transfer preflight archive.tar.gz`, **Then** the report shows 2 green and 1 red MCP entries, with the red entry including setup commands from the manifest.

2. **Given** an archive with `manifest.json` listing CLI tools `node`, `uv`, `snowsql`, **When** `node` and `uv` are installed but `snowsql` is not, **Then** the report shows 2 green and 1 red CLI tool, with a remediation hint for installing snowsql.

3. **Given** an archive with `manifest.json` listing env vars `ANTHROPIC_API_KEY` (critical) and `SNOWFLAKE_ACCOUNT` (non-critical), **When** only `ANTHROPIC_API_KEY` is set, **Then** the report shows 1 green and 1 yellow env var. Environment variable values are never displayed.

4. **Given** an archive with `manifest.json` listing a compiled binary with `arch: x86_64`, **When** the target machine is ARM, **Then** the report shows a red entry with a message about architecture mismatch and recompilation instructions if source is available.

5. **Given** a legacy archive without `manifest.json`, **When** the user runs preflight, **Then** a warning is displayed that no manifest exists, and the command exits gracefully with a message suggesting the archive was created before preflight support.

6. **Given** a `--json` flag, **When** the user runs `agent-transfer preflight archive.tar.gz --json`, **Then** the output is a valid JSON object with structured results for each dependency category, suitable for scripting.

---

### User Story 2 - Import with Automatic Preflight Gate (Priority: P1)

A developer runs `agent-transfer import backup.tar.gz` on a new machine. Before extracting any files, the import process reads the manifest, runs all preflight checks, and shows the readiness report. If there are RED items, the import pauses and asks for confirmation (or blocks unless `--force` is used). The developer can fix issues and re-run, or force the import knowing what will break.

**Why this priority**: This is where preflight delivers the most impact — preventing broken imports at the moment they happen, not after the fact.

**Independent Test**: Can be tested by running import against archives with varying levels of dependency satisfaction and verifying the gate behavior (block on RED, warn on YELLOW, proceed on all-green).

**Acceptance Scenarios**:

1. **Given** an archive with all dependencies satisfied on the target, **When** the user runs `agent-transfer import archive.tar.gz`, **Then** the readiness report shows all green, and import proceeds without interruption.

2. **Given** an archive with 1 RED dependency (missing MCP server), **When** the user runs `agent-transfer import archive.tar.gz`, **Then** the readiness report is shown, import pauses, and the user is prompted to continue or abort.

3. **Given** an archive with RED dependencies, **When** the user runs `agent-transfer import archive.tar.gz --force`, **Then** the readiness report is shown as a warning but import proceeds without blocking.

4. **Given** a legacy archive without manifest, **When** the user runs import, **Then** a warning is shown that no preflight data is available, and import proceeds normally (backward compatible).

---

### User Story 3 - Export with Manifest Generation (Priority: P1)

A developer runs `agent-transfer export` to create an archive of their agents, skills, hooks, and configs. The export process automatically scans all included items for dependencies — MCP servers referenced by agents, CLI tools used in skill scripts, environment variables referenced in configs, git repos backing MCP servers, compiled binaries in skill trees — and bundles a `manifest.json` in the archive root.

**Why this priority**: Without manifest generation, there's nothing for the target-side preflight to check against. This is a prerequisite for US1 and US2.

**Independent Test**: Can be tested by exporting a known set of agents and skills, extracting the resulting archive, and verifying the `manifest.json` contains accurate dependency entries that match the source environment.

**Acceptance Scenarios**:

1. **Given** agents that reference `mcp__graphiti__search_nodes` and `mcp__context7__resolve-library-id`, **When** the user runs export, **Then** `manifest.json` contains entries for `graphiti` and `context7-mcp` MCP servers with their installation types and setup commands.

2. **Given** a skill directory containing bash scripts that invoke `snowsql` and `jq`, **When** the user runs export, **Then** `manifest.json` lists `snowsql` and `jq` as CLI tool dependencies with the skill as `required_by`.

3. **Given** MCP server configs that reference git repos (e.g., `~/dev/gemini-mcp`), **When** the user runs export, **Then** `manifest.json` includes `git_repos` entries with the remote URL (from `.git/config`), local path, and setup commands.

4. **Given** a skill tree with a compiled Rust binary, **When** the user runs export, **Then** `manifest.json` includes a `compiled_binaries` entry with architecture, OS, source language, and build command.

5. **Given** scripts referencing `$SNOWFLAKE_ACCOUNT` and `process.env.GITHUB_TOKEN`, **When** the user runs export, **Then** `manifest.json` lists these as env var dependencies. Variable values are never included.

6. **Given** a skill directory containing a `.preflight.yml` with author-declared dependencies, **When** the user runs export, **Then** those declared dependencies are merged into `manifest.json` alongside auto-detected ones.

---

### User Story 4 - Self-Audit Mode (Priority: P2)

A developer wants to understand what their current machine setup requires — what would a target machine need if they exported right now? They run `agent-transfer preflight --self` and get a full readiness report of their own environment, useful for onboarding documentation or verifying their setup is complete.

**Why this priority**: Valuable but not blocking — the core export/import/check flow works without it. This is a convenience feature that reuses the same collector and report infrastructure.

**Independent Test**: Can be tested by running self-audit on a known machine setup and verifying the report lists all discovered dependencies across agents, skills, hooks, and configs.

**Acceptance Scenarios**:

1. **Given** a machine with 30 agents, 15 skills, and 8 MCP servers, **When** the user runs `agent-transfer preflight --self`, **Then** a readiness report shows all discovered dependencies organized by category.

2. **Given** `--self --json` flags, **When** the user runs the command, **Then** output is a valid JSON manifest identical in format to what `manifest.json` would contain in an export archive.

---

### User Story 5 - Claude Code Skill Integration (Priority: P3)

A Claude Code user invokes `/preflight` within a session. The skill runs the preflight checker against an archive or the local setup, presents findings conversationally, and offers actionable guidance — suggesting specific install commands, explaining why each dependency matters, and helping the user work through issues interactively.

**Why this priority**: Enhances the UX but the core CLI flow works without it. This wraps the CLI functionality in an agentic conversation.

**Independent Test**: Can be tested by invoking the skill and verifying it produces human-readable guidance based on the underlying preflight report.

**Acceptance Scenarios**:

1. **Given** the user invokes `/preflight` in Claude Code, **When** there are missing dependencies, **Then** the skill explains each gap in natural language and suggests specific remediation commands.

2. **Given** the user invokes `/preflight archive.tar.gz`, **When** the archive has a manifest, **Then** the skill runs all checks and presents an interactive summary.

---

### Edge Cases

- What happens when the archive is corrupted or not a valid tar.gz? System reports a clear error and exits without partial extraction.
- How does the system handle MCP server configs split across multiple files (`mcp.json`, `settings.json`, project-level configs)? The collector merges all config sources using pathfinder's platform-aware config resolution.
- What happens when a git repo URL is a private repo the target user can't access? The report shows the repo URL and marks it YELLOW with a note that access may require authentication.
- How are architecture-dependent compiled binaries handled when transferring between x86_64 and ARM? The manifest records source arch; the checker compares against `uname -m` and flags mismatches as RED with recompilation guidance.
- What happens when a `.preflight.yml` has syntax errors? The collector logs a warning and skips the malformed file, falling back to auto-detection only.
- How does the system handle Docker dependencies when Docker is installed but the daemon is not running? Checker verifies `docker` CLI exists (GREEN for CLI) but cannot verify daemon status — documented as a known limitation in the Manual Checklist.
- What happens when an environment variable is referenced inside a conditional branch of a script? Best-effort detection — the variable is listed as YELLOW (may not be required) rather than RED.

## Requirements

### Functional Requirements

- **FR-001**: System MUST scan agent `.md` files for MCP tool references (`mcp__<server>__<tool>` patterns) and extract unique server IDs
- **FR-002**: System MUST cross-reference MCP server IDs against local MCP config files to determine installation type (npm on-demand, bun on-demand, git repo + Python venv, git repo + uv, git repo + Node.js, remote SSE, Docker)
- **FR-003**: System MUST resolve git remote URLs for MCP servers and skills backed by local git repositories by reading `.git/config`
- **FR-004**: System MUST parse skill scripts (`.sh`, `.py`, `.js`) to detect CLI tool invocations via shebang lines, direct command calls, and `command -v`/`which` patterns
- **FR-005**: System MUST parse scripts and configs for environment variable references (`$VAR`, `${VAR}`, `os.environ`, `process.env`) without ever capturing or displaying variable values
- **FR-006**: System MUST detect compiled binaries in skill directories using file magic bytes and record architecture, OS, source language, and build command metadata
- **FR-007**: System MUST detect self-contained skill trees (directories with install scripts, nested structures, compiled binaries) and record their system dependencies, optional dependencies, and PATH requirements
- **FR-008**: System MUST detect Docker and docker-compose dependencies from Dockerfiles, compose files, and `docker run` commands in scripts
- **FR-009**: System MUST generate a `manifest.json` conforming to the v2.0 schema and bundle it in export archives at the archive root
- **FR-010**: System MUST read `.preflight.yml` files from skill and hook directories and merge author-declared dependencies with auto-detected ones
- **FR-011**: System MUST validate target environment by checking: MCP server configuration presence, CLI tool availability via PATH lookup, environment variable presence (not values), git repo directory existence, binary architecture compatibility via `uname -m`, Docker CLI availability
- **FR-012**: System MUST produce a readiness report with three severity levels: GREEN (available), YELLOW (warning/may not be required), RED (missing/critical)
- **FR-013**: System MUST include actionable remediation hints for RED and YELLOW items — install commands, git clone URLs, setup instructions, and recompilation guidance where applicable
- **FR-014**: System MUST support `--json` flag for machine-readable output suitable for CI/CD and scripting
- **FR-015**: System MUST handle legacy archives without `manifest.json` gracefully — show an informational warning and proceed with import normally
- **FR-016**: System MUST gate the import flow on preflight results — block on RED items unless `--force` is passed, warn on YELLOW items, proceed silently on all-GREEN

### Key Entities

- **TransferManifest**: The complete dependency declaration for an export archive — version, source environment metadata (platform, OS, arch, home dir), contents list, and all dependency categories (MCP servers, git repos, compiled binaries, skill trees, CLI tools, env vars, Docker, scripts, hooks, paths)
- **DependencyEntry**: A single dependency with name, category, severity, required-by references, installation type, and remediation hints
- **ReadinessReport**: The result of running all checkers against a manifest — per-category results with per-item status (GREEN/YELLOW/RED), overall pass/warn/fail status, and a Manual Checklist section for items that require human verification
- **InventoryCollector**: The source-side scanner that builds the manifest by analyzing agents, skills, hooks, configs, and `.preflight.yml` annotations
- **PreflightChecker**: The target-side validator that checks each manifest dependency against the local environment and produces the readiness report

## Success Criteria

### Measurable Outcomes

- **SC-001**: Preflight correctly identifies 90% or more of actual runtime dependencies when tested against a known agent-transfer setup with 30+ agents and 15+ skills
- **SC-002**: Users can prepare a new machine for import using only the readiness report and its remediation hints — no undocumented tribal knowledge required
- **SC-003**: Zero silent runtime failures occur after import when the preflight report shows all GREEN
- **SC-004**: Preflight check completes in under 3 seconds for typical archives containing up to 50 agents and 20 skills
- **SC-005**: Legacy archives created before preflight support continue to import successfully with only an informational warning
- **SC-006**: The readiness report is clear enough that a developer unfamiliar with the source machine's setup can understand and act on every item without additional context

### Assumptions

- MCP server configurations follow standard Claude Code patterns (`mcp.json`, `settings.json`, `.gemini/settings.json`, project-level configs)
- Git repositories have a configured remote origin URL accessible via `.git/config`
- CLI tools can be detected via `shutil.which()` (they're on the system PATH)
- Compiled binaries can be identified by file magic bytes or the `file` command
- Script parsing for CLI tools and env vars is best-effort — dynamically constructed commands, eval'd references, and runtime downloads may be missed
- The `.preflight.yml` annotation format fills gaps where automated scanning is insufficient
- Docker daemon status cannot be verified (only CLI presence) — this is documented in the Manual Checklist
