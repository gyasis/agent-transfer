---
name: agentbridge-compose
description: Bundle a named capability (skills + hooks + rules + bin scripts) from this Claude Code config so it can be installed on another machine. Trigger phrases include "bundle my <X> functionality", "I want to install <X> on another machine", "compose a capability", "AgentBridge bundle <name>". Runs `ab compose --capability <name>` to walk the dependency graph in ~/.claude/, propose a 3-tier selection matrix (CORE always-included / COMPANIONS opt-out / CONTEXT opt-in), prompt the user on every Yellow and Red asset, then seal a semi-package with manifest + Dear-Receiving-Claude briefing + risk tags + rollback tarball. Output goes to ./bundle-<capability>-<timestamp>/.
---

# agentbridge-compose

You are now bundling a Claude Code capability for transfer to another
machine. The user named a capability (e.g. "cascade-memory") and expects
a sealed bundle that another Claude can install on a fresh HOME.

## Trigger phrases

Invoke this skill when the user says any of:

- "bundle my <X> functionality"
- "I want to install <X> on another machine"
- "compose a capability called <X>"
- "AgentBridge: bundle <X>"
- "make an AgentBridge package for <X>"

## What to do

1. **Confirm the capability name with the user.** Don't guess. If they
   said "memory functionality", ask: "Do you mean the cascade-memory
   capability (session-search + 7 dependent skills + 2 hooks + 5 rules)?"

2. **Run `ab compose --capability <name>`.** The CLI walks `~/.claude/`,
   builds a 3-tier selection matrix, and shows it. CORE assets are
   non-removable; COMPANIONS default in (user can opt-out); CONTEXT
   defaults out (user can opt-in via `--add <dest_path>`).

3. **The Briefing Preview UI fires automatically.** It shows every asset
   with its risk tag (Green / Yellow / Red) and prompts y/n on every
   Yellow and Red asset. The user MUST confirm every Red before the
   bundle seals. If they decline a Red, the CLI exits 3 and the bundle
   is NOT sealed (this is intentional per FR-018 — no partial-trust
   bundles).

4. **The seal step writes 5 files into `bundle-<name>-<timestamp>/`:**
   - `manifest.json` — `ManifestModel` per `manifest.schema.json`
   - `BRIEFING.md` — the "Dear Receiving Claude" letter (7 sections)
   - `bundle/` — asset tree with preserved permissions
   - `rollback.tar.gz` — pre-install snapshot for the destination
   - `rollback.sh` — restore script for the destination
   - `confirmations.log` — audit trail of user Y/N decisions

5. **A pre-seal secret scan runs over manifest.json + BRIEFING.md.** If
   any pattern (Bearer / sk- / sk-ant- / ghp_ / xox / ATBB / AKIA /
   generic high-entropy) matches, the CLI exits 4 and refuses to seal.
   This is the second layer (the first is at asset-bundling time);
   together they enforce SC-006 "zero plaintext secrets in any bundle".

## CLI reference

```
ab compose --capability NAME [OPTIONS]
  --out PATH          Where to write the bundle (default: ./bundle-<name>-<ts>)
  --description TEXT  One-sentence description (overrides default)
  --intent TEXT       Why-it-exists narrative (overrides default)
  --drop DEST_PATH    Drop a COMPANIONS asset (repeatable)
  --add  DEST_PATH    Add a CONTEXT asset (repeatable)
  --yes               Auto-confirm Yellow/Red prompts (CI/tests; still logs)
  --no-bundle         Stop after preview; do not write bundle (dry-run)
```

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Bundle sealed |
| 2 | `ValueError`: no anchored matches for the given capability name — ask the user for a more concrete name |
| 3 | User declined a Red-tier asset (FR-018) — bundle NOT sealed |
| 4 | Pre-seal secret scan flagged a finding — bundle NOT sealed |

## What to tell the user when done

- The bundle path
- Approximate size (`du -sh <bundle>`)
- A reminder to copy `bundle-<name>-<ts>/` (the directory, not just the
  tar) to the destination machine and invoke the receiving
  `agentbridge-ingest` skill there

## Things you must not do

- Do NOT promise that COMPANIONS or CONTEXT items will be present —
  the user can trim them at preview time.
- Do NOT bypass the secret scan with `--yes` — the scan ALWAYS runs.
  `--yes` only auto-confirms the user-prompt step.
- Do NOT copy personal data into the bundle. The composer intentionally
  never bundles `~/.claude/projects/` (session JSONL transcripts) or
  `~/.specstory/` (formatted session history). If the user asks for
  these, decline and explain the scope rule.

## Cross-references

- Source: `agent_transfer/bridge/compose.py`, `selection_matrix.py`,
  `briefing.py`, `preview.py`, `rollback.py`
- CLI wiring: `agent_transfer/cli.py::compose`
- Receiving counterpart: `agentbridge-ingest` skill on the destination
- Manifest schema: `specs/003-agentbridge-mvp/contracts/manifest.schema.json`
- Briefing template: `agent_transfer/templates/briefing.template.md`
