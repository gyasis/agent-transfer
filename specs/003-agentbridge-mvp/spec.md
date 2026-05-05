# Feature Specification: AgentBridge MVP — Capability-Level Claude→Claude Transfer

**Feature Branch**: `003-agentbridge-mvp`
**Created**: 2026-05-03
**Status**: Draft
**Input**: User description: "AgentBridge MVP - capability-level Claude to Claude transfer with agent-driven ingestion, per PRD agentbridge_capability_transfer_2026-05-03.md"
**Source PRD**: `~/dev/prd/scratch/agentbridge_capability_transfer_2026-05-03.md` (FINAL 8-day MVP cut, 2026-05-03T13:54:46+00:00)

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Bundle and install a capability across machines (Priority: P1) — SHIP GATE

A user has a working capability on Source Machine — e.g., "cascade-memory functionality" composed of the `session-search` binary, 7 Claude Code skills that call it, 2 hooks, and 5 rule files. The user wants the same capability working on Destination Machine without copying their personal session data.

On Source: the user tells Claude "Bundle my cascade-memory functionality so I can install it on another machine." Claude (via `ab compose --capability cascade-memory`) reasons about what cascade-memory means in this user's config, enumerates contributing skills/hooks/rules/binaries by walking dependency graphs, and presents a 3-tier selection matrix (CORE always-included / COMPANIONS opt-out / CONTEXT opt-in) with risk tags. The user reviews, optionally trims, and confirms. `ab export` produces a semi-package: bundle directory + source manifest + agent-readable "Dear Receiving Claude" briefing + rollback tarball.

On Destination: the user gives a fresh Claude session the bundle and says "Install this AgentBridge bundle." Claude invokes the `agentbridge-ingest` skill, reads the briefing, re-presents the selection matrix (so the user can further trim at install time), executes BUILD + INGEST per the briefing's instructions with per-asset conflict resolution (skip / merge / overwrite / ask), runs the post-install smoke test, and leaves the rollback in place.

**Why this priority**: This is the entire MVP. If this round-trips on a fresh sandbox HOME, the foundation is proven and the post-MVP cross-harness work (Modes B and C) has a working substrate to extend. If it fails, the architecture has a real gap that must be fixed before any cross-harness work begins.

**Independent Test**: On a fresh sandbox HOME at `/tmp/ab-mvp-sandbox-$(date +%s)`, run `ab compose --capability cascade-memory` → confirm selection matrix → bundle is produced → invoke `agentbridge-ingest` skill on the destination Claude with the bundle → smoke test passes → `bash rollback.sh` cleanly restores prior state.

**Acceptance Scenarios**:

1. **Given** Source Machine has session-search installed (binary + 7 skills + 2 hooks + 5 rule files), **When** user runs `ab compose --capability cascade-memory`, **Then** Claude proposes the 14 expected assets (with risk tags) in a 3-tier selection matrix and waits for confirmation.
2. **Given** the user confirms the proposed selection, **When** `ab export` runs, **Then** the bundle contains: source manifest (capabilities-not-files), all selected assets with preserved permissions, "Dear Receiving Claude" briefing with all required sections, rollback tarball + script, and risk-tag inventory.
3. **Given** a sealed bundle on Destination Machine with empty corpus, **When** the receiving Claude invokes `agentbridge-ingest` on it, **Then** the briefing is read, selection matrix is re-presented, user confirms Yellow/Red items, BUILD+INGEST executes per briefing, and `session-search foo` runs cleanly returning "no matches" (correct behavior on empty corpus).
4. **Given** a successful install, **When** receiving Claude is asked "how do I use session-search?", **Then** it answers correctly using the imported rules.
5. **Given** an installed bundle, **When** user runs `bash rollback.sh`, **Then** all bundle-introduced files are removed, prior config is restored, and no leftover artifacts remain.
6. **Given** a Yellow- or Red-tagged asset in the bundle, **When** ingestion reaches it, **Then** the user is prompted before any write happens.
7. **Given** an install with a destination-side path conflict, **When** ingestion reaches the conflicting asset, **Then** the per-asset conflict policy from the briefing (skip/merge/overwrite/ask) is honored.

