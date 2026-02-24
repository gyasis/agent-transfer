# Tasks: 001 — Platform-Agnostic Agent Transfer

**Spec:** `spec.md`
**Plan:** `plan.md`
**Constitution:** `.specify/memory/constitution.md` (12 rules)

---

## Phase 1: Bug Fixes + Security (US-6 + Foundation)

**Goal:** Fix all pre-existing bugs (B1-B7), harden security, enforce hygiene gates. Zero regressions.

- [ ] T001 [US6] Create `agent_transfer/utils/tar_safety.py` — safe extraction rejecting path traversal, symlinks, absolute paths (R7)
- [ ] T002 [US6] Replace `tar.extractall()` in `agent_transfer/transfer.py:331` with safe extraction (B1)
- [ ] T003 [P] [US6] Replace `tar.extractall()` in `agent_transfer/transfer.py:647` with safe extraction (B1)
- [ ] T004 [P] [US6] Replace `tar.extractall()` in `agent_transfer/import_analyzer.py:52` with safe extraction (B1)
- [ ] T005 [P] [US6] Replace `tar.extractall()` in `agent_transfer/utils/skill_validator.py:654` with safe extraction (B1)
- [ ] T006 [US6] Grep codebase for remaining `tar.extractall()` / `tarfile.open()` — verify T002-T005 cover all sites (R7 audit)
- [ ] T007 Fix `ImportPreview` missing `skill_comparisons=[]` default in `agent_transfer/import_analyzer.py:111` (B2)
- [ ] T008 [P] Sanitize markdown output in `agent_transfer/templates/agent_view.html:442` — fix XSS (B3)
- [ ] T009 [P] Sanitize markdown output in `agent_transfer/templates/skill_view.html:561` — fix XSS (B3)
- [ ] T010 [P] Sanitize markdown in `agent_transfer/utils/web_server.py` render pipeline — fix XSS (B3)
- [ ] T011 Fix KEEP mode return value in `agent_transfer/conflict_resolver.py:428` — return `None` not truthy path (B4)
- [ ] T012 Fix `pyproject.toml` — add `agent_transfer.utils` to packages + `templates/*.html` to package-data (B5)
- [ ] T013 Sync version `agent_transfer/__init__.py` to `"1.1.0"` to match `pyproject.toml` (B6)
- [ ] T014 Replace hand-rolled TOML parser in `agent_transfer/utils/skill_validator.py:155-194` with `tomllib`/`tomli` (B7)
- [ ] T015 Audit codebase for hardcoded absolute paths — replace with `Path.home()` / platform config (R6)
- [ ] T016 Add filename lint gate — reject `_v2`, `_new`, `_old` suffixes in CI/pre-commit (R10)
- [ ] T017 Run ruff lint + format on full codebase
- [ ] T018 Run full test suite — verify zero regressions (R11)
- [ ] T019 Adversarial bug hunt — targeted report (R12)
- [ ] T020 Adversarial bug hunt — general logic scan (R12)
- [ ] T021 Git checkpoint `v1.2.0-security`

## Phase 2: Platform Abstraction Layer (US-3 Foundation)

**Goal:** Create plugin architecture for platform detection and registration. Wrap existing Claude Code code. All config dirs use `Path.home()` (R6).

