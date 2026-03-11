# Data Model: Pathfinder Module

**Date**: 2026-03-11
**Feature**: 001-pathfinder-module

## Entities

### PathProfile

Defines a platform's filesystem layout. Immutable after creation.

| Field | Type | Description | Example (Claude Code) |
|-------|------|-------------|----------------------|
| slug | str | Unique platform identifier | `"claude-code"` |
| config_dir | str | Relative to home directory | `".claude"` |
| agents_subdir | str or None | Relative to config_dir | `"agents"` |
| skills_subdir | str or None | Relative to config_dir | `"skills"` |
| hooks_subdir | str or None | Relative to config_dir | `"hooks"` |
| config_files | list of str | Config filenames in config_dir | `["mcp.json", "settings.json", "settings.local.json"]` |
| executable_names | list of str | Executable names to search PATH | `["claude"]` |
| project_level | bool | Supports project-level dirs? | `True` |
| project_config_dir | str or None | Project-level config dir name | `".claude"` |
| env_override_var | str or None | Env var to override config_dir | `"CLAUDE_CONFIG_DIR"` |
| search_paths | list of str | Extra executable search paths | `[]` |

### Built-in Profiles

| Platform | slug | config_dir | agents | skills | hooks | project_level |
|----------|------|-----------|--------|--------|-------|--------------|
| Claude Code | `claude-code` | `.claude` | `agents` | `skills` | `hooks` | Yes (`.claude`) |
| Codex CLI | `codex` | `.codex` | None | None | None | No |
| Gemini CLI | `gemini-cli` | `.gemini` | `agents` | `skills` | None | No |
| Goose | `goose` | `.config/goose` | None | `recipes` | None | No |
| OpenCode | `opencode` | `.opencode` | `agents` | `plugins` | None | Yes (`.opencode`) |

Note: Codex uses `~/.agents/skills` for both agents and skills, which differs from the subdirectory pattern. The profile uses `search_paths` to handle this — `agents_subdir` and `skills_subdir` are None because they're not relative to `config_dir`.

### PathProfileRegistry

Collection of PathProfile instances, keyed by slug.

| Field | Type | Description |
|-------|------|-------------|
| _profiles | dict (str to PathProfile) | Slug-keyed profile store |

**Operations**:
- `register(profile)` — Add or replace a profile
- `get(slug)` — Retrieve profile by slug, raise KeyError if not found
- `list_slugs()` — Return all registered platform slugs
- `load_entry_points()` — Scan `agent_transfer.path_profiles` entry point group

### Pathfinder

Main resolver class. Holds a registry and caches.

| Field | Type | Description |
|-------|------|-------------|
| registry | PathProfileRegistry | Profile store |
| project_search_depth | int | Max levels to search upward (default 5) |
| _cache | dict | Method result cache keyed by (slug, method, args) |

## Relationships

```
PathProfileRegistry 1---* PathProfile
       |
       | owns
       |
   Pathfinder (singleton via get_pathfinder())
```

- One `Pathfinder` instance exists per process (singleton)
- `Pathfinder` owns one `PathProfileRegistry`
- `PathProfileRegistry` contains 5+ `PathProfile` instances
- Consuming modules (discovery.py, transfer.py, etc.) reference the singleton `Pathfinder`

## Validation Rules

- `PathProfile.slug` must be non-empty and unique within the registry
- `PathProfile.config_dir` must be non-empty (every platform has a config location)
- `PathProfile.executable_names` must have at least one entry
- Paths returned by Pathfinder are always absolute (resolved via `Path.home()`)
- `remap_path()` input paths must be absolute; relative paths are returned unchanged
- `translate_path()` returns the original path unchanged if no platform prefix matches

## State Transitions

Pathfinder is stateless beyond its cache. No lifecycle state machine.

Cache states:
- **Cold** — First call for a (slug, method) pair. Full resolution performed.
- **Warm** — Subsequent calls return cached result.
- **Cleared** — After `clear_cache()`, all entries removed. Next call is cold again.
