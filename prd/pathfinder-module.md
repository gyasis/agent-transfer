# PRD: Pathfinder Module — Centralized Path Resolution for Platform-Agnostic Agent Transfer

**Author:** Gyasi Sutton
**Date:** 2026-03-11
**Status:** Draft
**Branch:** `feature/pathfinder-module`
**Parent PRD:** `prd/agent-transfer-v2-platform-agnostic.md`

---

## 1. Problem Statement

Path resolution in `agent-transfer` is scattered across 7+ modules with 35+ hardcoded `.claude` references, 20+ `Path.home()` calls, and 8+ system path literals. Every module independently constructs paths to agents, skills, configs, and executables — creating:

1. **Duplication** — The same `Path.home() / '.claude' / 'agents'` pattern appears in `cli.py`, `discovery.py`, `transfer.py`, `import_analyzer.py`, and `skill_discovery.py`
2. **Inconsistency** — `tool_checker.py` checks 5 MCP config locations while `config_manager.py` checks 3, in different orders
3. **Claude Code lock-in** — Every path is hardcoded to `.claude/` directory structure. Adding Goose (`~/.config/goose/`), Codex (`~/.agents/skills/`), Gemini CLI (`~/.gemini/`), or OpenCode (`.opencode/`) would require touching every module
4. **No normalization** — Paths from exports (Machine A's home dir) aren't systematically remapped to the target machine. `config_manager.py` does ad-hoc path remapping but it's not reusable
5. **Violation of R6** — Constitution rule R6 says "No hardcoded absolute paths" but the codebase has 8+ system path literals (`/usr/local/bin`, `/opt/claude-code/bin`, etc.)

### Impact on v2 Platform-Agnostic Goal

The v2 roadmap (Phases 2-6) adds 5 platform backends. Without a pathfinder, each platform's ingestor/emitter would independently implement path resolution, creating N*M path logic where N = modules and M = platforms. With a pathfinder, it's 1 centralized resolver that all modules call.

---

## 2. Vision

A single `agent_transfer/utils/pathfinder.py` module that is the **sole authority** for resolving filesystem paths across all platforms. Every other module calls `pathfinder` instead of constructing paths directly. When a new platform is added, only `pathfinder` needs a new path profile — not every module.

```
Before (scattered):
  cli.py          → Path.home() / '.claude' / 'agents'
  transfer.py     → Path.home() / '.claude' / 'agents'
  import_analyzer → Path.home() / '.claude' / 'agents'
  discovery.py    → Path.home() / '.claude' / 'agents'
  skill_discovery → Path.home() / '.claude' / 'skills'

After (centralized):
  cli.py          → pathfinder.agents_dir("claude-code")
  transfer.py     → pathfinder.agents_dir("claude-code")
  import_analyzer → pathfinder.agents_dir("claude-code")
  discovery.py    → pathfinder.agents_dir("claude-code")
  skill_discovery → pathfinder.skills_dir("claude-code")
```

---

## 3. Scope

### In Scope

- `pathfinder.py` module with platform-aware path resolution
- Path profiles for all 5 target platforms (Claude Code, Codex, Gemini CLI, Goose, OpenCode)
- User-level vs project-level path resolution
- Executable discovery (consolidate 7 strategies from `discovery.py`)
- Config file discovery (consolidate from `tool_checker.py`, `config_manager.py`)
- Path normalization/remapping for cross-machine transfers
- Environment variable integration (`VIRTUAL_ENV`, `CONDA_PREFIX`, `CLAUDE_CONFIG_DIR`, etc.)
- Refactor all 7 existing modules to use pathfinder instead of direct path construction

### Out of Scope

- macOS-specific paths (future phase per R3)
- Windows native paths (R3)
- Platform detection logic (that's `platforms/base.py` in Phase 2 — pathfinder provides paths, platforms provide detection)
- Archive handling (stays in `transfer.py`)

---

## 4. Requirements

### 4.1 Platform Path Profiles

Each platform has a path profile defining where its artifacts live:

| Platform | Config Dir | Agents Dir | Skills Dir | Hooks Dir | Config Files | Executable |
|----------|-----------|------------|------------|-----------|-------------|------------|
| **Claude Code** | `~/.claude` | `~/.claude/agents` + `.claude/agents` | `~/.claude/skills` + `.claude/skills` | `~/.claude/hooks` | `mcp.json`, `settings.json`, `settings.local.json` | `claude` |
| **Codex CLI** | `~/.codex` | `~/.agents/skills` | `~/.agents/skills` | N/A | TOML config | `codex` |
| **Gemini CLI** | `~/.gemini` | `~/.gemini/agents` | `~/.gemini/skills` | N/A | `settings.json` | `gemini` |
| **Goose** | `~/.config/goose` | N/A (uses recipes) | `~/.config/goose/recipes` | N/A | `profiles.yaml` | `goose` |
| **OpenCode** | `.opencode` | `.opencode/agents` | `.opencode/plugins` | N/A | `opencode.json` | `opencode` |

### 4.2 Core API

```python
from agent_transfer.utils.pathfinder import Pathfinder

pf = Pathfinder()

# Platform-aware directory resolution
pf.config_dir("claude-code")      # -> Path("~/.claude")
pf.agents_dir("claude-code")      # -> Path("~/.claude/agents")
pf.skills_dir("claude-code")      # -> Path("~/.claude/skills")
pf.hooks_dir("claude-code")       # -> Path("~/.claude/hooks")
pf.config_files("claude-code")    # -> [Path("~/.claude/mcp.json"), Path("~/.claude/settings.json"), ...]

# Project-level resolution (searches up from cwd)
pf.project_agents_dir("claude-code")   # -> Path(".claude/agents") or None
pf.project_skills_dir("claude-code")   # -> Path(".claude/skills") or None

# Executable discovery
pf.find_executable("claude-code")      # -> Path("/usr/local/bin/claude") or None

# All directories for a platform (user + project)
pf.all_agents_dirs("claude-code")      # -> [(Path, "user"), (Path, "project")]
pf.all_skills_dirs("claude-code")      # -> [(Path, "user"), (Path, "project")]

# Cross-machine path remapping
pf.remap_path(path, source_home="/home/alice", target_home="/home/bob")

# Path validation
pf.validate_path(path)                 # -> True/False (exists, readable)
pf.ensure_dir(path)                    # -> creates if missing

# Environment overrides
pf.config_dir("claude-code", env_override="CLAUDE_CONFIG_DIR")
# Checks $CLAUDE_CONFIG_DIR first, falls back to default

# List all known platforms
pf.supported_platforms()               # -> ["claude-code", "codex", "gemini-cli", "goose", "opencode"]
```

### 4.3 Path Profile Registration

Path profiles use a dataclass, supporting both the built-in 5 platforms and third-party additions via the plugin architecture (R9):

```python
@dataclass
class PathProfile:
    slug: str                        # "claude-code", "goose", etc.
    config_dir: str                  # Relative to home: ".claude"
    agents_subdir: str | None        # Relative to config_dir: "agents"
    skills_subdir: str | None        # "skills", "recipes", "plugins"
    hooks_subdir: str | None         # "hooks" or None
    config_files: list[str]          # ["mcp.json", "settings.json"]
    executable_names: list[str]      # ["claude"] — names to search in PATH
    project_level: bool              # Does this platform use project-level dirs?
    project_config_dir: str | None   # ".claude" for project-level (relative to project root)
    env_override_var: str | None     # "CLAUDE_CONFIG_DIR" — env var to override config_dir
    search_paths: list[str]          # Extra executable search paths beyond PATH
```

### 4.4 Executable Discovery Consolidation

`discovery.py` has 7 strategies for finding the Claude Code executable. Pathfinder consolidates these into a single ordered search:

1. `shutil.which(name)` — check PATH
2. Environment variable override (`$CLAUDE_CONFIG_DIR/../bin/claude`)
3. npm global paths (`~/.npm-global/bin/`, `~/.local/share/npm/bin/`)
4. npm prefix (`npm config get prefix`)
5. nvm paths (`~/.nvm/versions/node/*/bin/`)
6. Virtual environment (`$VIRTUAL_ENV/bin/`)
7. Conda environment (`$CONDA_PREFIX/bin/`)
8. System paths (`/usr/local/bin/`, `/usr/bin/`)
9. Custom search paths from `PathProfile.search_paths`

Each platform's `PathProfile` specifies which strategies apply (e.g., Goose doesn't need npm/nvm checks).

### 4.5 Path Remapping for Cross-Machine Transfer

When importing configs from Machine A to Machine B, paths containing Machine A's home directory must be remapped:

```python
# Machine A exported: /home/alice/.claude/hooks/pre-commit.sh
# Machine B (bob) imports:
pf.remap_path(
    Path("/home/alice/.claude/hooks/pre-commit.sh"),
    source_home="/home/alice",
    target_home="/home/bob"
)
# -> Path("/home/bob/.claude/hooks/pre-commit.sh")
```

This replaces the ad-hoc remapping in `config_manager.py` with a reusable utility.

### 4.6 Cross-Platform Path Translation

When converting an agent from Claude Code to Goose, references to platform-specific paths need translation:

```python
# Claude Code agent references: ~/.claude/skills/my-skill/
# Converting to Goose: needs to become ~/.config/goose/recipes/my-skill/
pf.translate_path(
    path="~/.claude/skills/my-skill/",
    from_platform="claude-code",
    to_platform="goose"
)
# -> "~/.config/goose/recipes/my-skill/"
```

### 4.7 Constraints

- **R3**: Linux + WSL only. No macOS paths (`/opt/homebrew/`, `~/Library/`). No Windows paths.
- **R4**: Wrap existing logic. `discovery.py` functions become thin wrappers around pathfinder calls.
- **R5**: Backward compatible. Modules that currently work keep working — pathfinder is additive.
- **R6**: No hardcoded absolute paths in pathfinder itself. Use `Path.home()` and env vars.
- **R9**: Path profiles are pluggable — third parties can register custom profiles.

---

## 5. Affected Modules (Refactoring Map)

| Module | Current Path Logic | Pathfinder Replacement |
|--------|-------------------|----------------------|
| `discovery.py` | 7-strategy executable search, 4-location config search, 3 agent dir strategies | `pf.find_executable()`, `pf.config_dir()`, `pf.all_agents_dirs()` |
| `config_manager.py` | `Path.home() / '.claude'` for mcp.json, settings.json, settings.local.json; ad-hoc path remapping | `pf.config_files()`, `pf.remap_path()` |
| `transfer.py` | `Path.home() / '.claude' / 'agents'`, `Path.cwd() / '.claude' / 'agents'`, same for skills | `pf.agents_dir()`, `pf.project_agents_dir()`, `pf.skills_dir()` |
| `import_analyzer.py` | `Path.home() / '.claude' / 'agents'`, `Path.cwd() / '.claude' / 'agents'` | `pf.agents_dir()`, `pf.project_agents_dir()` |
| `skill_discovery.py` | `Path.home() / '.claude' / 'skills'`, recursive cwd search | `pf.all_skills_dirs()` |
| `tool_checker.py` | 5-location MCP config search | `pf.config_files("claude-code", filename="mcp.json")` |
| `cli.py` | `Path.home() / '.claude' / 'skills'`, `Path.cwd() / '.claude' / 'skills'` | `pf.skills_dir()`, `pf.project_skills_dir()` |

---

## 6. User Stories

### US-PF1: Centralized Path Resolution
> As a contributor to agent-transfer, I want a single module that resolves all platform paths so I don't have to duplicate path logic across modules.

**Acceptance:**
- All 7 modules listed above use pathfinder instead of direct `Path.home() / '.claude'` construction
- Zero `Path.home() / '.claude'` in any module except `pathfinder.py`
- All existing tests pass (R5)

### US-PF2: Multi-Platform Path Profiles
> As a developer adding Goose support to agent-transfer, I want to register Goose's path profile once and have all modules automatically resolve Goose paths.

**Acceptance:**
- `pf.config_dir("goose")` returns `~/.config/goose`
- `pf.skills_dir("goose")` returns `~/.config/goose/recipes`
- Adding a new platform requires only a new `PathProfile` entry — no changes to consuming modules

### US-PF3: Cross-Machine Path Remapping
> As a user importing MCP configs from a colleague's machine, I want paths in the config to be automatically remapped to my home directory.

**Acceptance:**
- `pf.remap_path()` correctly translates `/home/alice/.claude/...` to `/home/bob/.claude/...`
- `config_manager.py` uses `pf.remap_path()` instead of ad-hoc remapping
- Handles edge cases: no home prefix, already-correct paths, relative paths

### US-PF4: Environment Variable Overrides
> As a developer with a non-standard Claude Code install, I want to set `$CLAUDE_CONFIG_DIR` to override the default config location.

**Acceptance:**
- `pf.config_dir("claude-code")` checks `$CLAUDE_CONFIG_DIR` before defaulting to `~/.claude`
- Each platform can define its own override env var
- Override propagates to all dependent paths (agents, skills, hooks, configs)

### US-PF5: Cross-Platform Path Translation
> As a user converting a Claude Code agent to Goose format, I want internal path references to be translated to Goose-appropriate paths.

**Acceptance:**
- References to `~/.claude/skills/X` become `~/.config/goose/recipes/X` when converting to Goose
- Translation works for all 5 platforms
- Untranslatable paths are flagged with a warning

---

## 7. Technical Design

### 7.1 Module Structure

```
agent_transfer/utils/pathfinder.py
    PathProfile          — Dataclass defining a platform's filesystem layout
    PathProfileRegistry  — Registry of all platform profiles (dict + entry_points)
    Pathfinder           — Main class, instantiated once, used by all modules
```

### 7.2 Integration Pattern

```python
# In any module (e.g., transfer.py):
from agent_transfer.utils.pathfinder import get_pathfinder

pf = get_pathfinder()  # Singleton, lazy-initialized
user_agents = pf.agents_dir("claude-code")
project_agents = pf.project_agents_dir("claude-code")
```

`get_pathfinder()` returns a module-level singleton so all modules share the same instance and path cache.

### 7.3 Caching

Pathfinder caches:
- Executable lookup results (expensive `shutil.which` + subprocess calls)
- Config dir resolution results
- Project-level directory scans (cwd-relative searches)

Cache is invalidated on explicit `pf.clear_cache()` call or when `cwd` changes.

### 7.4 Relationship to Phase 2 Platform Abstraction

Pathfinder is a **prerequisite** for Phase 2. The `BasePlatform` ABC will use pathfinder internally:

```python
class BasePlatform(ABC):
    def __init__(self):
        self.pf = get_pathfinder()

    def find_agents(self) -> list[Path]:
        dirs = self.pf.all_agents_dirs(self.slug)
        # ... scan dirs for agent files
```

Pathfinder handles **where** to look. Platform handles **what** to look for and **how** to parse it.

---

## 8. Success Criteria

1. **Zero scattered path construction** — `grep -r "Path.home().*\.claude" agent_transfer/` returns results ONLY in `pathfinder.py`
2. **5 platform profiles registered** — Claude Code, Codex, Gemini CLI, Goose, OpenCode
3. **All existing tests pass** — No regressions (R5, R11)
4. **Path remapping works** — Cross-machine config imports use pathfinder's `remap_path()`
5. **Env override works** — Setting `$CLAUDE_CONFIG_DIR` changes all resolved paths
6. **Adversarial scan passes** — No CRITICAL or HIGH findings (R12)

---

## 9. Implementation Phases

### Phase A: Core Module (pathfinder.py)
1. Define `PathProfile` dataclass
2. Define `PathProfileRegistry` with 5 built-in profiles
3. Implement `Pathfinder` class — config_dir, agents_dir, skills_dir, hooks_dir, config_files
4. Implement project-level resolution (search up from cwd)
5. Implement `remap_path()` and `translate_path()`
6. Implement `find_executable()` with consolidated search strategies
7. Implement `get_pathfinder()` singleton
8. Unit tests for all methods

### Phase B: Refactor Existing Modules
1. Refactor `discovery.py` — delegate to pathfinder
2. Refactor `config_manager.py` — use pathfinder for config paths + remap
3. Refactor `transfer.py` — use pathfinder for import/export paths
4. Refactor `import_analyzer.py` — use pathfinder for agent lookup
5. Refactor `skill_discovery.py` — use pathfinder for skill dirs
6. Refactor `tool_checker.py` — use pathfinder for MCP config locations
7. Refactor `cli.py` — use pathfinder for display paths
8. Run full test suite — zero regressions

### Phase C: Validation
1. Adversarial bug hunt — targeted (path traversal, edge cases)
2. Adversarial bug hunt — general logic scan
3. Verify grep shows zero scattered path construction
4. Git checkpoint

---

## 10. Dependencies

```
Pathfinder Module (this PRD)
    └── Required BY Phase 2: Platform Abstraction Layer (tasks.md T022-T034)
    └── Required BY Phase 3: IR Ingestors/Emitters (need platform paths)
    └── Required BY config_manager.py refactor (already uses ad-hoc remapping)
    └── Blocks nothing in Phase 1 bug fixes (can run in parallel with T001-T014)
```

---

## 11. Open Questions

1. **Should pathfinder auto-detect which platforms are installed?** Or should that stay in `platforms/` (Phase 2)? Proposed: Pathfinder resolves paths but does NOT check if platforms are installed. Platform detection stays in Phase 2's `BasePlatform.detect()`.

2. **Should pathfinder handle MCP server path resolution?** MCP servers have their own `command` paths (e.g., `npx`, `uvx`, `node`). Proposed: Out of scope — MCP command resolution stays in runtime tools.

3. **Cache invalidation strategy?** If user installs Claude Code mid-session, should pathfinder notice? Proposed: Cache with TTL (5 min for executable lookups) + manual `clear_cache()`.

4. **Should project-level search depth be configurable?** Currently hardcoded to 5 levels up. Proposed: Default 5, configurable via `Pathfinder(project_search_depth=N)`.
