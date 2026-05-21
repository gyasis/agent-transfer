# AGENT_TRANSFER_README.md — STALE, see `README.md`

This file is the original v1.0.0 readme from `13a2a3e Initial commit` (2025-01). It is **out of date** and intentionally kept short as a redirect so name-match searches (`*agent*transfer*README*`) don't land on outdated content.

## Read `README.md` instead

The current docs are in [`README.md`](./README.md) (755 lines, last updated `ef01463`). What changed since the v1.0.0 readme this file used to hold:

- **Renamed to AgentBridge** (commit `c764270`, Wave 8) — the project is now AgentBridge; `agent-transfer` remains as a CLI alias for back-compat (constitution R5).
- **Two CLI entry points** — `ab` (capability-scoped) and `agent-transfer` (wholesale). Both resolve to the same Click app.
- **Skills support** — both flat (`~/.claude/skills/name.md`) AND folder-shape (`~/.claude/skills/name/SKILL.md`) skills are exported/imported. See `agent_transfer/utils/skill_discovery.py`.
- **Rules, hooks, MCP config, bin scripts, CLAUDE.md** — wholesale `agent-transfer export` covers all of these, not just `~/.claude/agents/`.
- **Capability composition** (`ab compose --capability NAME`) — bundles a named capability (skill + companion hooks + rules + bin scripts) instead of dumping the whole tree.
- **`init` + `doctor`** subcommands — finish wire-up on the destination (`~/.claude.json` merge, path-rewrite, CLAUDE.md as `.incoming.`) and validate post-install (`doctor inspect` / `doctor playbook`).
- **Linux ↔ macOS round-trip** (spec `004-mac-compat`, commit `9b8a124`).
- **Plugin metadata + skill format drift handling** (commit `a06ef6d`, Q2/Q4).

## Why this redirect exists

A previous Claude Code session searched for "agent transfer" and read this stale file first, then incorrectly told the user "agent-transfer only handles agents, not skills." That was wrong — the actual code (since v1.1) walks `~/.claude/skills/` too. Replacing the stale body with this redirect prevents that misfire.

— Replaced 2026-05-21
