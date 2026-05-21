---
name: agent-transfer
description: Bundle and transfer Claude Code agents, skills, hooks, rules, MCP config, and bin scripts between machines or sessions. Two CLIs — `ab` (capability-scoped via `ab compose --capability NAME`) and `agent-transfer` (wholesale `export`/`import`/`init`/`doctor`). Use when the user says "transfer skills/agents", "bundle [capability]", "share [skill] with another machine", "export my [X] skills", "package this for [machine/teammate]", "transfer my Claude setup", "agent transfer", or "ab compose". Source repo at ~/dev/agent-transfer; executables at ~/bin/ab and ~/bin/agent-transfer.
---

# /agent-transfer — Capability bundling and Claude Code config transfer

`agent-transfer` (alias `ab`) is a local CLI (`~/dev/agent-transfer/`, v1.1+) for moving Claude Code config between sessions, machines, or teammates. Covers BOTH `~/.claude/agents/*.md` AND `~/.claude/skills/` (flat + folder-shape) AND rules + hooks + MCP config + `CLAUDE.md` + bin scripts.

## When to invoke

- "Transfer SIO skills to another machine" → wholesale export of `sio*` skill files
- "Bundle the cascade-memory capability" → `ab compose --capability cascade-memory`
- "Share my HH skills with [teammate]" → wholesale export or capability bundle
- "Back up my Claude config before re-installing WSL" → `agent-transfer export --all`
- "Install [bundle.tar.gz] on this new machine" → `agent-transfer import` + `agent-transfer init`

## Two entry points (same Click app)

| Form | When to use |
|---|---|
| `ab compose --capability NAME` then `ab ingest BUNDLE` | Capability-scoped — bundles one named capability with its companion hooks/rules/bin scripts, risk-tagged (Green/Yellow/Red), with `BRIEFING.md` for the receiving Claude. |
| `agent-transfer export [out.tar.gz] [--all]` then `agent-transfer import BUNDLE` | Wholesale — agents + skills + rules + hooks + MCP + CLAUDE.md + bin. Then `agent-transfer init` for path-rewrite + `~/.claude.json` merge, `agent-transfer doctor inspect` to validate. |

## What gets exported (wholesale path)

- User-level agents: `~/.claude/agents/*.md`
- User-level skills: `~/.claude/skills/*.md` (flat) AND `~/.claude/skills/<name>/SKILL.md` (folder-shape)
- Project-level agents + skills: `.claude/agents/`, `.claude/skills/` (cwd + up to 5 parents)
- Rules: `~/.claude/rules/**`
- Hooks: `~/.claude/hooks/**`
- MCP config: relevant `mcpServers` from `~/.claude.json`
- Top-level: `~/.claude/CLAUDE.md` (lands as `.incoming.` on destination, never auto-overwrites)
- Bin scripts referenced by exported skills/hooks

Secret scan runs pre-seal — Bearer / `sk-` / `sk-ant-` / `ghp_` / `xox*` / `ATBB...` / `AKIA...` / entropy fallback. Refuses to seal if it hits.

## Conflict handling on import

| Flag | Behavior |
|---|---|
| `--diff` (default) | Interactive diff per conflict — choose per-file |
| `--overwrite` | Replace all conflicts with incoming |
| `--keep` | Keep existing, skip conflicting incoming |
| `--duplicate` | Save incoming as `name_1.md`, `name_2.md` to avoid clobber |

`CLAUDE.md` and `~/.claude.json` are NEVER auto-overwritten — always land as `.incoming.` for manual review.

## Anti-patterns

- ❌ Tar-ing `~/.claude/` manually — misses bin scripts, doesn't risk-tag hooks, no rollback, no secret scan
- ❌ Telling the user "agent-transfer only handles agents" — that was the v1.0 readme; v1.1+ handles skills/rules/hooks/MCP too (source: `agent_transfer/utils/skill_discovery.py`)
- ❌ Running `agent-transfer init --yes` without `--i-accept-risks` (refused by design)
