# Implementation Plan: 001 — Platform-Agnostic Agent Transfer

**Spec:** `spec.md`
**Constitution:** `.specify/memory/constitution.md`
**Date:** 2026-02-24

---

## Sprint Overview

> **Note:** Numbered items in each sprint group related sub-tasks (e.g., Sprint 1 item 2 covers T002-T005). See `tasks.md` for atomic task counts.

| Sprint | Focus | Tasks | Dependencies |
|--------|-------|-------|-------------|
| 1 | Bug Fixes + Security + Hygiene | 21 | None (foundation) |
| 2 | Platform Abstraction | 13 | Sprint 1 |
| 3 | IR Schema + Claude Code Ingestor/Emitter | 17 | Sprint 2 |
| 4 | Compatibility Matrix + Codex | 10 | Sprint 3 |
| 5 | Goose + Gemini CLI | 6 | Sprint 3 (parallel with 4) |
| 6 | OpenCode + Skills + Final Validation | 9 | Sprint 4, 5 |

---

## Sprint 1: Foundation (Bug Fixes + Security)

**Goal:** Fix all pre-existing bugs (3 CRITICAL, 1 HIGH, 3 MEDIUM) and harden security. Zero regressions.

### Tasks
1. Create `agent_transfer/utils/tar_safety.py` — safe extraction utility
   - Reject path traversal (`../`), absolute paths, symlink escapes
   - Unit tests with malicious archive fixtures
   - Constitution: R7

2. Replace all `tar.extractall()` calls with safe utility (B1)
   - `transfer.py:331` — export archive extraction
   - `transfer.py:647` — import archive extraction
   - `import_analyzer.py:52` — preview extraction
   - `skill_validator.py:654` — skill archive extraction

3. Fix `ImportPreview` missing `skill_comparisons` arg (B2)
   - `import_analyzer.py:111` — add `skill_comparisons=[]` default

4. Fix XSS in templates (B3)
   - `agent_view.html:442` — sanitize markdown before `|safe`
   - `skill_view.html:561` — sanitize markdown before `|safe`
   - Use `bleach` or manual sanitization in `web_server.py`

5. Fix KEEP mode return value (B4)
   - `conflict_resolver.py:428` — return `None` for KEEP, not truthy path

6. Fix `pyproject.toml` packaging (B5)
   - Add `agent_transfer.utils` to packages
   - Add `templates/*.html` to package-data

7. Sync version numbers (B6)
   - `__init__.py` → `"1.1.0"` (match `pyproject.toml`)

8. Replace hand-rolled TOML parser with `tomllib`/`tomli` (B7)
   - `skill_validator.py:155-194` — use stdlib `tomllib` (3.11+) or `tomli` fallback

9. Grep codebase for all `tar.extractall()` / `tarfile.open()` — verify no sites missed (R7 audit)
10. Audit codebase for hardcoded absolute paths — replace with `Path.home()` (R6)
11. Add filename lint gate — reject `_v2`, `_new`, `_old` suffixes (R10)
12. Run full test suite — verify zero regressions
13. Run ruff lint + format
14. Run adversarial bug hunter (targeted) — constitution R12
15. Run adversarial bug hunter (general scan) — constitution R12
16. Git checkpoint: `v1.2.0-security`

---

## Sprint 2: Platform Abstraction Layer

**Goal:** Create the plugin architecture for platform detection and registration. Wrap existing Claude Code code.

### Tasks
1. Create `agent_transfer/platforms/__init__.py`
2. Create `agent_transfer/platforms/base.py`
   - `PlatformConfig` dataclass: name, slug, config_dirs, file_patterns, supports_mcp
   - `BasePlatform` ABC: `detect() -> bool`, `find_agents() -> list`, `find_skills() -> list`
   - `PlatformRegistry` class: `register()`, `get()`, `detect_all()`
   - Constitution: R9

