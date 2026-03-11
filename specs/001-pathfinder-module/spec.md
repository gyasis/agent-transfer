# Feature Specification: Pathfinder Module — Centralized Path Resolution

**Feature Branch**: `001-pathfinder-module`
**Created**: 2026-03-11
**Status**: Draft
**Input**: PRD: `prd/pathfinder-module.md` — Centralized path resolution for platform-agnostic agent transfer

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Centralized Path Resolution for Contributors (Priority: P1)

As a contributor to agent-transfer, I want a single module that resolves all platform paths so I don't have to duplicate path logic across 7+ modules. Currently, the same `Path.home() / '.claude' / 'agents'` pattern appears in `cli.py`, `discovery.py`, `transfer.py`, `import_analyzer.py`, and `skill_discovery.py`. With pathfinder, I call `pathfinder.agents_dir("claude-code")` from any module.

**Why this priority**: This is the foundational capability. Without centralized resolution, every other story (multi-platform, remapping, translation) has no foundation to build on. Eliminates 35+ hardcoded `.claude` references and 20+ `Path.home()` calls.

**Independent Test**: Can be fully tested by creating the pathfinder module with Claude Code path profiles and verifying that `agents_dir()`, `skills_dir()`, `config_dir()`, `hooks_dir()`, and `config_files()` all resolve correctly for the Claude Code platform. Delivers immediate value by establishing the single source of truth for path resolution.

**Acceptance Scenarios**:

1. **Given** the pathfinder module is available, **When** a contributor calls `pf.agents_dir("claude-code")`, **Then** it returns the correct path to `~/.claude/agents`
2. **Given** the pathfinder module is available, **When** a contributor calls `pf.skills_dir("claude-code")`, **Then** it returns the correct path to `~/.claude/skills`
3. **Given** the pathfinder module is available, **When** a contributor calls `pf.config_files("claude-code")`, **Then** it returns paths for `mcp.json`, `settings.json`, and `settings.local.json`
4. **Given** all 7 existing modules are refactored, **When** searching the codebase for `Path.home().*\.claude`, **Then** results appear ONLY in `pathfinder.py`
5. **Given** existing modules are refactored, **When** running the full test suite, **Then** all tests pass with zero regressions

---

### User Story 2 - Multi-Platform Path Profiles (Priority: P1)

As a developer adding support for a new AI platform (Goose, Codex, Gemini CLI, OpenCode), I want to register a path profile once and have all modules automatically resolve paths for that platform — without modifying any consuming module.

**Why this priority**: This is the primary value proposition for the v2 platform-agnostic goal. Without path profiles, adding each new platform requires touching every module (N*M path logic). With profiles, it's 1 profile definition per platform.

**Independent Test**: Can be tested by registering all 5 platform profiles and verifying each one resolves its config, agents, skills, and hooks directories correctly. Can also test by adding a mock 6th platform profile and confirming it works without code changes.

**Acceptance Scenarios**:

1. **Given** 5 platform profiles are registered, **When** calling `pf.config_dir("goose")`, **Then** it returns `~/.config/goose`
2. **Given** 5 platform profiles are registered, **When** calling `pf.skills_dir("goose")`, **Then** it returns `~/.config/goose/recipes`
3. **Given** 5 platform profiles are registered, **When** calling `pf.supported_platforms()`, **Then** it returns all 5 platform slugs
4. **Given** a new platform profile is registered, **When** any consuming module uses pathfinder with the new platform slug, **Then** paths resolve correctly without changes to that module
5. **Given** a platform has no hooks directory (e.g., Codex), **When** calling `pf.hooks_dir("codex")`, **Then** it returns `None` rather than an invalid path

---

### User Story 3 - Cross-Machine Path Remapping (Priority: P2)

As a user importing MCP configs from a colleague's machine, I want paths in the config to be automatically remapped to my home directory so the config works on my machine without manual editing.

**Why this priority**: Directly enables the cross-machine transfer use case. Currently `config_manager.py` has ad-hoc remapping logic that isn't reusable. This story makes it a first-class utility.

