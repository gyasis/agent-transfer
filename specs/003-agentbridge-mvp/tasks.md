---
description: "Tasks for AgentBridge MVP — capability-level Claude→Claude transfer with agent-driven ingestion"
---

# Tasks: AgentBridge MVP — Capability-Level Claude→Claude Transfer

**Input**: Design documents from `specs/003-agentbridge-mvp/`
**Prerequisites**: plan.md (required), spec.md (required for user stories). research.md / data-model.md / contracts/ to be produced as part of Foundational phase.
**Source PRD**: `~/dev/prd/scratch/agentbridge_capability_transfer_2026-05-03.md`

**Tests**: INCLUDED — the spec defines testable success criteria (SC-001 through SC-009) and the project constitution requires test coverage (R11). Tests for each user story MUST be written before the implementation tasks for that story (they must FAIL first).

**Organization**: Tasks are grouped by user story. **User Story 1 is the MVP ship gate** — completing Phases 1, 2, and 3 ships the MVP. User Story 2 is post-ship validation and is intentionally deferrable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: `US1` (cascade-memory, P1, ship gate), `US2` (prd-planning, P2, post-ship), or unlabeled (foundational/setup/polish)

## Path Conventions

Single-project Python CLI per plan.md. Paths are relative to repo root (`~/dev/agent-transfer/`). New code lives under `agent_transfer/bridge/`. New shipped skills' canonical sources live at `agent_transfer/templates/skills/agentbridge-{compose,ingest}/SKILL.md`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffold the new `bridge/` subpackage and the new shipped skills.

- [x] **T001** Create `agent_transfer/bridge/__init__.py` and empty stubs for `models.py`, `compose.py`, `briefing.py`, `selection_matrix.py`, `preview.py`, `rollback.py`, `ingest.py`, `smoke_test.py`, `secrets.py` per plan.md "Source Code" tree.
- [x] **T002** [P] Create `agent_transfer/templates/skills/agentbridge-compose/SKILL.md` skeleton (frontmatter + 1-line description; full content lands in T032).
- [x] **T003** [P] Create `agent_transfer/templates/skills/agentbridge-ingest/SKILL.md` skeleton (frontmatter + 1-line description; full content lands in T040).
- [x] **T004** [P] Add Pydantic to project dependencies if not already transitively present. Verify import in fresh `uv` env.
- [x] **T005** [P] Add `ab` console-script entry point in `pyproject.toml` alongside existing `agent-transfer` entry point. Both must work post-install (R5).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data model, security primitives, and design artifacts that ALL user stories depend on. Includes the two parent-PRD carry-overs (FR-010 secret regex, FR-015 path-rewrite) so that any later bundle/import flow inherits them.

**CRITICAL**: No user-story work can begin until this phase completes.

### Phase 0/1 design artifacts

- [ ] **T006** Write `specs/003-agentbridge-mvp/research.md` covering the 6 questions in plan.md Phase 0 (capability-graph heuristics, briefing format, risk-tag classification, conflict-policy defaults, rollback snapshot scope, smoke-test prompts).
- [ ] **T007** Write `specs/003-agentbridge-mvp/data-model.md` defining `ManifestModel`, `Capability`, `AssetEntry`, `RiskTag`, `ConflictPolicy`, `BriefingSection`, `Confirmation` (per plan.md Phase 1).
- [x] **T008** [P] Write `specs/003-agentbridge-mvp/contracts/manifest.schema.json` JSON Schema for `ManifestModel`.
- [x] **T009** [P] Write `specs/003-agentbridge-mvp/contracts/briefing.template.md` Markdown template for "Dear Receiving Claude" with 7 section slots (Identity, Capability Description, Inventory, Build Instructions, Ingest Instructions, Verification, Rollback).
- [x] **T010** [P] Write `specs/003-agentbridge-mvp/quickstart.md` user-facing walkthrough.

### Foundational implementation

