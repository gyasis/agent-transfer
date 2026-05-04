# Implementation Plan: AgentBridge MVP — Capability-Level Claude→Claude Transfer

**Branch**: `003-agentbridge-mvp` | **Date**: 2026-05-03 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/003-agentbridge-mvp/spec.md`
**Source PRD**: `~/dev/prd/scratch/agentbridge_capability_transfer_2026-05-03.md`

## Summary

Add a capability-level transfer flow on top of the existing same-platform Claude Code → Claude Code path. The unit of work is a named **capability** (e.g., "cascade-memory functionality") instead of a single skill or file. Source-side: a new `agentbridge-compose` skill + `ab compose --capability <name>` CLI proposes a 3-tier asset selection (CORE/COMPANIONS/CONTEXT) by walking dependency graphs across `~/.claude/` and surfaces it through a Rich-based selection matrix. The bundle ships as a "semi-package": existing tar bundle + a new source manifest (capabilities-not-files) + a "Dear Receiving Claude" briefing + per-asset Green/Yellow/Red risk tags + an all-or-nothing rollback tarball + script. Destination-side: a new `agentbridge-ingest` skill reads the briefing, re-presents the matrix, prompts on every Yellow/Red asset, executes BUILD+INGEST per the briefing's per-asset conflict policy, runs a smoke test, and leaves the rollback in place. Two parent-PRD carry-overs land in this feature: import-time `~/.claude.json` mcpServers path-rewrite, and a tightened secret regex (Bearer / `sk-` / `ghp_` / `xox*`). Repo + CLI rename to AgentBridge / `ab` happens at v1 cutover (R10-respecting: no file renames, only the package/CLI entry points). Mode B (cross-harness BUILD), Mode C (cross-machine native), and all non-Claude target harnesses are explicitly out of scope.

## Technical Context

**Language/Version**: Python ≥ 3.8 (per constitution Identity; supports 3.8–3.12)
**Primary Dependencies**: Click (CLI), Rich (TUI selection matrix + briefing preview), PyYAML (frontmatter), Pydantic (BaseModel for `ManifestModel`), pathlib / tarfile / shutil / hashlib (stdlib). No new heavy deps. Pydantic is the only potential addition; if not already pulled in transitively, this feature adds it.
**Storage**: Filesystem only. Bundle is a directory (or `.tar.gz`) with: `manifest.json`, `BRIEFING.md`, `bundle/` asset tree, `rollback.tar.gz`, `rollback.sh`, `confirmations.log` (per SC-007).
**Testing**: pytest (existing). Critical tests: capability round-trip on `/tmp/ab-mvp-sandbox-*`, byte-identical preservation of CORE assets (R1, R11), rollback file-tree diff, secret-redaction post-bundle scan (SC-006), permission-bit preservation (FR-011), settings.json idempotent merge (FR-014).
**Target Platform**: Linux + WSL (constitution R3). No macOS / Windows-native paths.
**Project Type**: Single-project Python CLI library — extends the existing `agent_transfer/` package. No web/mobile/service split.
**Performance Goals**: SC-004 source-side bundle production for cascade-memory < 60s; SC-005 destination-side ingestion (excluding user-pause time) < 30s.
**Constraints**:
- Constitution R1: same-platform CORE assets must round-trip byte-identical.
- Constitution R4: wrap don't rewrite — `config_manager.py`, `mcp_classifier.py`, `script_discovery.py`, `mcp_source_bundler.py`, `transfer.py`, `skill_parser`, `skill_discovery` are reused.
- Constitution R5: 9 existing CLI commands keep working unchanged.
- Constitution R6: no hardcoded absolute paths in logic; use `Path.home()`.
- Constitution R7: safe-extract on every tarfile open in ingestion + rollback restore.
- Constitution R8: no secrets in any shipped bundle; SC-006 verifies.
- Constitution R10: rename of `agent-transfer` → `AgentBridge` happens at the package/CLI/README level only — no file renames, no `_v2` / `_old` suffixes.
**Scale/Scope**: ~14 assets in the cascade-memory test bundle (1 bin + 7 skills + 2 hooks + 5 rule files including a CLAUDE.md section). prd-planning capability ~6 assets. v1 supports user-config-sized bundles (low hundreds of assets, ≤ 500MB hard cap inherited from `mcp_source_bundler.py`).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Rule | Status | Notes |
|---|---|---|
| R1 Lossless same-platform | PASS | CORE assets are written verbatim from `original_content`; no IR injection on Claude→Claude. SC-001 verifies. |
| R2 IR only for cross-platform | N/A | This feature is same-platform only. The new source manifest describes capabilities, but the asset bytes ship unmodified. |
| R3 Linux/WSL only | PASS | All paths via `Path.home()`. No platform-specific code added. |
| R4 Wrap don't rewrite | PASS | New code in `agent_transfer/bridge/` delegates to existing utils. Existing modules unchanged in behavior. |
| R5 Backward compatibility | PASS | New commands `ab compose`, new ingest skill. The 9 existing commands stay. CLI binary `ab` is added alongside `agent-transfer`; the old entry point continues to work. |
| R6 No hardcoded absolute paths | PASS | All paths derived from `Path.home()`, `Path.cwd()`, or passed-in arguments. |
| R7 Safe archive handling | PASS | Bundle extraction + rollback extraction both go through the existing safe-extract util. |
| R8 No secret transfer | PASS | FR-010 + SC-006: merged regex (Bearer / `sk-` / `ghp_` / `xox*` / generic) scans pre-seal AND post-seal. |
| R9 Plugin architecture | N/A | Capability composition is a layer on top of the existing Claude Code platform; no new platform/ingestor/emitter is registered. |
| R10 File naming discipline | PASS | Rename is at package/CLI/README level. No `_v2`/`_new`/`_old` suffixes. Existing files keep their names. |
| R11 Test coverage | PASS | New `tests/integration/test_capability_roundtrip.py` covers SC-001. Existing round-trip tests carry over. |
| R12 Adversarial bug hunting | REQUIRED AT MERGE | Before MVP merge, run targeted (rollback / secret-leak / settings.json merge) + general adversarial scans. Fix CRITICAL + HIGH. |

**Verdict**: PASS — no waiver entries needed. R12 is enforced at merge time, not at plan time.

## Project Structure

### Documentation (this feature)

```text
specs/003-agentbridge-mvp/
├── plan.md              # This file
├── spec.md              # Feature spec (already populated)
├── research.md          # Phase 0 — capability-graph heuristics, briefing format research (TODO)
├── data-model.md        # Phase 1 — ManifestModel, BriefingSection, AssetEntry, RiskTag (TODO)
├── quickstart.md        # Phase 1 — "ab compose cascade-memory" walkthrough (TODO)
├── contracts/           # Phase 1 — manifest.schema.json, briefing.template.md (TODO)
└── tasks.md             # Phase 2 — generated by /speckit.tasks
```

### Source Code (repository root)

```text
agent_transfer/
├── __init__.py
├── cli.py                       # Existing Click app — adds `ab compose` group; existing 9 commands unchanged
├── models.py                    # Existing — ManifestModel re-exported from bridge/models.py
├── templates/                   # Existing — adds skills/agentbridge-{compose,ingest}/SKILL.md sources
├── utils/                       # Existing — REUSED, not rewritten (R4)
│   ├── config_manager.py        # Existing — extended to emit ManifestModel-shaped capability output
│   ├── mcp_classifier.py        # Existing — extended with risk-tag field (Green/Yellow/Red)
│   ├── script_discovery.py      # Existing — extended to emit risk-tag per discovered script
│   ├── mcp_source_bundler.py    # Existing — secret regex tightened (FR-010)
│   ├── transfer.py              # Existing — gains import-time path-rewrite step (FR-015)
│   └── preflight/               # Existing — untouched
└── bridge/                      # NEW — all capability-level work lives here
    ├── __init__.py
    ├── models.py                # ManifestModel, AssetEntry, RiskTag, ConflictPolicy, BriefingSection (Pydantic)
    ├── compose.py               # `ab compose --capability` core: graph walk + selection-matrix data
    ├── briefing.py              # Renders BRIEFING.md from manifest + assets
    ├── selection_matrix.py      # Rich-based 3-tier selection matrix UI (used by export AND ingest)
    ├── preview.py               # Briefing Preview UI (Rich); enforces y/n on Yellow/Red
    ├── rollback.py              # Snapshots ~/.claude, ~/bin, ~/.claude.json regions before write
    ├── ingest.py                # Destination-side: read briefing, walk inventory, install per policy
    ├── smoke_test.py            # Post-install self-interrogation + drift detection
    └── secrets.py               # Merged regex (Bearer/sk-/ghp_/xox*/generic) — used pre- AND post-seal

