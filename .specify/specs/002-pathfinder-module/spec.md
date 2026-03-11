# Feature Spec: 002 — Pathfinder Module

**Source PRD:** `prd/pathfinder-module.md`
**Branch:** `feature/pathfinder-module`
**Status:** Specified
**Author:** Gyasi Sutton
**Date:** 2026-03-11

---

## Summary

Centralized path resolution module (`agent_transfer/utils/pathfinder.py`) that replaces 35+ scattered path constructions across 7 modules with a single platform-aware resolver. Prerequisite for v2 multi-platform support.

---

## User Stories

### US-PF1: Centralized Path Resolution
> As a contributor, I want a single module that resolves all platform paths so I don't duplicate path logic across modules.

**Acceptance:**
- All 7 consumer modules use pathfinder instead of direct `Path.home() / '.claude'`
- Zero `Path.home() / '.claude'` outside `pathfinder.py`
- All existing tests pass

### US-PF2: Multi-Platform Path Profiles
> As a developer adding Goose support, I want to register Goose's path profile once and have all modules automatically resolve Goose paths.

**Acceptance:**
- `pf.config_dir("goose")` returns `~/.config/goose`
- `pf.skills_dir("goose")` returns `~/.config/goose/recipes`
- New platform = new PathProfile only, no changes to consumers

### US-PF3: Cross-Machine Path Remapping
> As a user importing configs from a colleague's machine, I want paths auto-remapped to my home directory.

**Acceptance:**
- `pf.remap_path()` translates `/home/alice/.claude/...` to `/home/bob/.claude/...`
- `config_manager.py` uses `pf.remap_path()` instead of ad-hoc remapping
- Edge cases handled: no home prefix, already-correct, relative paths

### US-PF4: Environment Variable Overrides
> As a developer with a non-standard install, I want to set `$CLAUDE_CONFIG_DIR` to override the default config location.

**Acceptance:**
- `pf.config_dir("claude-code")` checks `$CLAUDE_CONFIG_DIR` first
- Override propagates to all dependent paths (agents, skills, hooks, configs)

### US-PF5: Cross-Platform Path Translation
> As a user converting a Claude Code agent to Goose, I want internal path references translated to Goose-appropriate paths.

**Acceptance:**
- `~/.claude/skills/X` becomes `~/.config/goose/recipes/X` for Goose
- Untranslatable paths flagged with warning

---

## Technical Design

### Module Structure

```
agent_transfer/utils/pathfinder.py
    PathProfile          — Dataclass: platform filesystem layout
    PathProfileRegistry  — Registry: built-in + entry_points plugins
    Pathfinder           — Main class: resolve, remap, translate, find
    get_pathfinder()     — Singleton accessor
```

### PathProfile Dataclass

```python
@dataclass
class PathProfile:
    slug: str                        # "claude-code"
    config_dir: str                  # Relative to home: ".claude"
    agents_subdir: str | None        # "agents"
    skills_subdir: str | None        # "skills", "recipes", "plugins"
    hooks_subdir: str | None         # "hooks" or None
    config_files: list[str]          # ["mcp.json", "settings.json"]
    executable_names: list[str]      # ["claude"]
    project_level: bool              # True = has .claude/agents in projects
    project_config_dir: str | None   # ".claude" for project-level
    env_override_var: str | None     # "CLAUDE_CONFIG_DIR"
    search_paths: list[str]          # Extra executable search locations
```

### Built-in Profiles

| Platform | slug | config_dir | agents | skills | hooks | config_files |
|----------|------|-----------|--------|--------|-------|-------------|
| Claude Code | `claude-code` | `.claude` | `agents` | `skills` | `hooks` | `mcp.json`, `settings.json`, `settings.local.json` |
| Codex CLI | `codex` | `.codex` | N/A | `~/.agents/skills` (absolute) | N/A | TOML |
| Gemini CLI | `gemini-cli` | `.gemini` | `agents` | `skills` | N/A | `settings.json` |
| Goose | `goose` | `.config/goose` | N/A | `recipes` | N/A | `profiles.yaml` |
| OpenCode | `opencode` | `.opencode` | `agents` | `plugins` | N/A | `opencode.json` |