---

### User Story 2 — Skill+CLI+hook capability with runtime guard (Priority: P2) — POST-SHIP VALIDATION

The user wants to transfer the `prd` planning capability (CLI binary + skill definition + `prd-guard` PreToolUse hook + plan-persistence rule + companion skills like `prd-checkout` and `prd-summary`). The hook is RED-tier because it enforces blocking behavior; if translation drifts, it could either block too much or fail to block when it should. Acceptance proves the briefing can describe non-trivial conditional behavior (when does the hook block vs allow) and that the receiving Claude correctly wires settings.json entries.

**Why this priority**: This is post-ship validation, not a blocker for declaring MVP shipped. It exercises the COMBINATION of binary + skill + hook + settings.json wiring (none of session-search's pieces need settings.json), validates the Red-tier confirmation path, and tests rule-with-runtime-rule (the plan-persistence rule contains the Decision Rule that the `prd` CLI implements).

**Independent Test**: After Story 1 ships, run `ab compose --capability prd-planning` on Source → bundle → import to a fresh sandbox HOME → confirm `prd new test_descriptor` creates the stub at the right location, `prd-guard` blocks writes outside `scratch/` as expected, and allows writes when the skill-internal lock is held.

**Acceptance Scenarios**:

1. **Given** Source has the prd capability installed, **When** `ab compose --capability prd-planning` runs, **Then** the proposal includes the `~/bin/prd` binary, `prd.md` skill, `prd-guard` hook directory, `settings.json` entries that wire the hook, companion skills, and the plan-persistence rule — all with appropriate risk tags (hook = Red, settings entries = Yellow).
2. **Given** ingestion on a fresh sandbox HOME, **When** the receiving Claude reaches the `settings.json` merge step, **Then** it merges the hook entries non-destructively (existing entries preserved) and prompts the user before writing.
3. **Given** the install is complete, **When** an off-skill agent tries to write a PRD outside `scratch/`, **Then** the `prd-guard` hook blocks the write.
4. **Given** the install is complete, **When** the `prd` skill takes its internal lock and writes outside `scratch/`, **Then** the hook allows the write.

---

### Edge Cases

- **Empty corpus on destination**: `session-search foo` must return "no matches" cleanly, not an error. The briefing must explain that the JSONL corpus is intentionally not transferred (personal data, multi-GB).
- **Missing dependency on destination**: Bundle declares `session-search` requires `ripgrep`. If destination lacks `ripgrep`, ingestion must detect this, surface it in the briefing/preview, and either install or refuse with a clear message — never silently produce a broken state.
- **Pre-existing conflicting file on destination**: For each destination path the bundle would write, the briefing's per-asset conflict policy (skip/merge/overwrite/ask) is honored.
- **Pre-existing `settings.json` with hooks already configured**: Hook merge must be additive and idempotent. Re-running ingestion should not duplicate hook entries.
- **Asset permissions**: Executable bits on `~/bin/*` scripts must survive the round-trip. Read-only files must not become writable on import.
- **Path-rewrite for MCP servers**: `~/.claude.json` mcpServers entries that reference source-machine absolute paths must be rewritten to destination-machine paths using `_classification.config_after_install`.
- **Partial install failure**: If ingestion fails mid-way, the rollback tarball + `rollback.sh` must restore prior state with no leftover artifacts.
- **Secrets in source config**: Bearer tokens, `sk-`/`ghp_`/`xox*` patterns, Bitbucket app passwords must be redacted before bundling, even when they appear in MCP server env entries or auth headers.
- **User declines a Red-tier asset at preview**: Bundle is sealed without that asset; downstream dependents must be flagged in the briefing as degraded.
- **Selection matrix on destination differs from source**: User trims further at ingestion time; ingestion proceeds only on the trimmed set, and the rollback covers exactly what was actually installed.
- **Capability name with no clear bounds**: `ab compose --capability foo` where Claude can't reason about what `foo` includes — must fail with a "describe the capability more concretely" prompt rather than guessing and bundling random assets.

---

## Requirements *(mandatory)*

### Functional Requirements

**Source-side capability composition**

- **FR-001**: System MUST provide a CLI command `ab compose --capability <name>` that takes a free-text capability name and produces a proposed asset bundle.
- **FR-002**: System MUST provide an `agentbridge-compose` skill at `~/.claude/skills/agentbridge-compose/SKILL.md` that the agent invokes when the user asks to bundle a named capability.
- **FR-003**: The composer MUST enumerate contributing skills, hooks, rule files, MCP servers, and bin scripts by reading `~/.claude/` and reasoning about coherence with the named capability.
- **FR-004**: The composer MUST walk dependency graphs for each candidate asset (e.g., a skill that calls `session-search` pulls in `~/bin/session-search`; a hook that injects a rule pulls in that rule file) to surface companions.
- **FR-005**: The composer MUST present a 3-tier selection matrix (CORE always-included / COMPANIONS opt-out / CONTEXT opt-in) populated with the agent's proposal and require user confirmation before sealing.

**Source-side export and bundle format**

- **FR-006**: System MUST produce a source manifest schema (`ManifestModel`) that describes the bundle as **capabilities** (intent, behavior, dependencies, risk tier) — not as a flat file list. The manifest extends current `agent_transfer/utils/config_manager.py` output.
- **FR-007**: System MUST emit a "Dear Receiving Claude" briefing in Markdown at the bundle root with sections: Identity, Capability Description, Inventory (with risk tags), Build Instructions, Ingest Instructions (with per-asset conflict policy), Verification, Rollback.
- **FR-008**: System MUST tag every asset Green / Yellow / Red. Green = personas/tone/text-only rules. Yellow = tool definitions, parameter types, settings.json entries. Red = auth hooks, circuit breakers, state-writing hooks, anything that blocks tool calls.
- **FR-009**: System MUST present a Briefing Preview UI (Rich-based CLI) on the source side before sealing the bundle, showing per-asset preview with risk tags. The user MUST `y/n` every Yellow/Red translation before the bundle is sealed.
- **FR-010**: System MUST redact secrets at bundle time. Detection MUST cover targeted patterns (Bearer, `sk-`, `ghp_`, `xox*`) merged with the existing generic regex.
- **FR-011**: System MUST preserve file permissions (notably executable bits on `~/bin/*` scripts) through bundle round-trip.

**Destination-side ingestion**

- **FR-012**: System MUST provide a receiving-side ingestion skill at `~/.claude/skills/agentbridge-ingest/SKILL.md` that the receiving Claude invokes when given an AgentBridge bundle.
- **FR-013**: The ingestion skill MUST read the briefing, walk the inventory, present the selection matrix again at install time so the user can further trim, prompt on every Yellow and Red asset before any write, and execute install per the briefing.
- **FR-014**: System MUST honor per-asset conflict policy (skip / merge / overwrite / ask) declared in the briefing. The destination merge for `~/.claude.json` and `settings.json` MUST be additive and idempotent.
- **FR-015**: System MUST rewrite path-prefixed entries on import. `~/.claude.json` mcpServers entries that reference source-machine absolute paths MUST be rewritten to destination-machine paths using `_classification.config_after_install`.

**Safety**

- **FR-016**: System MUST generate an all-or-nothing rollback tarball (snapshot of `~/.claude`, `~/bin`, `~/.claude.json` regions that the install will touch) before any destination write. The bundle MUST include `rollback.tar.gz` and `rollback.sh`.
- **FR-017**: System MUST run a post-install smoke test in which the receiving Claude session asks itself "who are you and what tools/skills/MCPs do you have?" and validates the answer against the source manifest. Drift MUST be flagged.
- **FR-018**: System MUST refuse to seal a bundle when the user declines confirmation on a Red-tier asset; partial-trust bundles are not allowed.

**Backward compatibility (constitution R5)**

- **FR-019**: All existing agent-transfer CLI commands (export, import, list-agents, list-skills, discover, view, validate-tools, validate-skills, check-ready) MUST continue to work unchanged. New commands (`ab compose`, `agentbridge-ingest` skill invocation) are additions only.
- **FR-020**: Existing modules (`config_manager.py`, `mcp_classifier.py`, `script_discovery.py`, `mcp_source_bundler.py`, `transfer.py`, `skill_parser`, `skill_discovery`) MUST be reused rather than rewritten (constitution R4).

**Naming**

- **FR-021**: Repository, package, and CLI binary MUST rename from `agent-transfer` to `AgentBridge` / `ab` at v1 cutover (not gradually). README MUST be rewritten around "capability-level transfer with agent-driven composition and ingestion."

### Out of Scope (post-MVP, do NOT implement in this feature)

- Mode B: cross-harness BUILD (Crosswalker workflow, per-target prompt library).
- Mode C: cross-machine native propagation for non-Claude target harnesses.
- Goose / Letta / OpenCode / PromptChain target support.
- Built/native manifest schema (only needed for Mode B/C).
- `ab purge` command (only meaningful for cross-harness scenarios; Mode A rollback is sufficient for MVP).
- Day-0 hand-translation Goose experiment (only needed before Mode B coding).
- HTTP-transport MCP server import (3 servers affected; deferred from parent PRD).

### Key Entities

- **Capability**: A named bundle of intent + behavior the user invokes by name (e.g., "cascade-memory functionality", "prd-planning"). Composes one or more contributing assets.
- **Asset**: A concrete file the bundle ships (skill markdown, hook script, rule file, bin binary, settings.json fragment, MCP server config). Carries a risk tag and a conflict policy.
- **Source Manifest**: JSON document describing the bundle as capabilities (intent, behavior, dependencies, risk tier per asset). Authoritative on source side.
- **Briefing ("Dear Receiving Claude")**: Markdown letter at bundle root that the receiving Claude reads to understand what to install and how. Sections: Identity, Capability Description, Inventory, Build Instructions, Ingest Instructions, Verification, Rollback.
- **Selection Matrix**: 3-tier UI (CORE / COMPANIONS / CONTEXT) presented at both export and ingestion. Drives what is bundled (source) and what is installed (destination).
- **Risk Tag**: One of Green (personas/tone), Yellow (tool defs / parameter types / settings entries), Red (auth hooks / circuit breakers / state-writing). Drives whether user confirmation is required.
- **Rollback**: Tarball + script generated before any destination write. All-or-nothing restore.
- **Smoke Test**: Post-install self-interrogation by the receiving Claude, validated against the source manifest.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001 (SHIP GATE)**: On a fresh sandbox HOME at `/tmp/ab-mvp-sandbox-$(date +%s)`, the cascade-memory capability round-trips end-to-end. `ab compose --capability cascade-memory` → selection matrix confirmed → `ab export` → bundle copied to sandbox → `agentbridge-ingest` skill invoked → smoke test passes → `session-search foo` runs cleanly returning "no matches" → all 7 dependent skills present → both hooks fire on triggering events → all 5 rule files inject correctly → receiving Claude can answer "how do I use session-search?" using imported rules.
- **SC-002**: `bash rollback.sh` from the bundle restores prior state with zero leftover artifacts (verified by file-tree diff before vs after install→rollback).
- **SC-003**: `ab status` after install reports the cascade-memory capability with all dependencies satisfied. After rollback, the same command reports it absent.
- **SC-004**: Source-side bundle production for cascade-memory completes in under 60 seconds on the user's current machine.
- **SC-005**: Destination-side ingestion (excluding user-confirmation pause time) completes in under 30 seconds.
- **SC-006**: Zero plaintext secrets are present in any shipped bundle. Verified by post-bundle scan against the merged secret regex (Bearer / `sk-` / `ghp_` / `xox*` / generic).
- **SC-007**: Every Red-tier asset in any produced bundle was confirmed by the user via the Briefing Preview UI before the bundle was sealed (audit log of confirmations exists in the bundle).
- **SC-008**: All 9 existing CLI commands (export, import, list-agents, list-skills, discover, view, validate-tools, validate-skills, check-ready) pass their existing tests after the rename to AgentBridge / `ab`.
- **SC-009 (post-ship validation, NOT a ship blocker)**: Story 2 (prd-planning capability) round-trips end-to-end on a fresh sandbox HOME with `prd-guard` correctly blocking writes outside `scratch/` and allowing writes when the skill-internal lock is held.
