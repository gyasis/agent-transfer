# Requirements Checklist: 001 — Platform-Agnostic Agent Transfer

**Spec:** `../spec.md`
**Status:** Pending

---

## Core Requirements

- [ ] **REQ-01**: Same-platform transfers remain byte-identical (R1)
  - Claude Code -> Claude Code = exact copy, no IR
  - Verified by round-trip test

- [ ] **REQ-02**: IR only used for cross-platform transfers (R2)
  - Same-platform path never touches IR
  - Cross-platform path always goes through IR

- [ ] **REQ-03**: Linux + WSL only (R3)
  - No macOS-specific code
  - No Windows native paths
  - `Path.home()` and `Path.cwd()` only (R6)

- [ ] **REQ-04**: Existing parsers wrapped, not rewritten (R4)
  - `parser.py` → `ingestors/claude_code.py` delegates
  - `skill_parser.py` → `ingestors/claude_code.py` delegates
  - `discovery.py` → `platforms/claude_code.py` delegates
  - `skill_discovery.py` → `platforms/claude_code.py` delegates

- [ ] **REQ-05**: All existing CLI commands work unchanged (R5)
  - `export`, `import`, `list-agents`, `list-skills`
  - `discover`, `view`, `validate-tools`, `validate-skills`, `check-ready`
  - Zero regressions in test suite

---

## Security Requirements

- [ ] **REQ-06**: Safe archive extraction everywhere (R7)
  - `tar_safety.py` utility created
  - All 4 `tar.extractall()` calls replaced
  - Path traversal rejected
  - Symlink escapes rejected
  - Absolute paths in archives rejected

- [ ] **REQ-07**: No secret transfer (R8)
  - IR defines `auth_requirements` but carries no secrets
  - API keys, tokens, credentials never appear in archives or IR

- [ ] **REQ-08**: XSS vulnerabilities fixed (B3)
  - Markdown sanitized before `|safe` in all templates
  - `agent_view.html`, `skill_view.html`, `web_server.py`

---

## Architecture Requirements

- [ ] **REQ-09**: Plugin architecture with ABCs (R9)
  - `BasePlatform`, `BaseIngestor`, `BaseEmitter` abstract classes
  - `PlatformRegistry` for runtime registration
  - Third parties can add platforms via `entry_points`
  - No hardcoded platform lists in core logic

- [ ] **REQ-10**: IR schema is YAML-based
  - `AIIntentManifest` with versioned schema
  - Includes: identity, capabilities, triggers, logic, environment, MCP
  - Shadow data (`platform_specific`) for round-trip fidelity

- [ ] **REQ-11**: Canonical tool mapping
  - Platform-specific tool names map through neutral names
  - MCP tools (`mcp__server__tool`) pass through directly

- [ ] **REQ-12**: Compatibility matrix covers all 20 platform pairs
  - 5 platforms x 4 targets = 20 pairs
  - Each feature classified: clean_transfer / best_effort_shim / cannot_transfer

---

## CLI Requirements

- [ ] **REQ-13**: `agent-transfer convert <name> --from <platform> --to <platform>`
  - Cross-platform conversion
  - Shows compatibility report before proceeding

- [ ] **REQ-14**: `agent-transfer platforms`
  - Lists all supported platforms
  - Shows detection status (installed/not found)
  - Shows MCP support

- [ ] **REQ-15**: `agent-transfer compat --from <platform> --to <platform>`
  - Shows feature-by-feature compatibility
  - Color-coded Rich table

---

## Bug Fix Requirements

- [ ] **REQ-16**: B1 — All `tar.extractall()` use safe extraction
- [ ] **REQ-17**: B2 — `ImportPreview` has `skill_comparisons=[]` default
- [ ] **REQ-18**: B3 — XSS fixed in all templates
- [ ] **REQ-19**: B4 — KEEP mode returns `None`, not truthy path
- [ ] **REQ-20**: B5 — `pyproject.toml` includes `utils` subpackage + templates
- [ ] **REQ-21**: B6 — Version synced between `__init__.py` and `pyproject.toml`
- [ ] **REQ-22**: B7 — TOML parser uses `tomllib`/`tomli`, not hand-rolled

---

## Test Requirements

- [ ] **REQ-23**: Lossless round-trip test (R11)
  - Claude Code agent -> IR -> Claude Code = byte-identical
  - Claude Code skill -> IR -> Claude Code = byte-identical

- [ ] **REQ-24**: Every new module has tests (R11)
  - `tar_safety.py` tests
  - `platforms/` tests
  - `ir/` tests
  - `ingestors/` tests
  - `emitters/` tests
  - `compat/` tests

- [ ] **REQ-25**: Adversarial bug hunt before each sprint merge (R12)
  - Targeted report
  - General scan
  - All CRITICAL and HIGH fixed before merge

---

## Success Metrics

- [ ] **MET-01**: Lossless round-trip passes
- [ ] **MET-02**: System prompts preserved in 100% of cross-platform conversions
- [ ] **MET-03**: Compatibility matrix covers all 20 platform pairs
- [ ] **MET-04**: Zero path traversal or XSS vulnerabilities
- [ ] **MET-05**: All existing tests pass (zero regressions)
