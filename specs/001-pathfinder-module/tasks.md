# Tasks: Pathfinder Module — Centralized Path Resolution

**Input**: Design documents from `/specs/001-pathfinder-module/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/pathfinder-api.md

**Tests**: Test tasks included — constitution R11 requires test coverage for every new module.

**Organization**: Tasks grouped by user story. US1+US2 combined (both P1, tightly coupled). Module refactoring is a dedicated phase since it depends on all core pathfinder features.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Exact file paths included in descriptions

## Phase 1: Setup

**Purpose**: Create the pathfinder module file and establish test infrastructure

- [x] T001 Create `agent_transfer/utils/pathfinder.py` with module docstring, `from __future__ import annotations` import, and empty `__all__` list
- [x] T002 [P] Create `tests/test_pathfinder.py` with pytest imports, basic fixtures for `tmp_path` home directory mocking, and `_reset_pathfinder()` teardown in autouse fixture
- [x] T003 [P] Add `pathfinder` imports to `agent_transfer/utils/__init__.py` (lazy import to avoid circular deps)

**Checkpoint**: Module files exist, test infrastructure ready

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data structures that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 Implement `PathProfile` dataclass in `agent_transfer/utils/pathfinder.py` with fields: `slug`, `config_dir`, `agents_subdir`, `skills_subdir`, `hooks_subdir`, `config_files`, `executable_names`, `project_level`, `project_config_dir`, `env_override_var`, `search_paths` — all using `Optional` and `List` from typing for Python 3.8 compat
- [x] T005 Implement `PathProfileRegistry` class in `agent_transfer/utils/pathfinder.py` with `register()`, `get()`, `list_slugs()` methods and `_profiles` dict storage. `get()` raises `KeyError` with helpful message listing valid slugs
- [x] T006 Implement `Pathfinder` class skeleton in `agent_transfer/utils/pathfinder.py` with `__init__(self, project_search_depth=5)` that creates a `PathProfileRegistry` and `_cache` dict. Add `clear_cache()` and `supported_platforms()` methods
- [x] T007 Implement `get_pathfinder()` and `_reset_pathfinder()` module-level functions in `agent_transfer/utils/pathfinder.py` using lazy-initialized `_instance` global
- [x] T008 Write unit tests for `PathProfile` creation and field defaults in `tests/test_pathfinder.py`
- [x] T009 Write unit tests for `PathProfileRegistry` — register, get, list_slugs, KeyError on unknown slug in `tests/test_pathfinder.py`
- [x] T010 Write unit tests for `get_pathfinder()` singleton behavior and `_reset_pathfinder()` isolation in `tests/test_pathfinder.py`

**Checkpoint**: Foundation ready — PathProfile, Registry, and Pathfinder skeleton work. All unit tests pass.

---

## Phase 3: User Story 1 + 2 — Core Path Resolution & Multi-Platform Profiles (Priority: P1) 🎯 MVP

**Goal**: Pathfinder resolves config, agents, skills, hooks, and config file paths for all 5 platforms via registered path profiles.

**Independent Test**: Call `pf.config_dir("claude-code")`, `pf.agents_dir("goose")`, `pf.skills_dir("opencode")` etc. and verify correct paths. Call `pf.supported_platforms()` and verify all 5 returned. Register a mock 6th profile and confirm it works without code changes.

### Implementation

- [x] T011 [US1] [US2] Define all 5 built-in `PathProfile` instances in `agent_transfer/utils/pathfinder.py`: Claude Code (`.claude`), Codex CLI (`.codex`), Gemini CLI (`.gemini`), Goose (`.config/goose`), OpenCode (`.opencode`) — with correct subdirs, config files, executable names, and env override vars per PRD table 4.1
- [x] T012 [US1] [US2] Implement `_load_builtin_profiles()` in `PathProfileRegistry` and call from `__init__`. Also implement `load_entry_points()` to scan `agent_transfer.path_profiles` entry point group (graceful no-op if none found)
- [x] T013 [US1] Implement `config_dir(slug)` in `Pathfinder` — resolve `Path.home() / profile.config_dir`, return absolute path. Use `_cache` for results
- [x] T014 [P] [US1] Implement `agents_dir(slug)`, `skills_dir(slug)`, `hooks_dir(slug)` in `Pathfinder` — derive from `config_dir()` + profile subdirs. Return `None` if subdir is `None`
- [x] T015 [P] [US1] Implement `config_files(slug)` in `Pathfinder` — return list of `config_dir / filename` for each entry in `profile.config_files`
- [x] T016 [US1] Implement `project_agents_dir(slug, start_dir)` and `project_skills_dir(slug, start_dir)` in `Pathfinder` — search upward from `start_dir` (default `Path.cwd()`) for `project_config_dir / subdir`, stopping at `project_search_depth` levels or filesystem root. Return `None` if not found or platform doesn't support project-level
- [x] T017 [US1] Implement `all_agents_dirs(slug)` and `all_skills_dirs(slug)` in `Pathfinder` — return `List[Tuple[Path, str]]` combining user-level and project-level results with scope labels `"user"` and `"project"`
- [x] T018 [P] [US1] Implement `validate_path(path)` and `ensure_dir(path)` utility methods in `Pathfinder`
- [x] T019 [US1] Implement `register_profile(profile)` on `Pathfinder` that delegates to `registry.register()` and clears cache
- [x] T020 [US1] [US2] Update `__all__` in `agent_transfer/utils/pathfinder.py` to export `PathProfile`, `PathProfileRegistry`, `Pathfinder`, `get_pathfinder`

### Tests

- [x] T021 [P] [US1] [US2] Write tests for all 5 built-in profiles in `tests/test_pathfinder.py` — verify `config_dir`, `agents_dir`, `skills_dir`, `hooks_dir`, `config_files` for each platform using monkeypatched `Path.home()`
- [x] T022 [P] [US1] Write tests for `None` returns — `hooks_dir("codex")`, `agents_dir("goose")` should return `None` in `tests/test_pathfinder.py`
- [x] T023 [P] [US1] Write tests for project-level resolution in `tests/test_pathfinder.py` — create `.claude/agents/` in tmp_path tree, verify `project_agents_dir` finds it. Verify returns `None` when not found
- [x] T024 [P] [US1] Write tests for `all_agents_dirs` and `all_skills_dirs` in `tests/test_pathfinder.py` — verify combined user+project results with scope labels
- [x] T025 [US2] Write test for third-party profile registration in `tests/test_pathfinder.py` — register a mock profile, verify all resolution methods work for it

**Checkpoint**: Core pathfinder resolves paths for all 5 platforms. This is the MVP — all consuming modules could start using it.

---

## Phase 4: User Story 6 — Executable Discovery (Priority: P2)

**Goal**: Single `find_executable()` method consolidates 7 search strategies from `discovery.py`.

**Independent Test**: Mock executables in various PATH locations and verify `find_executable("claude-code")` finds them in priority order.

### Implementation

- [x] T026 [US6] Implement `find_executable(slug)` in `Pathfinder` in `agent_transfer/utils/pathfinder.py` — ordered search: `shutil.which()` → env override path → npm global (`~/.npm-global/bin/`, `~/.local/share/npm/bin/`) → npm prefix (`npm config get prefix`) → nvm paths → virtualenv → conda → system paths (`/usr/local/bin/`, `/usr/bin/`) → `profile.search_paths`. Cache results. Return `Optional[Path]`
- [x] T027 [US6] Add platform-specific search strategy filtering — only run npm/nvm strategies for platforms whose profiles need them (Claude Code, Codex). Skip for Goose, OpenCode, Gemini CLI

### Tests

- [x] T028 [P] [US6] Write test for `find_executable` with mocked `shutil.which` success in `tests/test_pathfinder.py`
- [x] T029 [P] [US6] Write test for `find_executable` fallback chain — `shutil.which` fails, falls back to npm global path in `tests/test_pathfinder.py`
- [x] T030 [P] [US6] Write test for `find_executable` returns `None` when not found anywhere in `tests/test_pathfinder.py`
- [x] T031 [US6] Write test for executable caching — verify `shutil.which` called once for repeated lookups, cleared by `clear_cache()` in `tests/test_pathfinder.py`

**Checkpoint**: Executable discovery consolidated. `discovery.py` can delegate to pathfinder.

---

## Phase 5: User Story 3 — Cross-Machine Path Remapping (Priority: P2)

**Goal**: `remap_path()` translates paths between machines during config import.

**Independent Test**: Remap `/home/alice/.claude/hooks/pre-commit.sh` to `/home/bob/...` and verify.

### Implementation

- [x] T032 [US3] Implement `remap_path(path, source_home, target_home)` in `Pathfinder` in `agent_transfer/utils/pathfinder.py` — string prefix replacement. Return original path if: relative, no source_home prefix, or already matches target_home

### Tests

- [x] T033 [P] [US3] Write test for successful path remapping in `tests/test_pathfinder.py`
- [x] T034 [P] [US3] Write test for no-op cases: relative path, no prefix match, already-correct path in `tests/test_pathfinder.py`
- [x] T035 [P] [US3] Write test for edge case: source_home embedded in non-prefix position (e.g., `/opt/home/alice/...`) in `tests/test_pathfinder.py`

**Checkpoint**: Path remapping works. `config_manager.py` can delegate to pathfinder.

---

## Phase 6: User Story 4 — Environment Variable Overrides (Priority: P2)

**Goal**: Setting `$CLAUDE_CONFIG_DIR` (or platform equivalent) overrides `config_dir()` and all derived paths.

**Independent Test**: Set env var, verify `config_dir`, `agents_dir`, `skills_dir`, `hooks_dir`, `config_files` all reflect override.

### Implementation

- [x] T036 [US4] Update `config_dir(slug)` in `Pathfinder` in `agent_transfer/utils/pathfinder.py` to check `os.environ.get(profile.env_override_var)` first, fall back to default. Ensure override propagates to all derived methods (`agents_dir`, `skills_dir`, etc.) since they call `config_dir` internally

### Tests

- [x] T037 [P] [US4] Write test for env override on `config_dir` using `monkeypatch.setenv` in `tests/test_pathfinder.py`
- [x] T038 [P] [US4] Write test for env override propagation to `agents_dir`, `skills_dir`, `hooks_dir`, `config_files` in `tests/test_pathfinder.py`
- [x] T039 [US4] Write test for fallback when env var is not set in `tests/test_pathfinder.py`

**Checkpoint**: Environment overrides work. Non-standard installations supported.

---

## Phase 7: User Story 5 — Cross-Platform Path Translation (Priority: P3)

**Goal**: `translate_path()` converts platform-specific path references between platforms.

**Independent Test**: Translate `~/.claude/skills/my-skill/` from Claude Code to Goose and verify `~/.config/goose/recipes/my-skill/`.

### Implementation

- [x] T040 [US5] Implement `translate_path(path, from_platform, to_platform)` in `Pathfinder` in `agent_transfer/utils/pathfinder.py` — build map of expanded platform dirs, match longest prefix, swap with target platform equivalent. Return `(translated_path, warning)` tuple. Warning is `None` on success or descriptive message if path doesn't match any known dir

### Tests

- [x] T041 [P] [US5] Write test for successful translation Claude Code → Goose skills path in `tests/test_pathfinder.py`
- [x] T042 [P] [US5] Write test for translation with unrecognized path — verify warning returned in `tests/test_pathfinder.py`
- [x] T043 [P] [US5] Write test for translation between all 5 platforms for config_dir paths in `tests/test_pathfinder.py`

**Checkpoint**: Cross-platform translation works. Phase 3+ cross-platform conversion ready.

---

## Phase 8: Module Refactoring (US1 Completion)

**Purpose**: Refactor all 7 existing modules to use pathfinder instead of direct path construction. This completes US1's acceptance scenario 4: "zero `Path.home().*\.claude` in any module except pathfinder.py."

**⚠️ Depends on**: Phases 3-6 complete (all pathfinder features needed by consuming modules)

- [x] T044 [US1] Refactor `agent_transfer/utils/discovery.py` — replace 7 executable search strategies and 4 config location searches with `pf.find_executable()`, `pf.config_dir()`, `pf.all_agents_dirs()`. Keep function signatures unchanged (R4, R5)
- [x] T045 [US1] Refactor `agent_transfer/utils/config_manager.py` — replace `Path.home() / '.claude'` for mcp.json, settings.json, settings.local.json with `pf.config_files()`. Replace ad-hoc path remapping with `pf.remap_path()`. Keep function signatures unchanged
- [x] T046 [US1] Refactor `agent_transfer/utils/transfer.py` — replace `Path.home() / '.claude' / 'agents'`, `Path.home() / '.claude' / 'skills'`, and `Path.cwd()` variants with `pf.agents_dir()`, `pf.skills_dir()`, `pf.project_agents_dir()`, `pf.project_skills_dir()`. Keep function signatures unchanged
- [x] T047 [P] [US1] Refactor `agent_transfer/utils/import_analyzer.py` — replace `Path.home() / '.claude' / 'agents'` with `pf.agents_dir()` and `pf.project_agents_dir()`. Keep function signatures unchanged
- [x] T048 [P] [US1] Refactor `agent_transfer/utils/skill_discovery.py` — replace `Path.home() / '.claude' / 'skills'` and recursive cwd search with `pf.all_skills_dirs()`. Keep function signatures unchanged
- [x] T049 [P] [US1] Refactor `agent_transfer/utils/tool_checker.py` — replace 5 MCP config location checks with `pf.config_files("claude-code")`. Keep function signatures unchanged
- [x] T050 [US1] Refactor `agent_transfer/cli.py` — replace `Path.home() / '.claude' / 'skills'` and `Path.cwd()` variants with `pf.skills_dir()`, `pf.project_skills_dir()`. Keep function signatures unchanged
- [x] T051 [US1] Run full test suite (`pytest tests/`) and verify zero regressions — all existing tests pass
- [x] T052 [US1] Run `grep -r "Path.home().*\.claude" agent_transfer/` and verify results appear ONLY in `pathfinder.py`

**Checkpoint**: All modules use pathfinder. Zero scattered path construction. All existing tests pass.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Validation, adversarial testing, and cleanup

- [x] T053 [P] Run ruff linter on `agent_transfer/utils/pathfinder.py` and fix all findings
- [x] T054 [P] Run ruff linter on all 7 refactored modules and fix all findings
- [x] T055 Adversarial bug hunt — targeted: path traversal in `remap_path()` and `translate_path()`, edge cases in project-level search, symlink handling, container edge cases (run adversarial-bug-hunter agent)
- [x] T056 Adversarial bug hunt — general logic scan across pathfinder.py and all refactored modules (run adversarial-bug-hunter agent)
- [x] T057 Validate quickstart.md examples work against actual implementation
- [ ] T058 Git checkpoint — commit all changes

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1
- **US1+US2 Core Resolution (Phase 3)**: Depends on Phase 2
- **US6 Executable Discovery (Phase 4)**: Depends on Phase 2. **Parallel with Phases 5, 6, 7**
- **US3 Path Remapping (Phase 5)**: Depends on Phase 2. **Parallel with Phases 4, 6, 7**
- **US4 Env Overrides (Phase 6)**: Depends on Phase 3 (modifies `config_dir`). **Parallel with Phases 4, 5, 7**
- **US5 Cross-Platform Translation (Phase 7)**: Depends on Phase 3. **Parallel with Phases 4, 5, 6**
- **Module Refactoring (Phase 8)**: Depends on Phases 3, 4, 5, 6 (needs all pathfinder features)
- **Polish (Phase 9)**: Depends on Phase 8

### User Story Dependencies

- **US1+US2 (P1)**: Foundation → Core implementation → Module refactoring (spans Phases 3 and 8)
- **US6 (P2)**: Foundation → Executable discovery (Phase 4, independent)
- **US3 (P2)**: Foundation → Path remapping (Phase 5, independent)
- **US4 (P2)**: Core resolution → Env overrides (Phase 6, depends on Phase 3)
- **US5 (P3)**: Core resolution → Translation (Phase 7, depends on Phase 3)

### Within Each Phase

- Tasks marked [P] can run in parallel
- Sequential tasks depend on preceding tasks in the same phase

### Parallel Opportunities

```
Phase 2: T008 [P] + T009 [P] + T010 [P] (test tasks)
Phase 3: T014 [P] + T015 [P] + T018 [P] (independent methods)
Phase 3: T021 [P] + T022 [P] + T023 [P] + T024 [P] + T025 [P] (test tasks)
Phase 4-7: ALL FOUR PHASES can run in parallel after Phase 3
Phase 8: T047 [P] + T048 [P] + T049 [P] (independent module refactors)
Phase 9: T053 [P] + T054 [P] (linting), T055 [P] + T056 [P] (bug hunting)
```

---

## Parallel Example: Phase 3 (MVP)

```bash
# After T013 (config_dir), launch parallel methods:
Task: "T014 [P] Implement agents_dir, skills_dir, hooks_dir"
Task: "T015 [P] Implement config_files"
Task: "T018 [P] Implement validate_path, ensure_dir"

