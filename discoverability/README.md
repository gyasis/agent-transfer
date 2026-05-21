# Making agent-transfer discoverable to Claude Code agents

`agent-transfer` is a custom CLI, not a built-in Anthropic feature. A fresh Claude Code session does not know it exists. If a user types "transfer my skills" or "agent transfer", the session may:

- Not find the tool at all (no skill registration, no PATH entry).
- Find the stale `AGENT_TRANSFER_README.md` first (a v1.0.0 redirect file) and incorrectly conclude "agent-transfer only handles agents."
- Suggest tarring `~/.claude/` manually as a substitute (losing risk-tagging, secret scan, and rollback).

This directory holds the three small wire-ups that fix that. They are *consumer-side* — they live in `~/.claude/` and `~/bin/` after install, not inside the repo at runtime — so they're shipped here as **templates** you copy + a one-shot installer.

## What's here

| File | Destination | Purpose |
|---|---|---|
| `skill.md` | `~/.claude/skills/agent-transfer.md` | Appears in session-start skill list with trigger phrases ("transfer skills", "bundle capability", "ab compose", etc.). |
| `rule.md` | `~/.claude/rules/tools/agent-transfer.md` | Auto-injected on relevant tool use; pins the coverage table (agents AND skills AND rules AND hooks AND MCP AND CLAUDE.md AND bin) so a session can't fall back to the v1.0 misread. |
| `install.sh` | run once | Copies the two templates into place AND symlinks `~/bin/ab` + `~/bin/agent-transfer` to the venv shim. Idempotent. |

## Quick install

```bash
cd ~/dev/agent-transfer/discoverability
./install.sh
```

After it runs:

- `which ab` → `/home/<you>/bin/ab` (or your equivalent)
- `ab --version` → `ab, version 1.1.x`
- `~/.claude/skills/agent-transfer.md` exists
- `~/.claude/rules/tools/agent-transfer.md` exists
- Next Claude Code session will surface the skill in its skill list at session start.

## Why all three (A + B + C)

Any single one is brittle:

- **Skill alone (A)** — invisible if `~/.claude/skills/` isn't scanned that session, or if the description doesn't match the user's phrasing.
- **Rule alone (B)** — only fires on tool use, never at session start; doesn't surface the tool when the user is just *thinking* about transferring skills.
- **Symlink alone (C)** — `which ab` works but the agent has no description telling it *when* to reach for it.

Together: (A) session-start awareness, (B) in-task reinforcement that prevents the v1.0 misread, (C) shell-level discoverability so `which ab` works.

## Origin

2026-05-21 — a session searched for "agent transfer", found the stale `AGENT_TRANSFER_README.md` first, told the user `agent-transfer` doesn't handle skills, and was corrected by the user. The stale README is now a redirect pointer; this directory is the structural fix to prevent recurrence.