- [ ] T022 Create `agent_transfer/platforms/__init__.py` package
- [ ] T023 Create `agent_transfer/platforms/base.py` — PlatformConfig dataclass, BasePlatform ABC (`detect()`, `find_agents()`, `find_skills()`), PlatformRegistry (`register()`, `get()`, `detect_all()`) (R9)
- [ ] T024 Create `agent_transfer/platforms/claude_code.py` — wrap existing `discovery.py`, `skill_discovery.py`, `parser.py` (R4)
- [ ] T025 [P] Create `agent_transfer/platforms/codex.py` — stub: detect + PlatformConfig only
- [ ] T026 [P] Create `agent_transfer/platforms/gemini_cli.py` — stub: detect + PlatformConfig only
- [ ] T027 [P] Create `agent_transfer/platforms/goose.py` — stub: detect + PlatformConfig only
- [ ] T028 [P] Create `agent_transfer/platforms/opencode.py` — stub: detect + PlatformConfig only
- [ ] T029 [US3] Add `agent-transfer platforms` CLI command in `agent_transfer/cli.py` — Rich table: name, slug, detected Y/N, config dir, MCP support (R5: addition only)
- [ ] T030 Register platforms via entry_points in `pyproject.toml` (R9)
- [ ] T031 Verify all platform config dirs use `Path.home()`, zero hardcoded paths (R6 audit)
- [ ] T032 Tests — platform detection, PlatformConfig correctness, PlatformRegistry in `tests/test_platforms.py` (R11)
- [ ] T033 Adversarial scan (R12)
- [ ] T034 Git checkpoint

## Phase 3: IR Schema + Claude Code Ingestor/Emitter (US-4, US-5)

**Goal:** Define AI Intent Manifest (AIM) IR schema with `.aim.yaml` extension. Build Claude Code ingestor/emitter. Prove lossless round-trip (R1). No secrets in IR output (R8).

- [ ] T035 Create `agent_transfer/ir/__init__.py` package
- [ ] T036 Create `agent_transfer/ir/manifest.py` — AIIntentManifest dataclass + `to_yaml()`/`from_yaml()` serialization, `.aim.yaml` extension (R2)
- [ ] T037 [P] Create `agent_transfer/ir/capability.py` — canonical tool mapping registry for all 5 platforms (`map_tool(platform, tool_name) -> canonical_name`)
- [ ] T038 [P] Create `agent_transfer/ir/validators.py` — IR schema validation: required fields, type checks, version compat, no secrets (R8)
- [ ] T039 Create `agent_transfer/ingestors/__init__.py` package
- [ ] T040 Create `agent_transfer/ingestors/base.py` — BaseIngestor ABC: `ingest_agent(path) -> AIIntentManifest`, `ingest_skill(path) -> AIIntentManifest`
- [ ] T041 [US4] Create `agent_transfer/ingestors/claude_code.py` — wraps `parser.py`/`skill_parser.py`, produces AIIntentManifest with shadow data (R4)
- [ ] T042 Create `agent_transfer/emitters/__init__.py` package
- [ ] T043 Create `agent_transfer/emitters/base.py` — BaseEmitter ABC: `emit_agent(manifest, target_dir) -> Path`, `emit_skill(manifest, target_dir) -> Path`
- [ ] T044 [US4] Create `agent_transfer/emitters/claude_code.py` — reconstructs `.md` from IR using shadow data `original_content` for lossless output (R1)
- [ ] T045 Create test corpus in `tests/fixtures/canonical/` — 5+ agent fixtures (multi-line prompts, embedded YAML, unicode, code blocks) for SC-2 validation
- [ ] T046 [US4] CRITICAL TEST: Claude Code -> Ingestor -> IR -> Emitter -> Claude Code = byte-identical in `tests/test_lossless_roundtrip.py` (R1, R11)
- [ ] T047 [US5] Add `agent-transfer convert` CLI command in `agent_transfer/cli.py` — `convert <name> --from <platform> --to <platform>`, Claude Code <-> AIM only at this point (R5)
- [ ] T048 Tests for `ir/validators.py`, `ingestors/base.py`, `emitters/base.py` in `tests/test_ir.py` (R11)
- [ ] T049 Update `pyproject.toml` with new packages: `ir`, `ingestors`, `emitters`
- [ ] T050 Adversarial scan (R12)
- [ ] T051 Git checkpoint

## Phase 4: Compatibility Matrix + Codex Support (US-1, US-2, US-3)

