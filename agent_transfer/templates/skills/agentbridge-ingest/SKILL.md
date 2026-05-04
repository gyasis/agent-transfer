---
name: agentbridge-ingest
description: Install an AgentBridge bundle on this machine. Use when the user gives Claude a `bundle-*.tar.gz` and says "install this AgentBridge bundle", "ingest this", or "set up the X capability from this bundle". Reads BRIEFING.md, re-presents the selection matrix, prompts on Yellow/Red assets, applies per-asset conflict policy (skip / merge / overwrite / ask), runs smoke test, and leaves rollback.tar.gz + rollback.sh in place.
---

# agentbridge-ingest

**Status:** Skeleton — full content lands in T036 (Wave 7).

## Trigger phrases

- "install this AgentBridge bundle"
- "ingest this"
- "set up the <X> capability from this bundle"

## What this skill does

Invokes `ab ingest <bundle>` from the AgentBridge package. The CLI:

1. Validates `manifest.json` against the schema.
2. Reads `BRIEFING.md` aloud (the "Dear Receiving Claude" letter).
3. Re-presents the 3-tier selection matrix so the user can further trim
   at install time.
4. Generates rollback snapshot (FR-016) before any destination write.
5. Prompts the user on every Yellow and Red asset.
6. Applies per-asset conflict policy (skip / merge / overwrite / ask).
7. Performs idempotent merge for `~/.claude.json` and `~/.claude/settings.json`.
8. Runs the post-install smoke test (FR-017).

Full instructions land in T036 once `ab ingest` is wired (T035, Wave 6).