# After implementation, launch all tests in parallel:
Task: "T021 [P] Tests for 5 built-in profiles"
Task: "T022 [P] Tests for None returns"
Task: "T023 [P] Tests for project-level resolution"
Task: "T024 [P] Tests for all_agents_dirs, all_skills_dirs"
Task: "T025 [P] Test for third-party profile registration"
```

---

## Implementation Strategy

### MVP First (Phase 1-3 Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T010)
3. Complete Phase 3: US1+US2 Core Resolution (T011-T025)
4. **STOP and VALIDATE**: All 5 platforms resolve correctly, tests pass
5. This alone delivers the primary value — centralized path resolution

### Incremental Delivery

1. Setup + Foundational → Core ready
2. Phase 3: Core resolution → **MVP** — 5 platforms resolve correctly
3. Phases 4-7 (parallel): Add executable discovery, remapping, env overrides, translation
4. Phase 8: Refactor all modules → Full integration, zero scattered paths
5. Phase 9: Polish → Adversarial testing, linting, checkpoint

### Single Developer Strategy (Recommended)

1. Phases 1-3 sequentially → MVP checkpoint
2. Phase 6 (env overrides) → enhances Phase 3 immediately
3. Phase 4 (executable) → needed for discovery.py refactor
4. Phase 5 (remapping) → needed for config_manager.py refactor
5. Phase 7 (translation) → future-facing, can defer
6. Phase 8 (refactoring) → the big payoff
7. Phase 9 (polish) → adversarial scan + commit

---

## Notes

- [P] tasks = different files or independent methods, no dependencies
- [Story] label maps task to specific user story for traceability
- Constitution R4 (Wrap Don't Rewrite): Refactored modules keep their function signatures — they become thin wrappers around pathfinder
- Constitution R5 (Backward Compat): All existing tests must pass after refactoring
- Constitution R11 (Test Coverage): Every new method has corresponding tests
- Constitution R12 (Adversarial): T055+T056 run targeted + general adversarial scans before merge
- Python 3.8 compat: Use `from __future__ import annotations`, `Optional`, `List`, `Tuple` from typing