- [x] **T011** Implement `agent_transfer/bridge/models.py`: Pydantic `ManifestModel`, `Capability`, `AssetEntry { path, dest_path, risk, conflict, sha256, mode_bits }`, `RiskTag` (Literal Green/Yellow/Red), `ConflictPolicy` (Literal skip/merge/overwrite/ask), `BriefingSection`, `Confirmation { asset_path, risk, decided_at, user_choice }`. Re-export from `agent_transfer/models.py`.
- [x] **T012** [US1][US2] Implement `agent_transfer/bridge/secrets.py`: merged regex (Bearer / `sk-` / `ghp_` / `xox*` / generic). Single `scan(text) -> list[SecretFinding]` function used pre-seal AND post-seal. (FR-010, SC-006, parent-PRD M1.3)
- [ ] **T013** [US1][US2] Extend `agent_transfer/utils/transfer.py` import path to perform `~/.claude.json` mcpServers path-rewrite using `_classification.config_after_install`. (FR-015, parent-PRD M1.2). Existing same-platform round-trip MUST still pass (R1).
- [ ] **T014** [P] Extend `agent_transfer/utils/mcp_classifier.py` to emit a `risk_tag` field (Green/Yellow/Red) per entry. Default rule: any server with auth → Yellow; any state-writing hook reference → Red. (FR-008)
- [ ] **T015** [P] Extend `agent_transfer/utils/script_discovery.py` to emit `risk_tag` per discovered script. Heuristic: read-only (grep / find / cat / curl GET) = Yellow; state-writing (write / push / delete / chmod / install) = Red. (FR-008)
- [ ] **T016** [P] Extend `agent_transfer/utils/config_manager.py` to additionally emit a capability-shaped output (a list of `AssetEntry`) alongside its current output. Existing callers MUST keep working (R5).

### Foundational tests

- [ ] **T017** [P] Contract test `tests/contract/test_manifest_schema.py`: round-trip `ManifestModel` ↔ `manifest.schema.json`.
- [ ] **T018** [P] Contract test `tests/contract/test_briefing_sections.py`: render briefing → assert all 7 required sections present, each non-empty.
- [ ] **T019** [P] Unit test `tests/unit/test_secret_redaction.py`: positive + negative cases for Bearer / sk- / ghp_ / xox* / generic, including the 2 real Bitbucket app-password patterns the existing classifier caught.
- [ ] **T020** [P] Unit test `tests/unit/test_risk_tagging.py`: classify a known fixture set of skills, hooks, rules, bin scripts; assert exact Green/Yellow/Red tags per asset type rules from research.md.
- [ ] **T021** [P] Integration test `tests/integration/test_path_rewrite_mcp.py`: import a bundle whose `~/.claude.json` references `/home/source-user/...` paths into a sandbox HOME at `/tmp/...`; assert all mcpServers paths now point inside the sandbox.

**Checkpoint**: Foundation ready. Existing `agent-transfer` round-trip tests still pass. T012, T013, T021 verify the carry-overs. User-story work can begin.

---

## Phase 3: User Story 1 — Cascade-memory capability round-trip (Priority: P1) — MVP SHIP GATE

**Goal**: Story 1 from spec.md. User says "Bundle my cascade-memory functionality so I can install it on another machine"; round-trips on a fresh sandbox HOME via `ab compose` → selection matrix → `ab export` → bundle → destination Claude invokes `agentbridge-ingest` skill → smoke test passes → rollback works.

**Independent Test**: `pytest tests/integration/test_capability_roundtrip.py -k cascade_memory` PLUS the manual end-to-end sandbox walkthrough on `/tmp/ab-mvp-sandbox-$(date +%s)`.

### Tests for User Story 1 (write FIRST, must FAIL before implementation)