**Independent Test**: Can be tested by providing a path from Machine A (e.g., `/home/alice/.claude/hooks/pre-commit.sh`) and verifying it remaps to Machine B's home directory (e.g., `/home/bob/.claude/hooks/pre-commit.sh`).

**Acceptance Scenarios**:

1. **Given** a path from Machine A (`/home/alice/.claude/hooks/pre-commit.sh`), **When** calling `pf.remap_path()` with source and target homes, **Then** it returns `/home/bob/.claude/hooks/pre-commit.sh`
2. **Given** a path that doesn't contain the source home prefix, **When** calling `pf.remap_path()`, **Then** it returns the original path unchanged
3. **Given** a path that already matches the target home, **When** calling `pf.remap_path()`, **Then** it returns the path unchanged (no double-remap)
4. **Given** a relative path, **When** calling `pf.remap_path()`, **Then** it returns the path unchanged

---

### User Story 4 - Environment Variable Overrides (Priority: P2)

As a developer with a non-standard platform installation, I want to set an environment variable (e.g., `$CLAUDE_CONFIG_DIR`) to override the default config location, and have all dependent paths automatically adjust.

**Why this priority**: Essential for non-standard installations and CI/CD environments where platforms may be installed in custom locations.

**Independent Test**: Can be tested by setting `$CLAUDE_CONFIG_DIR` to a custom directory and verifying that `config_dir()`, `agents_dir()`, `skills_dir()`, and all derived paths use the override.

**Acceptance Scenarios**:

1. **Given** `$CLAUDE_CONFIG_DIR` is set to `/custom/path`, **When** calling `pf.config_dir("claude-code")`, **Then** it returns `/custom/path`
2. **Given** `$CLAUDE_CONFIG_DIR` is set, **When** calling `pf.agents_dir("claude-code")`, **Then** agents resolves relative to the override (e.g., `/custom/path/agents`)
3. **Given** no environment override is set, **When** calling `pf.config_dir("claude-code")`, **Then** it falls back to the default `~/.claude`

---

### User Story 5 - Cross-Platform Path Translation (Priority: P3)

As a user converting an agent from Claude Code to Goose format, I want internal path references to be automatically translated to the target platform's directory structure.

**Why this priority**: Enables the cross-platform agent conversion workflow. Lower priority because it depends on Stories 1 and 2 and is only needed when converting between platforms (Phase 3+).

**Independent Test**: Can be tested by translating a Claude Code path reference to each of the other 4 platforms and verifying correctness.

**Acceptance Scenarios**:

1. **Given** a Claude Code skills path `~/.claude/skills/my-skill/`, **When** translating to Goose, **Then** it becomes `~/.config/goose/recipes/my-skill/`
2. **Given** a path that doesn't match any known platform directory, **When** attempting translation, **Then** the system flags it with a warning and returns the original path
3. **Given** translation between all 5 platforms, **When** translating a known path type (config, agents, skills), **Then** each translation produces the correct target path

---

### User Story 6 - Executable Discovery (Priority: P2)

As a module that needs to invoke a platform's CLI tool, I want a single method that finds the executable using a consolidated, ordered search strategy rather than each module implementing its own search.

**Why this priority**: `discovery.py` currently has 7 independent search strategies. Consolidating them eliminates duplication and ensures consistent search ordering across all modules.

**Independent Test**: Can be tested by placing executables in various locations (PATH, npm global, nvm, virtual env) and verifying `find_executable()` discovers them in priority order.

**Acceptance Scenarios**:

1. **Given** the `claude` executable is on `$PATH`, **When** calling `pf.find_executable("claude-code")`, **Then** it returns the executable path
2. **Given** the executable is only in an npm global path, **When** `shutil.which` fails, **Then** pathfinder falls back to npm paths and finds it
3. **Given** a platform whose profile doesn't include npm/nvm search strategies (e.g., Goose), **When** searching for its executable, **Then** only the relevant strategies are used
4. **Given** the executable is not found anywhere, **When** calling `pf.find_executable()`, **Then** it returns `None`

---

### Edge Cases

