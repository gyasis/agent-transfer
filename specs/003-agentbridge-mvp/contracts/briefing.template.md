<!--
  AgentBridge "Dear Receiving Claude" briefing template.

  This file is the authoritative template for the BRIEFING.md that ships
  at the root of every AgentBridge bundle. The render() function in
  agent_transfer/bridge/briefing.py (T028) substitutes the placeholders
  below using fields from manifest.json.

  Placeholder syntax: {{capability.name}}, {{asset.path}}, etc. — values
  are taken directly from the Pydantic ManifestModel.

  The 7 sections below are MANDATORY (FR-007). Tests in
  tests/contract/test_briefing_sections.py (T018) assert that every
  rendered briefing has all 7 non-empty.
-->

# Dear Receiving Claude

You have been given an AgentBridge bundle. Read this letter completely
before doing anything. Do not skim. Do not skip the Rollback section.

---

## 1. Identity

- **Capability name:** {{capability.name}}
- **Manifest schema version:** {{schema_version}}
- **Source machine hint:** {{source_machine_hint}}
- **Generated at:** {{generated_at}}

If anything below disagrees with `manifest.json`, **trust the manifest**
and stop. The manifest is signed by the source-side Briefing Preview UI;
this letter is hand-rendered prose.

---

## 2. Capability Description

{{capability.description}}

**Why it exists (in the user's words):** {{capability.intent}}

The bundle is **harness-aware**: every asset declares its `kind`
(skill | rule | hook | bin | capability) so a non-Claude harness
(OpenClaude / OpenClaw / ZeroClaw / PromptChain) can map it onto its
own primitive instead of guessing from the path. The reference
target is still Claude Code on Linux / WSL, but the schema is now
cross-harness portable — see §8 "Risk Mapping" below.

---

## 3. Inventory

The following assets ship in this bundle. **Risk tags drive how you
must treat each one:**

- **Green** — apply directly, no prompt needed (personas, tone, text-only rules)
- **Yellow** — show to user before write (tool defs, parameter types, settings.json fragments)
- **Red** — explicit user Y/N confirmation required (auth hooks, circuit breakers, state-writing hooks)

| Path in bundle | Destination | Kind | Risk | Conflict | Notes |
|---|---|---|---|---|---|
{{#each capability.assets}}
| `{{path}}` | `{{dest_path}}` | {{kind}} | {{risk}} | {{conflict}} | {{notes}} |
{{/each}}

### Per-asset behavior

Short behavioral summaries extracted from each CORE asset (skill/rule
first paragraph; bin/hook leading comment block). Use these to map
the asset onto your harness's primitive without opening the file.

{{#each capability.assets}}
- **`{{dest_path}}`** ({{kind}}) — {{behavior_md}}
{{/each}}

---

## 4. Build Instructions

For this MVP, "build" is a no-op — all assets ship as ready-to-install
files. (Build steps land later when Mode B / Crosswalker is added; out
of scope for this bundle.)

If `manifest.json` lists OS-level dependencies in `capability.dependencies`,
verify each one is on PATH before proceeding. Bundle dependencies
declared:

{{#each capability.dependencies}}
- `{{this}}`
{{/each}}

If any dependency is missing: **STOP**. Surface it to the user and ask
whether to install or abort.

---

## 5. Ingest Instructions

Execute in this exact order:

1. **Snapshot first** (FR-016). Run `agent_transfer.bridge.rollback.snapshot()`
   over the union of (every `dest_path` above, `~/.claude.json`,
   `~/.claude/settings.json`). The result is `rollback.tar.gz` +
   `rollback.sh` placed in the bundle root.

2. **Re-present the selection matrix** (FR-013). Even though the source
   user already trimmed at export time, the destination user may want
   to drop COMPANIONS or CONTEXT items.

3. **For every asset, in inventory order:**
   - If `risk == red`, prompt the user Y/N. On N: skip, mark in
     confirmations log, continue. Bundle is sealed without partial-trust;
     the user can always re-ingest.
   - If `risk == yellow`, show the asset preview, prompt Y/N.
   - If `risk == green`, apply directly.
   - Honor the asset's `conflict` policy:
     - `skip` — destination wins, do not write.
     - `merge` — for JSON files (`~/.claude.json`, `settings.json`) do
       additive idempotent merge. For markdown rules, append-with-deduplication.
     - `overwrite` — write bundle bytes verbatim. Preserve `mode_bits`.
     - `ask` — prompt user every time.

4. **Rewrite paths on import** (FR-015). Any `~/.claude.json` mcpServers
   entry that contains a source-machine absolute path MUST be rewritten
   to the destination home. Use the existing `_classification.config_after_install`
   data from `mcp_classifier.py`.

---

## 6. Verification

After install, run the smoke test (FR-017):

- For each declared asset: check it exists at `dest_path` with `mode_bits`.
- Run any bundle-declared smoke command (e.g., for `cascade-memory`:
  `session-search foo` should return "no matches" cleanly on an empty
  corpus, NOT an error).
- Ask yourself "who am I and what tools/skills/MCPs do I have?" and
  validate the answer against the manifest. Flag drift.

If verification fails: **invoke rollback** (next section) before
returning to the user.

---

## 7. Rollback

If anything goes wrong at any step:

```bash
bash {{bundle_root}}/rollback.sh
```

The rollback tarball was generated BEFORE any destination write.
Restoring it returns the destination machine to its pre-ingest state
with zero leftover artifacts (SC-002).

You are explicitly authorized to invoke rollback without further
user confirmation if the smoke test fails or any destination-side
write throws. Tell the user afterward.

---

## 8. Risk Mapping

How each asset `kind` lands on common agent harnesses. This table is a
STUB — concrete mappings live in `specs/agentbridge_v1.1/cross_harness_kind_mapping.md`
and are expected to be filled in as each harness adopts the v1.1 schema.

| `kind`     | Claude Code                | OpenClaude  | OpenClaw     | ZeroClaw     | PromptChain |
|------------|----------------------------|-------------|--------------|--------------|-------------|
| skill      | `~/.claude/skills/<x>.md`  | TBD         | TBD          | TBD          | TBD         |
| rule       | `~/.claude/rules/<...>.md` | TBD         | TBD          | TBD          | TBD         |
| hook       | `~/.claude/hooks/<x>/...`  | TBD         | TBD          | TBD          | TBD         |
| bin        | `~/bin/<x>` (executable)   | TBD         | TBD          | TBD          | TBD         |
| capability | composite — see manifest    | TBD         | TBD          | TBD          | TBD         |

If your harness is not listed, treat the asset as **inert** (no auto-
wire) and surface it to the user with the `behavior_md` summary so
they can decide whether/how to install.

---

*Sincerely, your earlier self on another machine.*