- [ ] **T022** [P] [US1] Integration test `tests/integration/test_capability_roundtrip.py::test_cascade_memory_roundtrip` — SC-001 ship gate. Sets up fresh sandbox HOME, runs full pipeline, asserts: bundle has 14 expected assets, briefing has all 7 sections, sandbox `session-search foo` runs cleanly returning "no matches", all 7 dependent skills present, both hooks fire on triggering events, all 5 rule files inject correctly.
- [ ] **T023** [P] [US1] Integration test `tests/integration/test_rollback_diff.py::test_cascade_memory_rollback` — SC-002. File-tree diff before vs after install→rollback shows zero leftover artifacts.
- [ ] **T024** [P] [US1] Unit test `tests/unit/test_compose_graph.py::test_cascade_memory_graph` — given `~/.claude/` fixture mirroring source machine, `compose("cascade-memory")` returns the expected 14-asset graph with correct CORE/COMPANIONS/CONTEXT tier assignments.
- [ ] **T025** [P] [US1] Unit test `tests/unit/test_selection_matrix.py` — 3-tier matrix renders correctly; user trim of a COMPANIONS asset removes it from the export set; trim of a CORE asset is rejected with clear error.

### Implementation for User Story 1

#### Source-side composition

- [ ] **T026** [US1] Implement `agent_transfer/bridge/compose.py::compose(capability_name) -> Capability`: deterministic dependency-graph walk per research.md heuristics. Reads `~/.claude/skills/`, `~/.claude/hooks/`, `~/.claude/rules/`, `~/bin/`, follows cross-references (skill→bin, hook→rule, rule→skill). (FR-003, FR-004) Depends on T011, T015, T016.
- [ ] **T027** [US1] Implement `agent_transfer/bridge/selection_matrix.py`: Rich-based 3-tier UI (CORE always-included, COMPANIONS opt-out, CONTEXT opt-in). Returns the trimmed `Capability` after user confirmation. (FR-005) Depends on T011.
- [ ] **T028** [US1] Implement `agent_transfer/bridge/briefing.py::render(manifest) -> str`: emits BRIEFING.md from `contracts/briefing.template.md` with all 7 sections populated from the manifest. (FR-007) Depends on T011, T009.
- [ ] **T029** [US1] Implement `agent_transfer/bridge/preview.py`: Briefing Preview UI (Rich) — per-asset preview with risk tags; enforces `y/n` on every Yellow and Red asset; refuses to seal on declined Red. Writes `confirmations.log` to bundle root. (FR-009, FR-018, SC-007) Depends on T027.
- [ ] **T030** [US1] Implement `agent_transfer/bridge/rollback.py::snapshot(targets) -> (rollback_tar, rollback_sh)`: snapshots union of (every dest path the bundle will touch, `~/.claude.json`, `~/.claude/settings.json`). All-or-nothing tarball + shell script. (FR-016) Depends on T011.
- [ ] **T031** [US1] Wire `ab compose --capability <name>` Click command in `agent_transfer/cli.py` invoking T026 → T027 → T028 → preview → existing `mcp_source_bundler` to seal. (FR-001) Depends on T026, T027, T028, T029, T030. Pre-seal secret scan (T012). Post-seal scan asserts SC-006.
- [ ] **T032** [US1] Author `agent_transfer/templates/skills/agentbridge-compose/SKILL.md` content: trigger phrases ("bundle my X functionality", "I want to install X on another machine"), behavior (invoke `ab compose`), expected outputs, conflict-handling guidance for the source-side agent. (FR-002) Depends on T031.

#### Destination-side ingestion

- [ ] **T033** [US1] Implement `agent_transfer/bridge/ingest.py::ingest(bundle_path)`: reads BRIEFING.md, validates manifest, invokes selection_matrix again (for destination-side trim), prompts on every Yellow/Red, walks inventory, applies per-asset conflict policy (skip/merge/overwrite/ask), preserves mode bits, performs settings.json + ~/.claude.json idempotent merge. (FR-012, FR-013, FR-014, FR-011) Depends on T011, T013, T027, T030.
- [ ] **T034** [US1] Implement `agent_transfer/bridge/smoke_test.py::run(manifest)`: post-install self-interrogation — checks each declared asset is present at its declared path with declared mode, runs `session-search foo` on empty corpus, validates "who are you" against manifest. Flags drift. (FR-017)
- [ ] **T035** [US1] Wire `ab ingest <bundle>` Click command in `agent_transfer/cli.py` invoking rollback snapshot → T033 → T034. Failures trigger `rollback.sh` invocation hint. (FR-019 — additive only; existing 9 commands untouched).
- [ ] **T036** [US1] Author `agent_transfer/templates/skills/agentbridge-ingest/SKILL.md` content: trigger ("Install this AgentBridge bundle"), behavior (invoke `ab ingest`), conflict-policy guidance, smoke-test interpretation. (FR-012) Depends on T035.
- [ ] **T037** [US1] Add settings.json idempotent-merge integration test `tests/integration/test_settings_merge_idempotent.py::test_re_running_ingest_does_not_duplicate_hooks` — FR-014. Assert running ingestion twice produces exactly one set of hook entries.

