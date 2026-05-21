# Feature Specification: AgentBridge v1.2 — Out-of-Tree Dependencies

**Feature Branch**: `006-out-of-tree-deps`
**Created**: 2026-05-21
**Status**: Draft (lightweight — parallel to dev, not waterfall)
**Input**: User insight (2026-05-21 SIO bundle session): "The bundle has the 207 skills but not the SIO Python package or the 5 settings.json hooks. We need to instruct the receiving agent how to install what's needed, and that pattern should be agent-agnostic."
**Predecessor**: feature 003 (`AgentBridge MVP`) + manual prototype shipped 2026-05-21 in `/tmp/bundle-sio/` (PREREQUISITES.md, install_prereqs.sh, settings_patch.json).

## Problem

`ab compose --capability <name>` today walks the dependency graph inside `~/.claude/` (skills → bin scripts → hook scripts → rules). It produces a sealed bundle the receiving harness can install with `ab ingest`. This works perfectly for in-tree capabilities like `cascade-memory` (everything lives under `~/.claude/` and `~/bin/`).

It fails silently for capabilities with **out-of-tree dependencies**. Three concrete classes:

1. **Third-party Python (or other) package** installed via `pip` / `npm` / `cargo` / OS package manager. Example: SIO's `self-improving-organism` package lives at `~/dev/projects/SIO/` (or wherever the destination user clones it) and is `pip install -e`'d into a Python environment outside `~/.claude/`. The CLI shim lands in that environment's `bin/`, not `~/bin/`.

2. **Harness settings entries** that aren't standalone hook scripts. Example: SIO registers 5 hooks as JSON entries in `~/.claude/settings.json`, each invoking `python -m sio.adapters.claude_code.hooks.<event>`. The hook scripts don't exist as files — they're Python modules inside the installed package.

3. **System tools** the capability depends on (`git`, `jq`, `gh`, a specific node version). Today's `capability.dependencies` field is a single string and isn't surfaced to the receiving agent in actionable form.

The 2026-05-21 SIO bundle proved this with a hand-built workaround: PREREQUISITES.md + install_prereqs.sh + settings_patch.json shipped alongside the standard AgentBridge artifacts (BRIEFING.md + manifest.json + bundle/ + rollback.tar.gz). The pattern works. But it was hand-written. This spec generalizes it.

## User Scenarios & Testing

### User Story 1 — Capability with a Python package source dep (Priority: P1) — SHIP GATE

