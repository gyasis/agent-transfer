# Quickstart: Pathfinder Module

**Feature**: 001-pathfinder-module
**Date**: 2026-03-11

## What This Feature Does

Pathfinder centralizes all filesystem path resolution for agent-transfer. Instead of every module independently constructing paths like `Path.home() / '.claude' / 'agents'`, they all call `pathfinder.agents_dir("claude-code")`.

## Basic Usage

```python
from agent_transfer.utils.pathfinder import get_pathfinder

pf = get_pathfinder()

# Resolve platform directories
config = pf.config_dir("claude-code")        # ~/.claude
agents = pf.agents_dir("claude-code")        # ~/.claude/agents
skills = pf.skills_dir("goose")              # ~/.config/goose/recipes

# Find executables
exe = pf.find_executable("claude-code")      # /usr/local/bin/claude or None

# Project-level resolution
proj_agents = pf.project_agents_dir("claude-code")  # .claude/agents or None

# Cross-machine remapping
remapped = pf.remap_path(
    Path("/home/alice/.claude/hooks/pre-commit.sh"),
    source_home="/home/alice",
    target_home="/home/bob"
)
# -> /home/bob/.claude/hooks/pre-commit.sh

# Cross-platform translation
translated, warning = pf.translate_path(
    "~/.claude/skills/my-skill/",
    from_platform="claude-code",
    to_platform="goose"
)
# -> ~/.config/goose/recipes/my-skill/

# List supported platforms
platforms = pf.supported_platforms()
# -> ["claude-code", "codex", "gemini-cli", "goose", "opencode"]
```

## Migration Pattern (for existing modules)

Before:
```python
agents_dir = Path.home() / '.claude' / 'agents'
project_agents = Path.cwd() / '.claude' / 'agents'
```

After:
```python
from agent_transfer.utils.pathfinder import get_pathfinder
pf = get_pathfinder()
agents_dir = pf.agents_dir("claude-code")
project_agents = pf.project_agents_dir("claude-code")
```

## Adding a New Platform

```python
from agent_transfer.utils.pathfinder import PathProfile, get_pathfinder

profile = PathProfile(
    slug="my-platform",
    config_dir=".my-platform",
    agents_subdir="agents",
    skills_subdir="extensions",
    hooks_subdir=None,
    config_files=["config.yaml"],
    executable_names=["myplatform"],
    project_level=False,
    project_config_dir=None,
    env_override_var="MY_PLATFORM_HOME",
    search_paths=[],
)

pf = get_pathfinder()
pf.register_profile(profile)
```

## Key Design Decisions

1. **Singleton**: `get_pathfinder()` returns the same instance everywhere — shared cache, consistent results
2. **None for missing dirs**: If a platform doesn't have a directory type (e.g., Goose has no agents dir), methods return `None`
3. **Env overrides propagate**: Setting `$CLAUDE_CONFIG_DIR` changes agents_dir, skills_dir, hooks_dir, and config_files too
4. **No platform detection**: Pathfinder resolves paths. It does NOT check if a platform is installed. That's Phase 2.
