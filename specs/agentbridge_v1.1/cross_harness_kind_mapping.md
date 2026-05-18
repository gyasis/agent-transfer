# AgentBridge v1.1 — Cross-Harness `kind` Mapping

**Status:** STUB. Rows below are placeholders. Each harness column is
TBD until that harness's maintainer confirms the mapping.

This document is the authoritative table for how each `AssetEntry.kind`
value (declared in `agent_transfer/bridge/models.py:AssetKind`) lands on
a destination harness. It is referenced by the BRIEFING.md "§8 Risk
Mapping" appendix, which renders a copy of this table inline in every
v1.1 bundle.

## Mapping table

| `kind`     | Claude Code                                | OpenClaude | OpenClaw | ZeroClaw | PromptChain |
|------------|--------------------------------------------|------------|----------|----------|-------------|
| skill      | `~/.claude/skills/<x>.md`                  | TBD        | TBD      | TBD      | TBD         |
| rule       | `~/.claude/rules/<domain>/<x>.md`          | TBD        | TBD      | TBD      | TBD         |
| hook       | `~/.claude/hooks/<group>/<event>.sh`       | TBD        | TBD      | TBD      | TBD         |
| bin        | `~/bin/<x>` or `~/.local/bin/<x>` (exec)   | TBD        | TBD      | TBD      | TBD         |
| capability | composite — see manifest `capability.assets` | TBD      | TBD      | TBD      | TBD         |

## Per-kind semantics (harness-neutral)

- **skill** — A self-contained markdown playbook the agent reads at
  decision time. Typically frontmatter + body. Has a `description:`
  field used as the bundle-wide description fallback.
- **rule** — An always-on behavioral constraint or tool-specific
  guidance, surfaced via the harness's instruction-injection mechanism
  rather than retrieved on demand.
- **hook** — A lifecycle handler (pre-tool-use, post-commit, session-
  end, etc.) that fires on harness events. Almost always `kind="hook"`
  carries `risk="red"` because hooks observe + can block tool calls.
- **bin** — An executable on PATH that the agent invokes via the shell
  tool. Risk `red` by default; `mode_bits` must survive ingest.
- **capability** — A composite glue artifact (the CLAUDE.md fragment,
  a settings.json fragment, a capability registry YAML). Receivers
  should treat as merge-or-append, never overwrite.

## Decision rule for "kind=other"

The composer is FORBIDDEN from emitting `kind="other"` — the v1.1
`AssetEntry` model validator rejects it at seal time. If you see a
bundle with `kind="other"` in the manifest, it was hand-edited; treat
as untrusted.

## How to fill in a harness column

For each row, the harness owner should answer:

1. **What is the canonical destination path** for an asset of this
   `kind` in this harness?
2. **What is the install action** (copy, symlink, register-in-config)?
3. **What is the harness-native risk class** that maps to v1.1's
   green / yellow / red? (Hooks usually map to "red — requires
   capability grant"; skills to "green — automatic".)
4. **What does the harness do if `kind` is unrecognized**? The
   recommended default is "inert — surface to user via `behavior_md`."

Submit a PR adding the populated rows. The BRIEFING.md template
imports this table verbatim, so changes here flow to every bundle.

## Open questions

- Should we add a `harness_min_version` field to `capability` in
  v1.2 so producers can hard-require a minimum harness for assets
  that don't gracefully degrade? (PRD §5 Q6 — deferred.)
- Should we add a `kind_extensions` array on `capability` so
  harnesses can declare additional asset shapes (e.g. PromptChain
  "chain", OpenClaw "tool-binding") without forcing them through
  `kind="capability"`? (PRD §5 Q7 — deferred to v1.2.)
