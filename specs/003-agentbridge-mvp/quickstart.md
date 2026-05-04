# AgentBridge MVP — Quickstart

End-to-end walkthrough of the cascade-memory capability round-trip.
This is the **MVP ship gate** (SC-001).

## Prerequisites

- Linux or WSL
- Python ≥ 3.8
- A working Claude Code install with the cascade-memory capability already
  set up (the L1.5 anchor): `~/bin/session-search` plus the 7 dependent
  skills, 2 hooks, and 5 rule files.
- `pip install -e .` from the agent-transfer repo (or the published
  `agent-transfer` package) so both `agent-transfer` and `ab` console
  scripts are on PATH.

## Source machine — bundle the capability

```bash
ab compose --capability cascade-memory
```

What happens:

1. `agent_transfer/bridge/compose.py` walks `~/.claude/` and proposes a
   3-tier asset selection (CORE / COMPANIONS / CONTEXT).
2. The Rich-based selection matrix UI shows the proposal. You can opt
   out of COMPANIONS items or opt in to CONTEXT items. CORE items are
   non-removable.
3. The Briefing Preview UI shows every asset with its risk tag (Green /
   Yellow / Red). You confirm Y/N on every Yellow and Red.
4. The bundle is sealed at `./bundle-cascade-memory-<timestamp>.tar.gz`
   containing:
   - `manifest.json` (per `contracts/manifest.schema.json`)
   - `BRIEFING.md` (rendered from `contracts/briefing.template.md`)
   - `bundle/` asset tree with preserved permissions
   - `rollback.tar.gz` + `rollback.sh` (generated lazily on import)
   - `confirmations.log`

## Destination machine — install

```bash
mkdir -p /tmp/ab-mvp-sandbox-$(date +%s)
HOME=/tmp/ab-mvp-sandbox-... ab ingest bundle-cascade-memory-<ts>.tar.gz
```

Or, in a Claude Code session: drop the bundle in the project, then say
**"install this AgentBridge bundle"** — Claude invokes the
`agentbridge-ingest` skill, which calls `ab ingest` under the hood.

What happens:

1. Manifest validated against the JSON schema.
2. BRIEFING.md is read aloud.
3. Selection matrix is re-presented (you can further trim).
4. Rollback snapshot generated before any write (FR-016).
5. Per-asset conflict policy applied (skip / merge / overwrite / ask).
6. `~/.claude.json` mcpServers paths rewritten to destination paths (FR-015).
7. `settings.json` merged additively + idempotently (FR-014).
8. Smoke test runs:
   - `session-search foo` returns "no matches" cleanly on empty corpus.
   - All 7 dependent skills present.
   - Both hooks fire on triggering events.
   - All 5 rule files inject correctly.

## If something breaks

```bash
bash bundle-cascade-memory-<ts>/rollback.sh
```

Restores prior state with zero leftover artifacts (SC-002 verifies this
via file-tree diff).

## Performance targets

- SC-004: source-side bundle production for cascade-memory < 60 s.
- SC-005: destination-side ingestion (excluding user-pause time) < 30 s.

Numbers from the most recent verified run land here once T045 (Wave 8)
completes.