A user has a working SIO install on their source machine: `~/dev/projects/SIO/` (a git clone, `pip install -e .`'d into their Python env) + `~/.claude/skills/sio*` (207 adapter files) + 5 hook entries in `~/.claude/settings.json`. They want a receiving agent on a fresh destination machine to install everything needed and end up with a working `/sio-scan` invocation.

The user runs `ab compose --capability sio` on the source. The bundle now includes a declared `dependencies.sources` block in `manifest.json` (one entry: `kind=git_python_package`, repo URL, package name, min Python version) AND a declared `dependencies.settings_patch` block (the 5 hook entries with `${SIO_PYTHON}` placeholder). `ab compose` renders PREREQUISITES.md + install_prereqs.sh + settings_patch.json from those declarations — no hand-writing.

On the destination, the receiving agent reads BRIEFING.md → sees a new **§0 Prerequisites** → reads PREREQUISITES.md → assesses the destination system (git? Python ≥3.11? PATH? user wants step-by-step or atomic?) → either walks the user through the steps (Path A) or runs `bash install_prereqs.sh` atomically (Path B) → verifies `sio status` returns clean → merges the rendered settings_patch into the harness settings file → THEN ingests the 207 assets → restarts the session.

**Why this priority**: It's the proof-by-example. SIO is the smallest non-trivial real capability with all three out-of-tree dep classes. Shipping this proves the pattern works end-to-end and unblocks every future capability with similar shape (cascade-memory has none of these gaps; SIO has all three).

**Independent Test**: On a fresh sandbox HOME with no SIO installed, no SIO skills present, no `sio` on PATH, no SIO hook entries in settings.json — drop `/tmp/bundle-sio/` (auto-generated, not hand-edited) and follow BRIEFING.md → end state: `sio status` returns a non-error response AND the 207 skill assets exist at declared dest_paths AND the 5 hook entries are merged into `~/.claude/settings.json` AND a fresh harness session captures telemetry to `~/.sio/<platform>/behavior_invocations.db`.

**Acceptance Scenarios**:

1. **A**: `ab compose --capability sio` on a source machine with SIO declared as out-of-tree dependency → bundle contains `PREREQUISITES.md`, `install_prereqs.sh`, `settings_patch.json` (rendered from manifest declarations, not hand-written) → `manifest.json.capability.dependencies` has structured `sources` + `settings_patch` blocks.
2. **B**: Receiving agent reads `BRIEFING.md §0` → enumerates declared deps → surfaces them to user → user opts for Path A (step-by-step) → agent runs each step with confirmation → end state matches Independent Test.
3. **C**: Receiving agent under Path B runs `install_prereqs.sh` atomically → all steps succeed → settings_patch.rendered.json materialized → agent merges into settings.json → ingest proceeds → smoke test passes.
4. **D**: install_prereqs.sh fails midway (e.g., no Python ≥3.11) → exits non-zero → receiving agent falls back to Path A from failure point → reports to user.
5. **E**: Rollback (`bash rollback.sh`) restores ALL writes — including the settings.json merge AND the SIO Python package install (caveat: pip-installed packages are not auto-uninstalled; rollback documents the manual `pip uninstall` step instead of executing it).

### User Story 2 — Capability with system-tool deps only (Priority: P2)

A user composes a capability that requires `gh` (GitHub CLI) and `jq` to be present. No Python package, no settings entries — just two system tools. `ab compose` declares them in `manifest.dependencies.system_tools` with `min_version` constraints; the renderer generates a PREREQUISITES.md that lists them with install hints per common platform (`brew install gh jq` / `apt-get install gh jq` / etc.) and an install_prereqs.sh that checks `command -v gh && command -v jq` and reports.

**Independent Test**: On a sandbox without `gh` installed, `bash install_prereqs.sh` exits non-zero with the install hint; receiving agent surfaces it; once installed, re-run succeeds; ingest proceeds.

### User Story 3 — Capability with no out-of-tree deps (Priority: P0 — must not regress)

A user composes `cascade-memory` (in-tree only). `manifest.dependencies` is empty / omitted. NO PREREQUISITES.md, install_prereqs.sh, or settings_patch.json is generated. BRIEFING.md §0 says "no out-of-tree dependencies declared." Existing v1.1 behavior is preserved exactly.

## The convention (canonical artifacts)

When `manifest.capability.dependencies` is non-empty, the sealed bundle MUST contain:

| File | Generator | Role |
|---|---|---|
| `PREREQUISITES.md` | Auto-rendered from `manifest.dependencies` | Canonical instructions for the receiving agent. Documents declared deps + the Path A (assess + step-by-step) vs Path B (atomic install) choice. |
| `install_prereqs.sh` | Auto-rendered from `manifest.dependencies` | Reference implementation in script form. NOT the canonical installer — a playbook the receiving agent uses as a guide OR runs atomically based on assessment. |
| `settings_patch.json` | Auto-rendered IF `dependencies.settings_patch` is declared | Templated JSON delta with `${VAR}` placeholders the receiving agent resolves (e.g., `${SIO_PYTHON}` from the pip-install step) and merges into harness settings. |

The receiving agent's protocol when these files are present:

1. Read `BRIEFING.md §0 Prerequisites` (new mandatory section).
2. Read `PREREQUISITES.md` in full.
3. **Assess** destination: required tools, Python version, PATH, network access, repo SSH/HTTPS auth, user's preferred verbosity.
4. **Surface the choice to the user**: "Two paths — A: step-by-step (default, more visibility) or B: atomic via install_prereqs.sh. I recommend [X] because [assessment]. Which?"
5. Execute chosen path. If Path B fails non-zero at any step, fall back to Path A from failure point.
6. Verify per `PREREQUISITES.md` "Verification" section.
7. Only after verification passes, proceed to ingest the bundle's asset tree.

### User Story 4 — Capability that needs API keys / secrets (Priority: P1 — bundled with Story 1)

A user composes a capability that requires API keys to function (e.g., SIO needs `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` for DSPy optimization; a future capability might need a service account JSON path). These secrets **cannot be bundled** — the secret scanner correctly refuses, and bundling them would be a security failure regardless. But the capability still needs them at runtime.

Today there's no declared way for the receiving agent to know:
- That `ANTHROPIC_API_KEY` is needed (vs. SIO running in degraded read-only mode)
- Whether it should be an env var, an entry in `~/.sio/config.toml`, or something else
- What to do if the destination user doesn't have one
- Whether the destination's existing env var should be reused or re-prompted

The fix: declare required secrets in `manifest.dependencies.secrets_required` with structured fields (name, purpose, target form, fallback behavior). The receiving agent surfaces them to the user, prompts for missing values, places them in the declared target, and confirms before proceeding.

**Why bundled with Story 1**: SIO has both — Python package + settings hooks + API keys. The user-facing flow is one continuous "install + configure" experience; splitting it across multiple ship gates would produce a half-broken intermediate state.

**Independent Test**: On a fresh sandbox with no `ANTHROPIC_API_KEY` set, the receiving agent following PREREQUISITES.md detects the missing secret, prompts the user once with the documented purpose, accepts the value, persists it in the declared target form (env var via shell rc, or config file), and verifies. The secret VALUE never appears in any committed file, log, or telemetry. End state: SIO operations that require the secret succeed; the secret is not in the bundle, the manifest, the rendered scripts, or the receiver's session transcript.

**Acceptance Scenarios**:

1. **A**: `manifest.dependencies.secrets_required` is non-empty → BRIEFING §0 surfaces a Red-tier "Secrets required" callout → PREREQUISITES.md has a dedicated "Secrets" section listing each required secret with purpose + target form + fallback.
2. **B**: install_prereqs.sh detects missing required secrets and EXITS NON-ZERO with a precise error ("ANTHROPIC_API_KEY not set in environment; required for SIO optimization step. Set it and re-run, or run Path A so the agent can prompt you.") — it does NOT prompt itself (script is non-interactive by design).
3. **C**: Receiving agent on Path A handles the prompt — asks user, accepts the value via secure input (no echo, no transcript leak), writes to the declared target, never logs the value.
4. **D**: Secret value never appears in: BRIEFING.md, manifest.json, settings_patch.json (or its rendered form), install_prereqs.sh, install_prereqs.sh's stdout, rollback.tar.gz, confirmations.log, or any other bundle artifact. Verifiable via grep + secret scanner.
5. **E**: If the destination already has the secret set (env var present, config file populated), the receiving agent detects + offers to reuse vs. re-prompt — does NOT silently overwrite.

## Manifest schema extension (Pydantic)

```python
class GitSourceDep(BaseModel):
    kind: Literal["git_python_package", "git_node_package", "git_other"]
    repo: HttpUrl | str  # also accept git@host:path form
    package_name: str    # for verification (`import <name>`)
    min_python: str | None = None
    install_target_var: str | None = None  # e.g. SIO_PYTHON — exported for settings_patch

class SystemToolDep(BaseModel):
    kind: Literal["system_tool"]
    binary: str
    min_version: str | None = None
    install_hints: dict[str, str] | None = None  # {"darwin": "brew install X", "linux-apt": "apt-get install X", ...}

class SettingsPatchDep(BaseModel):
    kind: Literal["settings_patch"]
    file: str                     # bundle-relative path, e.g. "settings_patch.json"
    merge_into: Literal["harness_settings"]  # ~/.claude/settings.json on Claude Code
    merge_strategy: Literal["append_per_event", "deep_merge"]

class SecretTargetForm(BaseModel):
    """Where the secret lives once provided. Receiving agent honors this."""
    kind: Literal["env_var", "config_file_kv", "config_file_toml_path", "external"]
    # env_var: target is the env var named in `name`. Receiver writes to user's
    #   shell rc OR a sourced file the harness reads at session start.
    # config_file_kv: target is a `KEY=value` line in a file (path in `path` field).
    # config_file_toml_path: target is a dotted TOML path (e.g. `[providers].anthropic_key`).
    # external: secret lives in an external secret manager (1Password, AWS SM, vault).
    #   Receiver only verifies it's reachable; never reads the value.
    path: str | None = None  # for config_file_* kinds
    toml_path: str | None = None  # for config_file_toml_path

class SecretRequirement(BaseModel):
    """One declared secret the capability needs at runtime."""
    name: str  # canonical env var name OR config key (e.g., ANTHROPIC_API_KEY)
    purpose: str  # one-line — surfaced to user in the Red-tier prompt
    target: SecretTargetForm
    required: bool = True  # False = capability runs in degraded mode without it
    fallback_behavior: str | None = None  # human prose: what the capability does if missing
    verification: str | None = None  # optional shell snippet that exits 0 iff secret works

class CapabilityDependencies(BaseModel):
    sources: list[GitSourceDep] = []
    system_tools: list[SystemToolDep] = []
    settings_patch: SettingsPatchDep | None = None
    secrets_required: list[SecretRequirement] = []
    # `system_tools` and `sources` order matters — emitted in same order in PREREQUISITES.md.
    # `secrets_required` is surfaced LAST in PREREQUISITES.md but FIRST in BRIEFING §0
    # (Red-tier visibility), and the receiving agent must satisfy them BEFORE running
    # the rest of install_prereqs.sh.

# Add to existing Capability model:
class Capability(BaseModel):
    name: str
    description: str
    assets: list[AssetEntry]
    dependencies: CapabilityDependencies = CapabilityDependencies()
    # ... existing fields ...
```

## BRIEFING.md schema extension

Add **§0 — Prerequisites** as a new MANDATORY section (FR-007 extension). Position: between "Dear Receiving Claude" intro and §1 Identity.

§0 content (rendered from manifest):

- If `dependencies` is empty: one line — "No out-of-tree dependencies declared. Proceed directly to §1."
- Otherwise: a table summarizing the declared deps + a pointer to PREREQUISITES.md + the explicit Path A vs Path B framing + a STOP warning ("do not ingest assets until prerequisites verified").

## Renderer

New module: `agent_transfer/bridge/prereqs.py` with two public functions:

```python
def render_prerequisites_md(deps: CapabilityDependencies, capability_name: str) -> str: ...
def render_install_prereqs_sh(deps: CapabilityDependencies, capability_name: str) -> str: ...
```

Renderers consume the typed schema and emit the documented file shapes. Templates live in `agent_transfer/templates/prereqs/` so the prose is editable without code change.

Hook into `ab compose`: after the existing manifest/briefing/asset-tree write pass, if `manifest.capability.dependencies` is non-empty, call the two renderers + (if settings_patch declared) copy the user-supplied template into the bundle root.

## Source-side authoring (how the user declares deps)

Two options, both supported:

1. **`--dep` flag on `ab compose`** (repeatable): `ab compose --capability sio --dep 'git_python_package:repo=https://github.com/gyasis/SIO,name=self-improving-organism,min_python=3.11,export=SIO_PYTHON' --dep 'settings_patch:file=./settings_patch.template.json'`
2. **`.agentbridge.yaml`** sidecar in the source repo (auto-detected): a YAML file declaring the same blocks. Pre-empted by `--dep` flags.

User Story 1's SIO test exercises both (with the YAML as ground truth).

## What this spec does NOT do (out-of-scope)

- Cross-language package managers other than pip/npm/cargo (rust/go/system pkg mgrs covered as `system_tool` only).
- Automatic uninstall on rollback for pip/npm/cargo — rollback documents the manual step, doesn't execute it (different risk class).
- PyPI / private-index installs (covered by `git_python_package` for now; PyPI variant is a v1.3 extension).
- Cross-harness adapter discovery (knowing whether `sio.adapters.claude_code.hooks.*` exists on Goose / Letta / OpenCode) — receiving-agent responsibility, documented in PREREQUISITES.md failure modes table.

## Non-goals worth surfacing

- This is NOT a package manager. AgentBridge does not vendor third-party code; it instructs the receiving agent how to fetch + install it.
- This is NOT a sandbox. The receiving agent + destination user are trusted to run the script or walk the steps. Red-tier confirmation per existing 003 conventions still applies.

## Risk

| Risk | Mitigation |
|---|---|
| Receiving agent runs install_prereqs.sh blindly without assessment | PREREQUISITES.md "Two paths" section is the primary read; script header explicitly says "NOT the canonical installer"; BRIEFING §0 surfaces the choice to the user. |
| Rendered install script breaks on an unusual destination shell | Script targets `#!/usr/bin/env bash` + `set -euo pipefail`; failure modes table in PREREQUISITES.md covers common breaks. |
| User declares wrong package_name / repo URL → install silently installs wrong code | Verification step in PREREQUISITES.md asserts `import <package_name>` succeeds AND `<binary> --version` matches the declared min. Mismatch is a verification fail, not a silent pass. |
| Settings patch merge clobbers existing user hooks | `merge_strategy: append_per_event` (default) is purely additive. `deep_merge` is opt-in and documented. Pre-merge rollback snapshot already covers settings.json (existing FR-016). |
| Secret in `settings_patch.json` template (e.g., embedded API key) | Existing seal-time + per-asset secret scan covers it. The 2026-05-21 scanner-fix (commit 140ad77) is the prerequisite for this spec — settings patch templates would have tripped the old false-positive class. |
| Required secret (API key) declared but not provided on destination | install_prereqs.sh exits non-zero with precise error; receiving agent on Path A prompts user via secure-input flow; never echoes value to transcript/log/file other than the declared `target`. If user declines to provide, capability is marked installed-but-degraded with the declared `fallback_behavior` surfaced. |
| Receiving agent leaks secret value into session transcript while installing | Secrets section of PREREQUISITES.md mandates: agent MUST NOT log, echo, or include the secret value in any response after the user provides it. Only the *name* + *target form* may appear in agent output. Secret-scan on the post-install transcript (separate verification step) confirms no leak. |
| User already has the secret set on destination, agent re-prompts and clobbers | Story 4 Scenario E mandates: agent detects existing value at the declared target, offers reuse vs. re-prompt, never silent-overwrites. |

## Acceptance Criteria (SC)

- **SC-001**: `ab compose --capability sio` (with deps declared) produces all standard AgentBridge artifacts PLUS PREREQUISITES.md + install_prereqs.sh + settings_patch.json, with no hand-editing.
- **SC-002**: `ab compose --capability cascade-memory` (no deps declared) produces the standard artifacts only — NO PREREQUISITES.md / install_prereqs.sh / settings_patch.json. Existing v1.1 behavior preserved.
- **SC-003**: Receiving agent following Path A on the SIO bundle in a fresh sandbox ends with `sio status` returning clean.
- **SC-004**: Receiving agent following Path B (atomic) on the same bundle achieves the same end state in fewer turns.
- **SC-005**: `install_prereqs.sh` rendered from manifest is byte-for-byte equivalent to the hand-written 2026-05-21 prototype (modulo timestamps + interpreter-path resolution). Validation: diff the two.
- **SC-006**: Existing secret-scan tests (35/35 in `test_secret_redaction.py`) continue to pass with deps declared.
- **SC-007**: `BRIEFING.md §0` renders correctly for both deps-present and deps-empty cases; existing `tests/contract/test_briefing_sections.py` extended with §0 assertion.
- **SC-008**: With `secrets_required` declared, no rendered artifact (PREREQUISITES.md, install_prereqs.sh, settings_patch.json, BRIEFING.md, manifest.json) contains a secret VALUE — only the secret NAME + purpose + target form. Verifiable by grep + secret scanner pass against the sealed bundle.
- **SC-009**: install_prereqs.sh with declared `secrets_required` exits non-zero with a precise error pointing the user at the missing secret name; it does NOT prompt interactively (non-interactive by design — interactive prompts are the receiving agent's job, Story 4 Scenario C).

## Cross-references

- Hand-written prototype: `/tmp/bundle-sio/{PREREQUISITES.md, install_prereqs.sh, settings_patch.json}` (2026-05-21 — destroy on bundle-dir cleanup; this spec replaces it).
- Scanner-fix dependency: commit `140ad77` (eliminates the false-positive class that would have caught settings_patch templates).
- Predecessor spec: `specs/003-agentbridge-mvp/spec.md` (FR-007 mandatory briefing sections).
- Related convention pattern: `discoverability/` in repo root (consumer-side wire-ups for `agent-transfer` itself).

## Open questions (deliberate — for the dev pass to resolve)

1. Should `dependencies.sources[*].install_command` be overridable? Default is `pip install -e <clone>` for `git_python_package`; some users may need `pip install <clone>[extra]` or `uv pip install -e .`. Probably yes; add as optional field.
2. PREREQUISITES.md emits per-OS install hints for system tools — do we ship a built-in dict, or require user-supplied? Probably built-in for the common ones (gh, jq, git), user-supplied for the rest.
3. Should the receiving agent auto-detect `~/.claude/settings.json` vs `~/.claude/settings.local.json` for the merge target? Today the patch declares `merge_into: harness_settings` abstractly — the receiver resolves. Probably yes; document the resolution rule in PREREQUISITES.md.

These are intentionally left for the implementation pass to answer with code, not pinned in spec.