3. Create `agent_transfer/platforms/claude_code.py`
   - Wraps existing `discovery.py`, `skill_discovery.py`, `parser.py`
   - Constitution: R4 (wrap, don't rewrite)

4. Create stub platforms (detect + config only):
   - `agent_transfer/platforms/codex.py`
   - `agent_transfer/platforms/gemini_cli.py`
   - `agent_transfer/platforms/goose.py`
   - `agent_transfer/platforms/opencode.py`

5. Add `agent-transfer platforms` CLI command
   - Rich table: platform name, slug, detected (Y/N), config dir, MCP support

6. Register platforms via entry_points in `pyproject.toml`
7. Verify all platform config dirs use `Path.home()`, no hardcoded paths (R6)
8. Tests: platform detection, config correctness, registry
9. Adversarial scan
10. Git checkpoint

---

## Sprint 3: IR Schema + Claude Code Ingestor/Emitter

**Goal:** Define the AI Intent Manifest (AIM) IR schema. Build Claude Code ingestor and emitter. Prove lossless round-trip.

### Tasks
1. Create `agent_transfer/ir/__init__.py`
2. Create `agent_transfer/ir/manifest.py`
   - `AIIntentManifest` dataclass: schema_version, identity, capabilities, triggers, logic, environment, mcp_servers, platform_specific (shadow data)
   - `to_yaml()` / `from_yaml()` serialization
   - Constitution: R2

3. Create `agent_transfer/ir/capability.py`
   - Step 1: Research native tool names for each platform (discovery)
   - Step 2: Build canonical tool map: platform-specific name <-> neutral name
   - Built-in mappings for all 5 platforms
   - `map_tool(platform, tool_name) -> canonical_name`

4. Create `agent_transfer/ir/validators.py`
   - Schema validation for AIM YAML
   - Required fields, type checks, version compatibility

5. Create `agent_transfer/ingestors/__init__.py`
6. Create `agent_transfer/ingestors/base.py`
   - `BaseIngestor` ABC: `ingest_agent(path) -> AIIntentManifest`
   - `ingest_skill(path) -> AIIntentManifest`

7. Create `agent_transfer/ingestors/claude_code.py`
   - Wraps existing `parser.py` / `skill_parser.py`
   - Produces `AIIntentManifest` with full shadow data for round-trip
   - Constitution: R4

8. Create `agent_transfer/emitters/__init__.py`
9. Create `agent_transfer/emitters/base.py`
   - `BaseEmitter` ABC: `emit_agent(manifest, target_dir) -> Path`
   - `emit_skill(manifest, target_dir) -> Path`

10. Create `agent_transfer/emitters/claude_code.py`
    - Reconstructs `.md` files from IR
    - Uses shadow data (`original_content`) for lossless output
    - Constitution: R1

11. **CRITICAL TEST:** Claude Code -> Ingestor -> IR -> Emitter -> Claude Code = byte-identical
    - Test with agents (system prompt, tools, hooks)
    - Test with skills (SKILL.md, scripts, deps)

12. Create test corpus: 5+ canonical agent fixtures (multi-line prompts, embedded YAML, unicode, code blocks)
    - "Preserved" for same-platform = byte-identical after round-trip (R1)
    - "Preserved" for cross-platform = system prompt text matches after whitespace normalization; tool references map through canonical registry; MCP configs are structurally identical via dict comparison

13. Tests for `ir/validators.py`, `ingestors/base.py`, `emitters/base.py` (R11)

14. Add `agent-transfer convert` CLI command
    - `convert <name> --from <platform> --to <platform>`
    - Only Claude Code <-> AIM at this point

15. Update `pyproject.toml` with new packages
16. Adversarial scan
17. Git checkpoint

---

## Sprint 4: Compatibility Matrix + Codex Support

**Goal:** Build the compatibility reporting system. Add first cross-platform target (Codex CLI — most similar to Claude Code).

### Tasks
1. Create `agent_transfer/compat/__init__.py`
2. Create `agent_transfer/compat/matrix.py`
   - Feature compatibility data for all platform pairs
   - Classifications: clean_transfer, best_effort_shim, cannot_transfer

3. Create `agent_transfer/compat/reporter.py`
   - Rich table display of compatibility matrix
   - Per-feature breakdown with color coding

4. Create `agent_transfer/compat/shims.py`
   - Instructional shim generation for non-transferable hooks
   - Injects equivalent behavior into system prompt

5. Add `agent-transfer compat` CLI command
   - Acceptance: Rich table showing feature / transfer quality / notes for each platform pair
6. Wire compat pre-flight into `convert` command — show compat report before cross-platform conversion
7. Create `agent_transfer/ingestors/codex.py` + `agent_transfer/emitters/codex.py`
8. Tests: Claude Code <-> IR <-> Codex round-trip + `compat/` module tests (R11)
9. Adversarial scan — targeted + general (R12)
10. Git checkpoint

---

## Sprint 5: Goose + Gemini CLI Support

**Goal:** Add Goose (YAML recipes) and Gemini CLI (JSON settings) support.

### Tasks
1. Create `agent_transfer/ingestors/goose.py` + `agent_transfer/emitters/goose.py`
2. Create `agent_transfer/ingestors/gemini_cli.py` + `agent_transfer/emitters/gemini_cli.py`
3. Test cross-platform conversions (Claude <-> Goose, Claude <-> Gemini, Goose <-> Gemini)
4. Update compatibility matrix with real test results
5. Adversarial scan
6. Git checkpoint

---

## Sprint 6: OpenCode + Skills + Documentation

**Goal:** Add OpenCode support (JS/TS plugin stubs). Build Claude Code automation skills. Plugin registration. Docs.

### Tasks
1. Create `agent_transfer/ingestors/opencode.py` + `agent_transfer/emitters/opencode.py`
2. Update compatibility matrix with OpenCode's 4 platform pairs — verify all 20 pairs present (SC-3)
3. IR portability test: load pre-generated `.aim.yaml` → emit to each target platform (US-5 validation)
4. Create Claude Code skill: `/transfer-agent` (convenience wrapper for US-1/US-3)
   - Trigger: "transfer agent to [platform]"; Input: agent name + target; Output: converted files + compat report
5. Create Claude Code skill: `/analyze-platform` (convenience wrapper for US-1/US-3)
   - Trigger: "analyze platform compatibility"; Input: optional --from/--to; Output: compat matrix table
6. Register entry_points for all platforms in `pyproject.toml`
7. Tests for OpenCode ingestor/emitter + skill behavior (R11)
8. Adversarial scan across full codebase
9. Git checkpoint: `v2.0.0`

---

## Risk Register

| Risk | Mitigation |
|------|-----------|
| Lossless round-trip fails | Shadow data preserves `original_content`; test early in Sprint 3 |
| Platform API changes | Plugin architecture isolates changes to single file |
| MCP config incompatibility | All platforms support MCP; pass-through for MCP tools |
| Hook semantics lost | Instructional shims as documented fallback |
| Scope creep | Constitution R5 locks existing behavior; new commands only |
