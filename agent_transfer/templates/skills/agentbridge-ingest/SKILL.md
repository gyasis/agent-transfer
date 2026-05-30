---
name: agentbridge-ingest
description: Install an AgentBridge bundle on this machine. Use when the user gives Claude a `bundle-*.tar.gz` or a bundle directory and says "install this AgentBridge bundle", "ingest this", or "set up the X capability from this bundle". Reads BRIEFING.md, validates manifest.json against the schema, generates a rollback snapshot BEFORE any write (FR-016), prompts on every Yellow and Red asset (FR-013), applies per-asset conflict policy (skip / merge / overwrite / ask) including idempotent additive merge of ~/.claude.json + settings.json (FR-014), preserves mode bits (FR-011), runs the post-install smoke test (FR-017), and leaves rollback.tar.gz + rollback.sh in place.
---

# agentbridge-ingest

You have been given an AgentBridge bundle to install on this machine.

## Trigger phrases

Invoke this skill when the user says any of:

- "install this AgentBridge bundle"
- "ingest this"
- "set up the <X> capability from this bundle"
- "apply this bundle"
- "ab ingest <path>"

## What to do

1. **Read `BRIEFING.md` aloud or summarize it for the user** before
   doing anything. The briefing has 7 sections: Identity, Capability
   Description, Inventory, Build Instructions, Ingest Instructions,
   Verification, Rollback. The user MUST hear (at minimum) the
   Capability Description and Inventory before any write happens.

2. **Run `ab ingest <bundle>`.** The CLI will:
   - validate `manifest.json` against the schema (refuses
     incompatible major versions)
   - generate a rollback snapshot of every dest path it will touch,
     plus `~/.claude.json`, `~/.claude/settings.json`,
     `~/.claude/settings.local.json`
   - for each asset: verify sha256 against bundle bytes, prompt y/n on
     Yellow/Red, apply conflict policy (skip / merge / overwrite / ask),
     preserve mode bits via os.chmod
   - run the post-install smoke test and report drift

3. **Honor every Red prompt explicitly with the user.** Do NOT
   auto-confirm. The bundle's own `confirmations.log` only proves the
   SOURCE user was OK with the asset; the DESTINATION user must
   re-confirm. (Pass `--yes` only when the user explicitly says "yes
   to everything in this bundle".)

4. **If anything goes wrong, IMMEDIATELY invoke rollback** without
   waiting for further confirmation:
   ```bash
   bash <bundle-dir>/rollback.sh
   ```
   The rollback tarball was generated BEFORE any write, so restoring it
   returns the destination to pre-ingest state with zero leftover
   artifacts (SC-002). The Briefing's Rollback section explicitly
   authorizes you to invoke this without re-prompting on smoke-test
   failure or any destination-side write throw.

5. **After successful install**, run the smoke test's
   self-interrogation prompt (returned by `bridge.smoke_test.run()`):
   > "List the new skills, hooks, and rules currently loaded in your
   > config that are part of the {capability_name} capability. For each,
   > say what it does in 1 sentence."

   Compare your answer to the manifest's asset list. If any expected
   item is missing, that's drift — flag it but don't auto-rollback
   (presence + sha256 + mode_bits already passed at this point).

## CLI reference

```
ab ingest BUNDLE [OPTIONS]
  --yes              Auto-confirm Yellow/Red prompts (use only if user authorized)
```

`BUNDLE` can be either a directory or a `.tar.gz` archive. Tar archives
are extracted via `_safe_extract` which rejects path traversal and
symlink/hardlink members per constitution R7.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Install complete, smoke test passed |
| 5 | Smoke test failed — caller MUST invoke `bash rollback.sh` |
| 6 | At least one asset errored (sha256 mismatch / safe-extract reject / etc.) |

## What gets installed and where

The manifest's `capability.assets[*]` carries `dest_path`. Common
patterns for a bundle the user might receive:

| Asset kind | Typical dest_path | Default conflict |
|---|---|---|
| Skill markdown | `~/.claude/skills/<name>.md` | `ask` |
| Rule file | `~/.claude/rules/{tools,domains}/<x>.md` | `merge` (append-with-dedup) |
| Hook script | `~/.claude/hooks/<dir>/<x>.sh` | `ask` (Red) |
| Bin script | `~/bin/<x>` or `~/.local/bin/<x>` | `ask` (Red) |
| Settings fragment | `~/.claude/settings.json` | `merge` (additive idempotent) |
| MCP server entry | `~/.claude.json` | `merge` (with path-rewrite) |

**Path-rewrite** — `~/.claude.json` mcpServers entries that reference
source-machine absolute paths (e.g. `/home/src-user/.nvm/...`) are
rewritten to destination paths via `_classification.config_after_install`
when present, else best-effort string substitution (FR-015).

## Things you must not do

- Do NOT skip the briefing. The user must hear it before any write.
- Do NOT auto-rollback on the first Yellow asset failure — only the
  user can decide whether the partial install is acceptable.
- Do NOT carry the source `confirmations.log` over as if it were the
  destination user's confirmation. They are different people on
  different machines.
- Do NOT use `--yes` to silently install a Red-tier asset. If the user
  said "yes to everything", that's their call; if they didn't, prompt.

## Cross-references

- Source: `agent_transfer/bridge/ingest.py`
- CLI wiring: `agent_transfer/cli.py::ingest_cmd`
- Composer counterpart: `agentbridge-compose` skill on the source
- Manifest schema: `specs/003-agentbridge-mvp/contracts/manifest.schema.json`
- Briefing template: `agent_transfer/templates/briefing.template.md`
- Rollback details: `agent_transfer/bridge/rollback.py`,
  research.md §5 "Rollback snapshot scope"
