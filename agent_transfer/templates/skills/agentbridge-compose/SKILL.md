---
name: agentbridge-compose
description: Bundle a named capability (skills + hooks + rules + bin scripts) from this Claude Code config so it can be installed on another machine. Use when the user says "bundle my X functionality", "I want to install X on another machine", or "compose a capability". Runs `ab compose --capability <name>` which proposes a 3-tier selection matrix (CORE / COMPANIONS / CONTEXT), waits for user confirmation, then seals a semi-package with manifest + Dear-Receiving-Claude briefing + risk tags + rollback tarball.
---

# agentbridge-compose

**Status:** Skeleton — full content lands in T032 (Wave 5).

## Trigger phrases

- "bundle my <X> functionality"
- "I want to install <X> on another machine"
- "compose a capability"
- "AgentBridge: bundle <name>"

## What this skill does

Invokes `ab compose --capability <name>` from the AgentBridge package
(installed via `pip install agent-transfer`).  The CLI walks `~/.claude/`
to enumerate contributing skills/hooks/rules/binaries, presents a 3-tier
selection matrix, and on user confirmation calls the existing
`agent_transfer/utils/transfer.py` exporter to produce a semi-package.

## What the user sees

1. Selection matrix in Rich UI (CORE / COMPANIONS / CONTEXT).
2. Briefing Preview UI — per-asset preview with Green/Yellow/Red risk tags.
3. Y/N confirmation on every Yellow and Red asset (FR-009, SC-007).
4. Sealed bundle written to `./bundle-<capability>-<timestamp>.tar.gz`.

Full instructions land in T032 once `ab compose` is wired (T031, Wave 4).