### Core API

```python
pf = get_pathfinder()

# Directory resolution
pf.config_dir(platform)            # -> Path
pf.agents_dir(platform)            # -> Path | None
pf.skills_dir(platform)            # -> Path | None
pf.hooks_dir(platform)             # -> Path | None
pf.config_files(platform)          # -> list[Path]

# Project-level
pf.project_agents_dir(platform)    # -> Path | None (searches up from cwd)
pf.project_skills_dir(platform)    # -> Path | None

# All directories (user + project)
pf.all_agents_dirs(platform)       # -> list[tuple[Path, str]]
pf.all_skills_dirs(platform)       # -> list[tuple[Path, str]]

# Executable
pf.find_executable(platform)       # -> Path | None

# Cross-machine remapping
pf.remap_path(path, source_home, target_home)  # -> Path

# Cross-platform translation
pf.translate_path(path, from_platform, to_platform)  # -> Path

# Utilities
pf.validate_path(path)             # -> bool
pf.ensure_dir(path)                # -> Path (creates if missing)
pf.supported_platforms()           # -> list[str]
pf.clear_cache()                   # Invalidate cached lookups
```

### Executable Discovery (consolidated from discovery.py)

Ordered search strategy:
1. `shutil.which(name)` — PATH lookup
2. Environment override variable
3. npm global paths (`~/.npm-global/bin/`, `~/.local/share/npm/bin/`)
4. npm prefix (`npm config get prefix` + `/bin/`)
5. nvm paths (`~/.nvm/versions/node/*/bin/`)
6. Virtual environment (`$VIRTUAL_ENV/bin/`)
7. Conda environment (`$CONDA_PREFIX/bin/`)
8. System paths (`/usr/local/bin/`, `/usr/bin/`)
9. Custom `PathProfile.search_paths`

Only strategies relevant to each platform are used (e.g., Goose skips npm/nvm).

### Caching Strategy

- Executable lookups cached with 5-min TTL
- Directory existence cached per session
- `clear_cache()` for manual invalidation
- Cache key includes cwd for project-level paths

---

## Constraints

- **R3**: Linux + WSL only. No macOS or Windows paths.
- **R4**: Wrap existing logic. `discovery.py` becomes thin wrapper around pathfinder.
- **R5**: Backward compatible. No changes to CLI behavior.
- **R6**: No hardcoded absolute paths in pathfinder — use `Path.home()` + env vars.
- **R9**: Path profiles pluggable via entry_points.
- **R11**: Full test coverage for all pathfinder methods.
- **R12**: Adversarial scan before merge.

---

## Refactoring Map

| Module | Lines Affected | Change |
|--------|---------------|--------|
| `discovery.py` | ~170 lines | Delegate executable + config + agent dir lookups to pathfinder |
| `config_manager.py` | ~30 lines | Use `pf.config_files()`, `pf.remap_path()` |
| `transfer.py` | ~20 lines | Use `pf.agents_dir()`, `pf.skills_dir()` |
| `import_analyzer.py` | ~10 lines | Use `pf.agents_dir()`, `pf.project_agents_dir()` |
| `skill_discovery.py` | ~15 lines | Use `pf.all_skills_dirs()` |
| `tool_checker.py` | ~10 lines | Use `pf.config_files("claude-code", "mcp.json")` |
| `cli.py` | ~10 lines | Use `pf.skills_dir()`, `pf.project_skills_dir()` |

---

## Success Criteria

1. `grep -r "Path.home().*\.claude" agent_transfer/` returns ONLY `pathfinder.py`
2. 5 platform profiles registered and tested
3. All existing tests pass (zero regressions)
4. `remap_path()` works for cross-machine imports
5. Env override (`$CLAUDE_CONFIG_DIR`) changes all resolved paths
6. Adversarial scan: zero CRITICAL/HIGH findings

---

## Dependencies

- **Prerequisite for:** Phase 2 Platform Abstraction (T022-T034)
- **Prerequisite for:** Phase 3 IR Ingestors/Emitters
- **Parallel with:** Phase 1 Bug Fixes (T001-T014)
- **Blocks:** Nothing currently in progress
