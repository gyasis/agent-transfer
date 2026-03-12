# Tasks: Preflight Transfer Readiness Validation

**Input**: Design documents from `specs/002-preflight-check/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/preflight-api.md

**Organization**: Tasks grouped by user story. US1/US2/US3 are all P1 but sequenced because US3 (export/manifest) provides the data US1 (preflight check) reads, and US2 (import gate) wraps both.

## Phase 1: Setup

**Purpose**: Create package structure and shared data models

- [x] T001 Create preflight subpackage structure: `agent_transfer/utils/preflight/__init__.py`, `agent_transfer/utils/preflight/scanners/__init__.py`
- [x] T002 Implement manifest data models (TransferManifest, DependencyGraph, all Dep dataclasses) in `agent_transfer/utils/preflight/manifest.py`
- [x] T003 Implement CheckResult and ReadinessReport dataclasses in `agent_transfer/utils/preflight/checker.py` (dataclasses only, no logic yet)
- [x] T004 [P] Implement remediation hint database in `agent_transfer/utils/preflight/remediation.py`

**Checkpoint**: Package importable, all dataclasses instantiable

---

## Phase 2: Foundational — Scanners (Blocking)

**Purpose**: Individual scanners that detect each dependency type. All scanners are independent and can be built in parallel.

**CRITICAL**: Scanners must be complete before collector (Phase 3) or checker (Phase 5) can work.

- [x] T005 [P] Implement MCP scanner — extract server IDs from agent tools, detect install type from config command+args, resolve git URLs in `agent_transfer/utils/preflight/scanners/mcp_scanner.py`
- [x] T006 [P] Implement script scanner — regex-based CLI tool and env var extraction from .sh/.py/.js files in `agent_transfer/utils/preflight/scanners/script_scanner.py`
- [x] T007 [P] Implement binary scanner — ELF magic byte detection, architecture extraction via struct in `agent_transfer/utils/preflight/scanners/binary_scanner.py`
- [x] T008 [P] Implement git scanner — configparser-based remote URL extraction from `.git/config` in `agent_transfer/utils/preflight/scanners/git_scanner.py`
- [x] T009 [P] Implement Docker scanner — detect Dockerfiles, compose files, `docker run` in scripts in `agent_transfer/utils/preflight/scanners/docker_scanner.py`
- [x] T010 [P] Implement .preflight.yml reader — YAML parsing with graceful error handling in `agent_transfer/utils/preflight/scanners/preflight_yml.py`
- [x] T011 [P] Implement scanner tests — unit tests for each scanner with fixture data in `tests/test_preflight_scanners.py`

**Checkpoint**: All 6 scanners pass unit tests independently

---

## Phase 3: User Story 3 — Export with Manifest Generation (Priority: P1)

**Goal**: `agent-transfer export` bundles a `manifest.json` with dependency inventory

**Independent Test**: Export an archive, extract it, verify `manifest.json` contains accurate dependencies

### Implementation

- [x] T012 [US3] Implement inventory collector — compose all scanners, scan agents/skills/hooks/configs in `agent_transfer/utils/preflight/collector.py`
- [x] T013 [US3] Implement `collect_inventory()` public API function in `agent_transfer/utils/preflight/__init__.py`
- [x] T014 [US3] Implement `write_manifest()` and `read_manifest()` JSON serialization in `agent_transfer/utils/preflight/manifest.py`
- [x] T015 [US3] Implement `read_manifest_from_archive()` — safe tarfile extraction of manifest.json in `agent_transfer/utils/preflight/manifest.py`
- [x] T016 [US3] Modify `agent_transfer/utils/transfer.py` export flow to call `collect_inventory()` and bundle `manifest.json` in archive
- [x] T017 [US3] Implement collector tests — verify manifest generation against fixture agents/skills in `tests/test_preflight_collector.py`

**Checkpoint**: `agent-transfer export` produces archives with valid `manifest.json`

---

## Phase 4: User Story 1 — Standalone Preflight Check (Priority: P1)

**Goal**: `agent-transfer preflight <archive>` reads manifest and shows readiness report

**Independent Test**: Run preflight against a mock archive with known deps, verify GREEN/YELLOW/RED output

### Implementation

- [x] T018 [US1] Implement checker logic — check_mcp, check_cli, check_env, check_git_repos, check_binaries, check_skill_trees, check_docker, check_packages, check_sourced_files in `agent_transfer/utils/preflight/checker.py`
- [x] T019 [US1] Implement `run_preflight_checks()` public API that orchestrates all checkers in `agent_transfer/utils/preflight/__init__.py`
- [x] T020 [US1] Implement Rich readiness report display in `agent_transfer/utils/preflight/report.py`
- [x] T021 [US1] Implement `report_to_json()` for --json flag in `agent_transfer/utils/preflight/report.py`
- [x] T022 [US1] Add `preflight` CLI command to `agent_transfer/cli.py` — accepts archive path, --json flag
- [x] T023 [US1] Handle legacy archives (no manifest) — show warning, exit 0 in `agent_transfer/cli.py`
- [x] T024 [US1] Implement checker tests — mock env for GREEN/YELLOW/RED paths in `tests/test_preflight_checker.py`

**Checkpoint**: `agent-transfer preflight archive.tar.gz` shows color-coded report with remediation hints

---

## Phase 5: User Story 2 — Import with Preflight Gate (Priority: P1)

**Goal**: `agent-transfer import` runs preflight before extracting, blocks on RED unless --force

**Independent Test**: Import archives with RED/YELLOW/GREEN deps, verify gate behavior

### Implementation

- [x] T025 [US2] Modify `agent_transfer/cli.py` import command — add --force flag, read manifest before extraction
- [x] T026 [US2] Integrate preflight check into import flow — run checks, display report, prompt on RED in `agent_transfer/cli.py`
- [x] T027 [US2] Handle legacy archives in import — show "no preflight data" warning, proceed in `agent_transfer/cli.py`
- [x] T028 [US2] Implement import gate tests — verify block on RED, warn on YELLOW, pass on GREEN in `tests/test_preflight.py`

**Checkpoint**: `agent-transfer import` gates on preflight results. Legacy archives still import. --force bypasses.

---

## Phase 6: User Story 4 — Self-Audit Mode (Priority: P2)

**Goal**: `agent-transfer preflight --self` audits current machine without an archive

**Independent Test**: Run --self, verify all local agents/skills/hooks scanned and reported

### Implementation

- [x] T029 [US4] Add --self flag to preflight CLI command — scan local env using pathfinder in `agent_transfer/cli.py`
- [x] T030 [US4] Implement self-audit collector path — discover local agents, skills, hooks, configs via pathfinder in `agent_transfer/utils/preflight/collector.py`
- [x] T031 [US4] Support --self --json combination for manifest-format output in `agent_transfer/cli.py`

**Checkpoint**: `agent-transfer preflight --self` produces full dependency inventory of local machine

---

## Phase 7: User Story 5 — Claude Code Skill Integration (Priority: P3)

**Goal**: `/preflight` skill in Claude Code for interactive readiness checking

**Independent Test**: Invoke `/preflight`, verify conversational guidance output

### Implementation

- [ ] T032 [US5] Create `/preflight` skill markdown file at `~/.claude/skills/preflight/SKILL.md` (or document how to create it)
- [ ] T033 [US5] Skill script that invokes `agent-transfer preflight` and formats output for agentic conversation

**Checkpoint**: `/preflight` skill invocable in Claude Code sessions

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Quality, security, and robustness

- [ ] T034 [P] Run Ruff linter on all new preflight modules and fix issues
- [ ] T035 [P] Run Ruff linter on modified cli.py and transfer.py and fix issues
- [ ] T036 [P] Adversarial bug hunting — targeted scan of manifest serialization and env var handling (R8 compliance)
- [ ] T037 [P] Adversarial bug hunting — general logic scan across all preflight modules
- [ ] T038 Ensure env var values are NEVER logged or displayed — security audit of all report paths
- [ ] T039 Run full existing test suite to verify backward compatibility (R5)
- [ ] T040 Run quickstart.md test scenarios end-to-end
- [ ] T041 Git checkpoint — commit all changes

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Scanners)**: Depends on Phase 1 (needs dataclasses)
- **Phase 3 (US3 Export)**: Depends on Phase 2 (needs scanners)
- **Phase 4 (US1 Preflight)**: Depends on Phase 3 (needs manifest read) — could also start after Phase 2 if using mock manifests
- **Phase 5 (US2 Import Gate)**: Depends on Phase 4 (needs checker + report)
- **Phase 6 (US4 Self-Audit)**: Depends on Phase 4 (needs checker + report)
- **Phase 7 (US5 Skill)**: Depends on Phase 4 (needs working CLI command)
- **Phase 8 (Polish)**: Depends on all above

### Parallel Opportunities

```
Phase 1: T001 → T002/T003 sequential, T004 [P] independent
Phase 2: T005 [P] + T006 [P] + T007 [P] + T008 [P] + T009 [P] + T010 [P] (ALL parallel)
         T011 [P] can start as scanners complete