**Checkpoint**: User Story 1 fully functional. Run T022–T025 + T037; all green. Run the manual sandbox walkthrough end-to-end. **MVP IS SHIPPABLE AT THIS POINT.** Commit.

---

## Phase 4: User Story 2 — prd-planning capability round-trip (Priority: P2) — POST-SHIP VALIDATION

**Goal**: Story 2 from spec.md. Validates the architecture extends to settings.json-wired hooks and Red-tier assets. **Not a ship blocker.**

**Independent Test**: `pytest tests/integration/test_prd_capability_roundtrip.py` after MVP shipped.

### Tests for User Story 2 (write FIRST)

- [ ] **T038** [P] [US2] Integration test `tests/integration/test_prd_capability_roundtrip.py` — SC-009. Bundle the prd capability, install on sandbox, assert: `prd new test_descriptor` creates stub at right location; `prd-guard` blocks writes outside `scratch/`; `prd-guard` allows writes when skill-internal lock is held; settings.json gained the prd-guard hook entries non-destructively.

### Implementation for User Story 2

- [ ] **T039** [US2] No new code required if Phase 3 is correct — Phase 3's general ingestion handles `prd`'s asset mix (binary + skill + hook + settings.json fragment + companion skills + rule). Run T038 to confirm. If gaps found, file targeted fixes here.
- [ ] **T040** [US2] If T039 surfaces issues, implement targeted fixes (most likely: settings.json fragment merge edge cases, Red-tier hook confirmation flow). All fixes MUST keep T022 (US1 ship gate) green.

**Checkpoint**: User Story 2 validated. Architecture extension to Red-tier hooks + settings.json wiring is proven. Commit.

---

## Phase N: Polish & Cross-Cutting Concerns

**Purpose**: Rename, README, parent-PRD bookkeeping, adversarial scan, performance verification. Maps to PRD M4 (Day 7) + M5.2 (Day 8 buffer) + R12.

- [ ] **T041** Rename: update `pyproject.toml` package name and the README title from `agent-transfer` to `AgentBridge`. Keep both `agent-transfer` and `ab` console-scripts working (R5). NO file renames (R10). (FR-021, parent-PRD M4.1)
- [ ] **T042** [P] Rewrite `README.md` around "capability-level transfer with agent-driven composition and ingestion." Explicitly state Mode A only; cross-harness is post-MVP. (parent-PRD M4.2)
- [ ] **T043** [P] Update parent PRD `~/dev/prd/scratch/agent_transfer_full_config_capture_2026-05-02.md`: mark generated `setup.sh` init flow as superseded; mark HTTP-transport import as deferred; mark FR-010 (tighter secret regex) and FR-015 (path-rewrite) as landed in 003-agentbridge-mvp. (parent-PRD M4.3)
- [ ] **T044** Run adversarial bug-hunter agents (constitution R12) — spawn one targeted (rollback path / secret-leak / settings.json merge / mode-bit preservation) and one general scan. Fix all CRITICAL and HIGH findings before merge.
- [ ] **T045** Performance verification: SC-004 (source-side bundle for cascade-memory < 60s) and SC-005 (destination-side ingestion excluding pause time < 30s). Time the sandbox walkthrough; record numbers in `quickstart.md`.
- [x] **T046** Re-link `tasks.md` symlink at repo root to `specs/003-agentbridge-mvp/tasks.md` (already done in spec session 2026-05-03; verified `readlink tasks.md` → `specs/003-agentbridge-mvp/tasks.md`).
- [ ] **T047** Run `quickstart.md` validation end-to-end one final time on a clean sandbox.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies — start immediately.
- **Phase 2 Foundational**: Depends on Phase 1. **Blocks all user stories.** Carry-overs (T012, T013) MUST land here, not later.
- **Phase 3 (US1, MVP)**: Depends on Phase 2 complete. **This is the ship gate.**
- **Phase 4 (US2, post-ship)**: Depends on Phase 3 complete. Deferrable past MVP commit.
- **Phase N Polish**: Mostly depends on Phase 3 (T041–T045 require working MVP). T043 (parent-PRD update) can land any time after Phase 2.