**Goal:** Build compatibility reporting. Add Codex CLI as first cross-platform target. Wire compat pre-flight into `convert` command. Acceptance: Rich table per feature / transfer quality / notes.

- [ ] T052 Create `agent_transfer/compat/__init__.py` package
- [ ] T053 Create `agent_transfer/compat/matrix.py` — feature compatibility data for all platform pairs, classifications: `clean_transfer`, `best_effort_shim`, `cannot_transfer`
- [ ] T054 [P] Create `agent_transfer/compat/reporter.py` — Rich table display with per-feature breakdown and color coding
- [ ] T055 [P] Create `agent_transfer/compat/shims.py` — instructional shim generation for non-transferable hooks, inject into system prompt
- [ ] T056 [US3] Add `agent-transfer compat` CLI command in `agent_transfer/cli.py` — `compat --from <platform> --to <platform>`, Rich table output (R5)
- [ ] T057 [US1] Wire compat pre-flight into `convert` command — show compat report before cross-platform conversion
- [ ] T058 [US1] [US2] Create `agent_transfer/ingestors/codex.py` + `agent_transfer/emitters/codex.py` — hook import policy: incoming hooks become instructional shims (Resolved Q4)
- [ ] T059 [US1] [US2] Test: Claude Code <-> IR <-> Codex round-trip in `tests/test_codex_roundtrip.py` + `compat/` module tests in `tests/test_compat.py` (R11)
- [ ] T060 Adversarial scan — targeted + general (R12)
- [ ] T061 Git checkpoint

## Phase 5: Goose + Gemini CLI Support (US-1, US-2)

**Goal:** Add Goose (YAML recipes) and Gemini CLI (JSON settings) support. Hook import = instructional shims only (Resolved Q4).

- [ ] T062 [US1] [US2] Create `agent_transfer/ingestors/goose.py` + `agent_transfer/emitters/goose.py` — recipe steps map to/from system prompt + shims
- [ ] T063 [P] [US1] [US2] Create `agent_transfer/ingestors/gemini_cli.py` + `agent_transfer/emitters/gemini_cli.py` — JSON settings parsing + generation
- [ ] T064 [US1] [US2] Test cross-platform conversions in `tests/test_cross_platform.py`: Claude <-> Goose, Claude <-> Gemini, Goose <-> Gemini (R11)
- [ ] T065 Update `agent_transfer/compat/matrix.py` with real test results from Goose + Gemini conversions
- [ ] T066 Adversarial scan (R12)
- [ ] T067 Git checkpoint

## Phase 6: OpenCode + Skills + Final Validation (US-1, US-5)

**Goal:** Add OpenCode (JS/TS plugin stubs). Build Claude Code automation skills. Verify all 20 compat pairs. Validate IR portability end-to-end.

- [ ] T068 [US1] [US2] Create `agent_transfer/ingestors/opencode.py` + `agent_transfer/emitters/opencode.py`
- [ ] T069 Update `agent_transfer/compat/matrix.py` with OpenCode's 4 platform pairs — verify all 20 pairs present (SC-3)
- [ ] T070 [US5] IR portability test in `tests/test_ir_portability.py`: load pre-generated `.aim.yaml` → emit to each of the 4 non-AIM target platforms (US-5 end-to-end validation)
- [ ] T071 Create Claude Code skill `/transfer-agent` — trigger: "transfer agent to [platform]"; input: agent name + target; output: converted files + compat report
- [ ] T072 Create Claude Code skill `/analyze-platform` — trigger: "analyze platform compatibility"; input: optional --from/--to; output: compat matrix table
- [ ] T073 Register entry_points for all 5 platforms in `pyproject.toml` (R9)
- [ ] T074 Tests for OpenCode ingestor/emitter + skill behavior in `tests/test_opencode.py` + `tests/test_skills.py` (R11)
- [ ] T075 Adversarial scan — full codebase (R12)
- [ ] T076 Git checkpoint `v2.0.0`