- What happens when `Path.home()` is not writable or returns an unexpected value (e.g., in a container)?
- How does pathfinder handle symlinked directories (e.g., `~/.claude` is a symlink)?
- What happens when project-level search reaches filesystem root without finding a project config dir?
- How does `remap_path()` handle paths with embedded home directories in arguments (e.g., a script that references another user's home)?
- What happens when two platform profiles share the same config directory path?
- How does pathfinder behave when an environment override variable points to a non-existent directory?
- What happens when `translate_path()` encounters a path belonging to an unregistered platform?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a `Pathfinder` class that resolves config, agents, skills, hooks, and config file paths for any registered platform given its slug identifier
- **FR-002**: System MUST include built-in path profiles for 5 platforms: Claude Code, Codex CLI, Gemini CLI, Goose, and OpenCode
- **FR-003**: System MUST support both user-level (`~/.claude/agents`) and project-level (`.claude/agents`) path resolution
- **FR-004**: System MUST provide project-level directory discovery by searching upward from the current working directory
- **FR-005**: System MUST consolidate executable discovery into a single ordered search strategy (PATH, env override, npm global, npm prefix, nvm, virtualenv, conda, system paths, custom paths)
- **FR-006**: System MUST provide `remap_path()` to translate paths from one machine's home directory to another's
- **FR-007**: System MUST provide `translate_path()` to convert platform-specific path references between platforms
- **FR-008**: System MUST support environment variable overrides for config directories, with override propagating to all dependent paths (agents, skills, hooks, config files)
- **FR-009**: System MUST allow third-party registration of custom path profiles without modifying pathfinder source code
- **FR-010**: System MUST provide a singleton accessor (`get_pathfinder()`) so all modules share one instance
- **FR-011**: System MUST cache expensive operations (executable lookups, project-level scans) with manual invalidation support
- **FR-012**: System MUST NOT contain any hardcoded absolute paths — all paths derived from `Path.home()`, environment variables, or profile definitions
- **FR-013**: System MUST handle platforms that lack certain directory types (e.g., Goose has no agents dir) by returning `None` rather than invalid paths
- **FR-014**: System MUST provide `validate_path()` and `ensure_dir()` utilities for path existence checking and directory creation

### Key Entities

- **PathProfile**: Defines a platform's filesystem layout — config directory, subdirectory names for agents/skills/hooks, config file names, executable names, environment override variable, and project-level support flag
- **PathProfileRegistry**: Collection of registered path profiles, keyed by platform slug. Supports built-in profiles and third-party additions
- **Pathfinder**: Main resolver class. Takes a platform slug and returns resolved, absolute paths. Manages caching, project-level discovery, and cross-platform translation

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After refactoring, searching the codebase for direct platform path construction (e.g., `Path.home() / '.claude'`) returns results ONLY in `pathfinder.py` — zero scattered path logic in any other module
- **SC-002**: All 5 target platform profiles are registered and resolve paths correctly (config, agents, skills, hooks, config files, executables)
- **SC-003**: All existing tests pass after refactoring with zero regressions — backward compatibility is fully maintained
- **SC-004**: Adding a new (6th) platform requires only defining a new `PathProfile` — no changes to any consuming module
- **SC-005**: Cross-machine path remapping correctly handles all edge cases (different homes, no-op, relative paths, already-correct paths)
- **SC-006**: Environment variable overrides propagate correctly to all dependent paths for each platform
- **SC-007**: Contributors can resolve any platform path with a single method call, reducing code duplication from 35+ scattered references to 1 centralized module

## Assumptions

- The project targets Linux and WSL only (per constitution rule R3). macOS and Windows native paths are out of scope.
- Platform detection (determining which platforms are installed on a machine) is out of scope — pathfinder resolves paths but does not check installation status.
- MCP server command path resolution (e.g., `npx`, `uvx`, `node` paths) is out of scope and stays in runtime tools.
- Project-level directory search defaults to 5 levels upward from the current working directory, which is sufficient for typical project structures.
- Executable lookup caching uses a time-based invalidation (default 5 minutes) plus manual `clear_cache()` for immediate invalidation.
- The singleton pattern (`get_pathfinder()`) is appropriate because path resolution is stateless relative to the filesystem — all modules should see the same paths.