Phase 3: T012 → T013 → T014/T015 [P] → T016 → T017
Phase 4: T018 → T019 → T020/T021 [P] → T022/T023 [P] → T024
Phase 5: T025 → T026 → T027 → T028
Phase 6: T029/T030 [P] → T031
Phase 7: T032/T033 [P]
Phase 8: T034 [P] + T035 [P] + T036 [P] + T037 [P], then T038 → T039 → T040 → T041
```

---

## Implementation Strategy

### MVP (US3 + US1 only — Phases 1-4)

1. Phase 1: Setup (4 tasks)
2. Phase 2: Scanners (7 tasks) — all parallel
3. Phase 3: Export + manifest (6 tasks)
4. Phase 4: Preflight command (7 tasks)
5. **STOP**: You now have `agent-transfer export` producing manifests and `agent-transfer preflight` checking them.

### Full Delivery

6. Phase 5: Import gate (4 tasks)
7. Phase 6: Self-audit (3 tasks)
8. Phase 7: Skill (2 tasks)
9. Phase 8: Polish (8 tasks)

**Total**: 41 tasks across 8 phases

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to user story for traceability
- All scanners (Phase 2) are independent and parallelizable
- Phase 4 can overlap Phase 3 if mock manifests used for testing
- Commit after each phase checkpoint