# New ~/.claude skills (shipped by AgentBridge, installed once for the user)
# Canonical sources live at agent_transfer/templates/skills/... so they are versioned with the code
~/.claude/skills/agentbridge-compose/SKILL.md   # Source-side trigger
~/.claude/skills/agentbridge-ingest/SKILL.md    # Destination-side trigger

tests/
├── contract/
│   ├── test_manifest_schema.py          # ManifestModel ↔ JSON schema round-trip
│   └── test_briefing_sections.py        # BRIEFING.md must contain all 7 required sections
├── integration/
│   ├── test_capability_roundtrip.py     # SC-001 ship gate — cascade-memory in /tmp sandbox
│   ├── test_rollback_diff.py            # SC-002 — file-tree diff before vs after install→rollback
│   ├── test_settings_merge_idempotent.py # FR-014 — re-running ingestion does not duplicate hooks
│   ├── test_path_rewrite_mcp.py         # FR-015 — mcpServers paths rewritten on import
│   └── test_prd_capability_roundtrip.py # SC-009 — Story 2 post-ship validation
└── unit/
    ├── test_compose_graph.py            # Dependency walk produces expected COMPANIONS for given CORE
    ├── test_risk_tagging.py             # Green/Yellow/Red classification per asset type
    ├── test_secret_redaction.py         # SC-006 — merged regex catches all known patterns
    └── test_selection_matrix.py         # 3-tier rendering + user-trim semantics
