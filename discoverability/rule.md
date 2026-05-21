# agent-transfer / AgentBridge Tool Rules

## What this tool is

`agent-transfer` (alias `ab`, v1.1+) is a local CLI at `~/dev/agent-transfer/` for moving Claude Code config between sessions/machines/teammates. It is **NOT** an Anthropic-provided feature — it is a custom tool.

## Coverage (DO NOT mis-state)

`agent-transfer` handles **ALL** of these — not only agents:

| Asset | Location | Supported |
|---|---|---|
| Agents | `~/.claude/agents/*.md` | ✅ (since v1.0) |
| Skills (flat) | `~/.claude/skills/*.md` | ✅ (v1.1+) |
| Skills (folder) | `~/.claude/skills/<name>/SKILL.md` | ✅ (v1.1+) |
| Rules | `~/.claude/rules/**` | ✅ |
| Hooks | `~/.claude/hooks/**` | ✅ (risk-tagged Red, requires explicit confirm) |
| MCP servers | `~/.claude.json` mcpServers | ✅ |
| CLAUDE.md | `~/.claude/CLAUDE.md` | ✅ (lands as `.incoming.` — never auto-overwrites) |
| Bin scripts | referenced by exported skills/hooks | ✅ |
| Project-level | `.claude/{agents,skills}/` in cwd + parents | ✅ |

**NEVER tell the user "agent-transfer only handles agents."** That was the v1.0.0 readme (`AGENT_TRANSFER_README.md`, now a stale-pointer file). The current README is `README.md` in the same repo.

## Two entry points

- `ab compose --capability NAME` / `ab ingest BUNDLE` — capability-scoped (bundles one named capability + companion hooks/rules/bin, risk-tagged, with `BRIEFING.md`)
- `agent-transfer export` / `import` / `init` / `doctor` — wholesale (whole-tree dump and replay)

Both resolve to the same Click app (constitution R5 back-compat).

## When to suggest agent-transfer

Triggers — any one fires:
- User says "transfer skills", "transfer agents", "bundle [capability]", "share with [machine/teammate]", "export my Claude setup", "ab compose"
- User is about to manually tar `~/.claude/` — STOP and offer `agent-transfer export --all` instead (does risk-tagging, secret scan, rollback snapshot)
- User wants to back up before a destructive change to `~/.claude/`

## Secret-scan refusal

`ab compose` refuses to seal a bundle that fails the merged regex secret scan. If the scan flags, fix the secret in the source file (rotate + remove) — do NOT bypass.

## init / doctor — destination-side

After `agent-transfer import` extracts, `agent-transfer init <bundle-dir>` finishes wire-up:
- Path-rewrite (source-machine paths → destination paths)
- `~/.claude.json` merge (additive, never destructive)
- `CLAUDE.md` lands as `.incoming.` for manual diff/apply
- `--yes` mode REQUIRES `--i-accept-risks` (intentional friction gate)

After init: `agent-transfer doctor inspect` validates and exits 1 on any failed check. `agent-transfer doctor playbook` outputs a markdown bootstrap guide for the receiving Claude session.

## NEVER do

- ❌ Tar `~/.claude/` manually as a substitute — loses risk-tagging, rollback, secret scan
- ❌ Claim "agent-transfer only does agents" — read `agent_transfer/utils/skill_discovery.py` first
- ❌ Run `agent-transfer init --yes` without `--i-accept-risks`
- ❌ Bypass the secret scan
- ❌ Auto-overwrite `CLAUDE.md` on destination (the tool itself refuses; don't work around it)
