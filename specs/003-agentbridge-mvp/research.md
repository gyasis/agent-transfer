# Research — AgentBridge MVP (003)

Phase 0 research per `plan.md`. Six questions; answers inform Phase 1
design (`data-model.md`, `contracts/`, `quickstart.md`).

---

## 1. Capability-graph heuristics

**Question:** Given a free-text capability name (e.g. "cascade-memory"),
how does the composer decide which skills/hooks/rules belong?

**Decision:** Hybrid — deterministic graph walk over `~/.claude/` first,
LLM reasoning runs only on top of the deterministic candidates.

**Algorithm:**

1. **Anchor pass**: case-insensitive match of the capability name (and
   common synonyms supplied by the user or LLM) against:
   - filenames under `~/.claude/skills/`, `~/.claude/hooks/`,
     `~/.claude/rules/`
   - frontmatter `description:` and `name:` fields
   - first 2 KiB of each file body (covers section headers and
     trigger-phrase blocks)
2. **Cross-reference expansion** (depth-bounded BFS, max 2 hops):
   - skill → other skills it `mention`s by slug (`/foo`, `--skill foo`)
   - skill → `~/bin/<X>` references → ScriptReference
   - hook → rule path it injects (regex `~/.claude/rules/.../*.md`)
   - rule → skill it directs (`/skill-name`)
3. **Tiering**: each candidate gets one of three labels.
   - **CORE** — anchored directly OR is a strict-mode bin script reference.
     Cannot be removed at the selection matrix.
   - **COMPANIONS** — within 1 hop of a CORE asset, OR a hook/settings
     entry that wires CORE behavior. User can opt-out.
   - **CONTEXT** — 2 hops out, OR matched only via lenient (bare-word)
     reference. User must opt-in.

**LLM layer:** the deterministic graph produces (CORE, COMPANIONS, CONTEXT)
sets. The LLM step (in `agentbridge-compose` skill) only edits the proposal
shown in the selection matrix — adding a missing item, dropping a stray.
It NEVER fabricates assets that aren't on disk.

**Why this:** matches FR-003 + FR-004 while preventing hallucinated bundle
contents. Edge case "capability name with no clear bounds" is handled by
the anchor pass returning empty → the composer surfaces a "describe more
concretely" prompt rather than guessing.

---

## 2. Briefing format

**Question:** Are the 7 sections sufficient for a fresh receiving Claude
to install without follow-up questions?

**Decision:** Yes for the cascade-memory and prd-planning capabilities,
verified by writing both briefings by hand. The 7 sections are mandatory
(FR-007 + the contract test in `tests/contract/test_briefing_sections.py`).

**Section purpose map:**

| Section | Receiver question it answers |
|---|---|
| Identity | "What machine and capability is this?" |
| Capability Description | "What does this DO and why does it exist?" |
| Inventory | "What files am I about to write, where, and how risky?" |
| Build Instructions | "Do I need to assemble anything before placing files?" |
| Ingest Instructions | "Exact step order; what to merge vs overwrite vs skip" |
| Verification | "How do I know it worked?" |
| Rollback | "What do I run if anything broke?" |

**What was added during research:** an **Authorization to invoke rollback
without further user confirmation if the smoke test fails or any write
throws** clause in §7. Without it, a partial-install failure leaves the
agent waiting on user prompt; the rollback tarball was generated for
exactly this case so use it.

---

## 3. Risk-tag classification rules

**Question:** What are the exact rules per asset type?

**Decision** (codified in `tests/unit/test_risk_tagging.py` so they are
enforced):

| Asset type | Default | Promotion rules |
|---|---|---|
| Rule file (`.md` under `rules/`) | green | → yellow if it embeds tool-call args; → red never |
| Skill markdown | green | → yellow if it embeds tool params; → red if it ships a hook |
| Settings.json fragment | yellow | → red if hooks include `PreToolUse` blockers |
| MCP server config (no auth) | yellow | → green if no env, no headers, no warnings |
| MCP server config (with auth) | red | (any env key matching `AUTH`/`TOKEN`/`KEY` or any header) |
| Hook script | red | always — they intercept tool calls |
| Bin script (read-only) | green | grep/find/cat/ls/echo/head/tail with no auth strings |
| Bin script (state-writing) | red | rm/mv/git push/git commit/sed -i/perl -pi/install/curl -X POST/etc. |
| Bin script (other) | yellow | default |