```

**Structure Decision**: Single-project Python CLI (Option 1), extending the existing `agent_transfer/` package with a new `bridge/` subpackage. No backend/frontend split. Existing utils are imported and delegated to (R4); they are not rewritten. The two new `~/.claude/skills/` shipped by this project live outside the repo tree at install time but their canonical SKILL.md sources live at `agent_transfer/templates/skills/agentbridge-{compose,ingest}/SKILL.md` so they are versioned with the code.

## Phase 0 — Research (Required Before Phase 1)

Capture into `research.md`:

1. **Capability-graph heuristics**: Given a free-text capability name (e.g., "cascade-memory"), how does the composer decide which skills/hooks/rules belong? Approach: filename + frontmatter keyword match → expand via cross-references (skill mentions another skill, hook injects a rule path, rule references a `~/bin/` script). Document the deterministic graph rules; LLM reasoning runs on top of the deterministic candidates, not from scratch.
2. **Briefing format**: Confirm the 7 sections (Identity, Capability Description, Inventory, Build Instructions, Ingest Instructions, Verification, Rollback) are sufficient for a fresh receiving Claude to install without follow-up questions. Validate against the cascade-memory and prd-planning bundles by writing both briefings by hand first.
3. **Risk-tag classification rules**: Decide tag per asset type. Default rules: rule files = Green; skill markdown = Green unless it embeds tool-call params (then Yellow); MCP server config = Yellow; settings.json fragments = Yellow; hooks = Red; bin scripts that write state = Red, read-only = Yellow.
4. **Conflict-policy defaults per asset type**: skill markdown → ask; rule files → merge (additive); settings.json → merge (idempotent, additive); hooks → ask; bin scripts → overwrite if user confirmed Red; mcpServers → merge with path-rewrite.
5. **Rollback snapshot scope**: Exactly which paths to snapshot? Decision: union of (every destination path the bundle will touch) + (`~/.claude.json` whole file) + (`~/.claude/settings.json` whole file). Bin scripts snapshot the parent directory listing for orphan detection.
6. **Smoke-test prompts**: Exact text the receiving Claude self-asks. Draft 3 candidates, pick one for v1.

## Phase 1 — Design Outputs

- `data-model.md`: `ManifestModel`, `AssetEntry { path, dest_path, risk: Literal["green","yellow","red"], conflict: Literal["skip","merge","overwrite","ask"], sha256, mode_bits }`, `BriefingSection`, `Capability { name, description, intent, assets: list[AssetEntry], dependencies: list[str] }`, `Confirmation { asset_path, risk, decided_at, user_choice }`.
- `contracts/manifest.schema.json`: JSON Schema for `ManifestModel`. Used in `test_manifest_schema.py`.
- `contracts/briefing.template.md`: Markdown template for "Dear Receiving Claude" with placeholder slots for each section.
- `quickstart.md`: User-facing walkthrough — `ab compose --capability cascade-memory` → matrix → `ab export` → copy bundle → on dest: invoke `agentbridge-ingest` skill → smoke test → done.

## Phase 2 — Tasks (NOT generated here)

`tasks.md` will be produced by `/speckit.tasks` from this plan + spec. Tasks should map onto the PRD's M1–M5 phases (carry-overs Day 1; agent-briefing layer + composition Days 2–5; safety+UX Day 6; rename+polish Day 7; verification Day 8). Story 1 (cascade-memory) is the ship gate; Story 2 (prd-planning) is post-ship validation and its tasks should be marked accordingly so the orchestrator can defer them past the MVP commit.

## Complexity Tracking

> No constitution waivers required for this feature. Section intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