---

## Dependencies

```
Phase 1 (Bug Fixes)        → no dependencies (foundation)
Phase 2 (Platforms)         → Phase 1 complete
Phase 3 (IR + CC I/E)      → Phase 2 complete
Phase 4 (Compat + Codex)   → Phase 3 complete
Phase 5 (Goose + Gemini)   → Phase 3 complete (parallel with Phase 4)
Phase 6 (OpenCode + Skills) → Phase 4 + Phase 5 complete
```

**Parallel Opportunities:**
- Phase 4 and Phase 5 can run in parallel (both depend on Phase 3, not each other)
- Within Phase 1: T002-T005 (tar replacements) are parallel after T001
- Within Phase 1: T008-T010 (XSS fixes) are parallel
- Within Phase 2: T025-T028 (stub platforms) are parallel
- Within Phase 3: T037-T038 (capability + validators) are parallel
- Within Phase 4: T054-T055 (reporter + shims) are parallel
- Within Phase 5: T062-T063 (Goose + Gemini) are parallel

---

## Coverage Matrix

| Requirement | Tasks | Status |
|-------------|-------|--------|
| R1 (Lossless same-platform) | T044, T046 | Covered |
| R2 (IR cross-platform only) | T036, T047 | Covered |
| R3 (Linux + WSL only) | All platform configs | Implicit |
| R4 (Wrap, don't rewrite) | T024, T041 | Covered |
| R5 (Backward compat) | T018, T029, T047, T056 | Covered |
| R6 (No hardcoded paths) | T015, T031 | Covered |
| R7 (Safe archive) | T001-T006 | Covered |
| R8 (No secret transfer) | T038 | Covered |
| R9 (Plugin architecture) | T023, T030, T073 | Covered |
| R10 (File naming discipline) | T016 | Covered |
| R11 (Test coverage) | T018, T032, T046, T048, T059, T064, T074 | Covered |
| R12 (Adversarial scan) | T019-T020, T033, T050, T060, T066, T075 | All 6 sprints |
| US-1 (Cross-platform convert) | T057, T058, T062, T063, T068 | Covered |
| US-2 (Import from other) | T058, T062, T063, T068 | Covered |
| US-3 (Platform discovery) | T029, T056 | Covered |
| US-4 (Lossless same-platform) | T041, T044, T046 | Covered |
| US-5 (Bulk IR export) | T047, T070 | Covered |
| US-6 (Security fix) | T001-T006 | Covered |
| SC-3 (20 platform pairs) | T053, T065, T069 | Covered |
| B1-B7 (Known bugs) | T001-T014 | All covered |

---

## Metrics

- **Total tasks:** 76
- **Phase 1 (Bugs+Security):** 21 tasks
- **Phase 2 (Platforms):** 13 tasks
- **Phase 3 (IR+I/E):** 17 tasks
- **Phase 4 (Compat+Codex):** 10 tasks
- **Phase 5 (Goose+Gemini):** 6 tasks
- **Phase 6 (OpenCode+Skills):** 9 tasks
- **Parallel opportunities:** 7 groups identified
- **Constitution coverage:** 12/12 rules (100%)
- **User story coverage:** 6/6 stories (100%)
- **Success criteria coverage:** 6/6 criteria (100%)
- **Bug coverage:** 7/7 bugs (100%)

---

## Implementation Strategy

**MVP (Phase 1-3):** Bug fixes + platform abstraction + Claude Code lossless round-trip. Validates core architecture before adding cross-platform targets.

**Incremental delivery:**
- After Phase 1: Existing tool is more secure and stable
- After Phase 3: `convert --to aim` works for Claude Code
- After Phase 4: First real cross-platform conversion (Codex)
- After Phase 5: 3 cross-platform targets (Codex, Goose, Gemini)
- After Phase 6: Full v2.0.0 with all 5 platforms + skills
