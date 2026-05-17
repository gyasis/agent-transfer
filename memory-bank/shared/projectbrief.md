# Project Brief

**Purpose**: North Star document - why this project exists

## Vision

`agent-transfer` (renamed to **AgentBridge** at v1 cutover) is an LLM-to-LLM capability transfer system. The unit of work is a named **capability** (e.g., "cascade-memory functionality") rather than individual files. Claude Code reasons about what that capability means in the user's config, composes a deterministic 3-tier asset bundle (CORE/COMPANIONS/CONTEXT), produces a "Dear Receiving Claude" briefing, and ships a semi-package. On the destination, Claude reads the briefing, presents the selection matrix, installs per conflict policy, and runs a smoke test. The user stays in the loop throughout.

## Goals

- **Primary**: Capability-level Claude Code to Claude Code transfer — user says "bundle my cascade-memory functionality" and a receiving machine ends up with functionally identical behavior.
- **Secondary (post-MVP)**: Cross-harness transfer (Mode B) to Goose / Letta / OpenCode / PromptChain via LLM-driven crosswalk synthesis.

## Success Criteria

- SC-001: cascade-memory capability roundtrip completes on a `/tmp/ab-mvp-sandbox-*` with byte-identical CORE assets and working session-search on the destination (MVP ship gate).
- SC-002: rollback restores the file tree to pre-install state with zero drift.
- SC-006: no secrets in any shipped bundle (merged regex: Bearer / `sk-` / `ghp_` / `xox*` / generic).
- Performance: source-side bundle production for cascade-memory < 60s; destination-side ingestion < 30s.

## Constraints

- Python >= 3.8 (supports 3.8-3.12). Linux + WSL only (constitution R3).
- No new heavy dependencies beyond Pydantic (potential addition for BaseModel).
- 9 existing CLI commands must keep working unchanged (constitution R5).
- No secrets in any shipped bundle (constitution R8).

## v1 Rename Note (AgentBridge / `ab`)

At v1 cutover the repo/package/CLI renames from `agent-transfer` to **AgentBridge** and the CLI binary from `agent-transfer` to `ab`. This rename happens at the **package entry point, CLI binary name, and README only** — no file renames, no `_v2`/`_old` suffixes anywhere. The old entry point continues to work (constitution R10, R5).