The MCP rules live in `agent_transfer/utils/mcp_classifier.py::_compute_risk_tag`.
The script rules live in `agent_transfer/utils/script_discovery.py::tag_script`.

---

## 4. Conflict-policy defaults per asset type

**Question:** What's the default conflict policy when the destination
already has a file at the asset's destination path?

**Decision:**

| Asset type | Default conflict | Reason |
|---|---|---|
| Skill markdown (`*.md` under `skills/`) | ask | could shadow user's local edits |
| Rule file | merge | rules are append-only sections; safe to dedupe-append |
| Settings.json | merge (idempotent) | additive merge of hooks/env keys; never replace |
| `~/.claude.json` (mcpServers) | merge with path-rewrite | per FR-015 |
| Hook script | ask | red-tier; user must confirm |
| Bin script (read-only) | overwrite | safe — no state — assuming user confirmed Yellow |
| Bin script (state-writing) | ask | red-tier; user must confirm every overwrite |
| Anything else | overwrite | bundle is the source of truth |

These are *defaults*; the source-side composer can override per-asset by
writing a non-default `conflict` value into the manifest.

---

## 5. Rollback snapshot scope

**Question:** Exactly which paths to snapshot before any write?

**Decision:** the **union** of:

1. Every destination path the bundle declares (manifest's
   `capability.assets[*].dest_path`).
2. `~/.claude.json` whole file (always — paths inside change).
3. `~/.claude/settings.json` whole file (always — hook entries change).
4. `~/.claude/settings.local.json` (if it exists — user overrides may
   shadow our writes).
5. **Parent-directory listing** for every `~/bin/<x>` write target — used
   for orphan detection on rollback (so a script we created gets removed,
   not just overwritten back to nothing).

**Rollback tarball layout:**

```
rollback.tar.gz
├── before/
│   ├── home/.claude.json         (whole file, or .missing marker if absent)
│   ├── home/.claude/settings.json
│   ├── home/.claude/settings.local.json (optional)
│   ├── home/.claude/skills/<each-affected>.md
│   ├── home/.claude/hooks/<each-affected>/
│   ├── home/.claude/rules/<each-affected>.md
│   └── home/bin/<each-affected>
└── manifest-of-bundle-writes.json   # so rollback.sh knows what to remove
```

`rollback.sh` reads `manifest-of-bundle-writes.json`, restores `before/`,
and removes any path the bundle wrote that wasn't in `before/` (orphans).

---

## 6. Smoke-test prompts

**Question:** Exact text the receiving Claude self-asks post-install.

**Decision:** Three checks; pass all three.

1. **Asset presence + permissions** (deterministic, no LLM):
   for each `manifest.capability.assets[*]` ensure file exists at
   `dest_path`, sha256 matches, and `mode_bits` is set.
2. **Capability-specific functional check** (declared per bundle in
   the manifest; no fixed text). For cascade-memory, the manifest
   declares: `session-search foo` should return exit 0 and either
   "no matches" or empty stdout (correct behavior on an empty corpus).
3. **Self-interrogation** (LLM): the receiving Claude is asked
   *exactly* this prompt (chosen from 3 candidates):

   > **"List the new skills, hooks, and rules currently loaded in your
   > config that are part of the {capability_name} capability. For each,
   > say what it does in 1 sentence."**

   The agent's response is parsed for the expected asset names from
   `manifest.capability.assets[*].dest_path`. Drift (missing names) is
   flagged but not auto-rollback.

**Why this prompt:** it does not lead the agent (open-ended "list ...")
and forces it to reason from the actually-loaded config — not from
training-time knowledge of any particular skill. The two rejected
candidates were:

- ❌ "Do you have session-search installed?" — leading; allows confabulation.
- ❌ "What memory tools do you have?" — too vague; cascade-memory ≠
  "memory tools" (Graphiti is also memory but isn't in this bundle).

---

## Cross-references

- Implementation tasks: `tasks.md` T026 (compose), T028 (briefing render),
  T029 (preview), T030 (rollback), T033 (ingest), T034 (smoke test).
- Schema contract: `contracts/manifest.schema.json`.
- Briefing template: `contracts/briefing.template.md`.
- Test enforcement: `tests/unit/test_risk_tagging.py`,
  `tests/unit/test_secret_redaction.py`,
  `tests/contract/test_manifest_schema.py`,
  `tests/contract/test_briefing_sections.py`,
  `tests/integration/test_capability_roundtrip.py` (skipped until Wave 6).
