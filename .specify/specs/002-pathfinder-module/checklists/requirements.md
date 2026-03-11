# Requirements Checklist: 002 — Pathfinder Module

## Core Module
- [ ] `PathProfile` dataclass with all fields
- [ ] `PathProfileRegistry` with register/get/list methods
- [ ] 5 built-in profiles: claude-code, codex, gemini-cli, goose, opencode
- [ ] `Pathfinder` class with singleton `get_pathfinder()`
- [ ] `config_dir(platform)` — user-level config directory
- [ ] `agents_dir(platform)` — user-level agents directory
- [ ] `skills_dir(platform)` — user-level skills directory
- [ ] `hooks_dir(platform)` — user-level hooks directory
- [ ] `config_files(platform)` — list of config file paths
- [ ] `project_agents_dir(platform)` — project-level agents (search up from cwd)
- [ ] `project_skills_dir(platform)` — project-level skills
- [ ] `all_agents_dirs(platform)` — user + project combined
- [ ] `all_skills_dirs(platform)` — user + project combined
- [ ] `find_executable(platform)` — consolidated multi-strategy search
- [ ] `remap_path(path, source_home, target_home)` — cross-machine
- [ ] `translate_path(path, from_platform, to_platform)` — cross-platform
- [ ] `validate_path(path)` — existence check
- [ ] `ensure_dir(path)` — create if missing
- [ ] `supported_platforms()` — list registered slugs
- [ ] `clear_cache()` — invalidate cached lookups
- [ ] Environment variable overrides per platform
- [ ] Caching with TTL for expensive lookups

## Refactor Consumers
- [ ] `discovery.py` → delegate to pathfinder
- [ ] `config_manager.py` → use pathfinder config_files + remap_path
- [ ] `transfer.py` → use pathfinder agents_dir/skills_dir
- [ ] `import_analyzer.py` → use pathfinder agents_dir
- [ ] `skill_discovery.py` → use pathfinder all_skills_dirs
- [ ] `tool_checker.py` → use pathfinder config_files
- [ ] `cli.py` → use pathfinder skills_dir

## Validation
- [ ] Zero `Path.home() / '.claude'` outside pathfinder.py (grep audit)
- [ ] All existing tests pass (zero regressions)
- [ ] Unit tests for PathProfile, PathProfileRegistry, Pathfinder
- [ ] Unit tests for remap_path edge cases
- [ ] Unit tests for translate_path all platform pairs
- [ ] Unit tests for find_executable strategies
- [ ] Unit tests for project-level search (mock cwd)
- [ ] Unit tests for env override
- [ ] Adversarial bug hunt — targeted (path traversal, symlinks)
- [ ] Adversarial bug hunt — general logic scan
- [ ] Git checkpoint