### User-Story Dependencies

- **US1 (P1, MVP)**: Self-contained after Foundational. No dependency on US2.
- **US2 (P2, post-ship)**: Depends on US1 implementation (reuses Phase 3 code).

### Within User Story 1

- T022–T025 (tests) MUST be written and FAIL before T026–T037 (implementation).
- T026 (compose) before T027 (matrix) before T028 (briefing) before T029 (preview) before T031 (CLI wire).
- T030 (rollback) parallel with T026–T029.
- T033 (ingest) before T034 (smoke test) before T035 (CLI wire) before T036 (skill content).
- T032 and T036 (skill markdown content) require their respective CLIs working.

### Parallel Opportunities

- T002, T003, T004, T005 in Phase 1 are all `[P]`.
- T008, T009, T010, T014, T015, T016 in Phase 2 are `[P]`.
- T017–T021 (Foundational tests) are all `[P]`.
- T022–T025 (US1 tests) are all `[P]` — write them in one parallel batch.
- T038 (US2 test) is `[P]` — can run anytime after Phase 3 ships.
- T042, T043 in Polish are `[P]`.

---

## Parallel Example: User Story 1 tests

```bash
# Write all 4 US1 tests in parallel, ensure they FAIL, then start implementation:
Task: "Integration test for cascade-memory roundtrip in tests/integration/test_capability_roundtrip.py"
Task: "Integration test for cascade-memory rollback in tests/integration/test_rollback_diff.py"
Task: "Unit test for compose graph in tests/unit/test_compose_graph.py"
Task: "Unit test for selection matrix in tests/unit/test_selection_matrix.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 only — SHIP GATE)

1. Phase 1 Setup (T001–T005).
2. Phase 2 Foundational (T006–T021) — completes the carry-overs and the data model.
3. Phase 3 User Story 1 (T022–T037) — write tests first, then implement.
4. **STOP and VALIDATE**: Run T022–T025 + T037; run the manual sandbox walkthrough.
5. If green: **MVP SHIPS.** Commit and tag.

### Incremental Delivery (post-ship)

6. Phase 4 User Story 2 (T038–T040) — confirm architecture extends.
7. Phase N Polish (T041–T047) — rename, README, adversarial scan, parent-PRD bookkeeping, perf verification, symlink fix, final quickstart validation.

### Parallel-Team Strategy

A second developer can take T038 (US2 test + fixes) and Phase N polish (T041–T043) while the first wraps Phase 3. T044 (adversarial scan) and T045 (perf verification) MUST run after both stories are complete.

---

## Notes

- `[P]` = different files, no dependencies.
- `[US1]` / `[US2]` traceability labels.
- US1 is independently shippable; US2 is independently testable on top of US1.
- Tests must FAIL before implementation begins.
- Constitution R1 (lossless same-platform), R4 (wrap don't rewrite), R5 (backward compat), R7 (safe extract), R8 (no secrets), R10 (no file renames), R11 (test coverage), R12 (adversarial scan) are non-negotiable. Plan.md Constitution Check confirms PASS.
- PRD-mapped phase calendar: M1 = Phase 2 carry-overs (Day 1); M2.1–M2.6 = Phase 2 + Phase 3 (Days 2–5); M3 = Phase 3 safety + UX (Day 6, parallel with implementation); M4 = Phase N rename/polish (Day 7); M5 = T022 + T038 + T044–T047 (Day 8 verification + buffer).
