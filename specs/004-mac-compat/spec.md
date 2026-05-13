# Feature Specification: AgentBridge v1.1 — macOS Compatibility

**Feature Branch**: `004-mac-compat`
**Created**: 2026-05-05
**Status**: Draft
**Input**: User description: "AgentBridge v1.1 macOS portability — Linux ↔ macOS bundle round-trip with mode_bits anchoring fix, rollback.sh HOME re-stamp, and Linux nvm → macOS Homebrew path-rewrite. Per PRD agentbridge_mac_compat_2026-05-05.md."
**Source PRD**: `~/dev/prd/scratch/agentbridge_mac_compat_2026-05-05.md`
**Predecessor**: feature 003 (`AgentBridge MVP`) shipped via merge `74ccac1` to master 2026-05-05.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Linux source machine bundles a capability for a Mac destination (Priority: P1) — SHIP GATE

A user has a working capability on Linux Source Machine — e.g., `cascade-memory` composed of `~/bin/session-search` + 7 dependent skills + 2 hooks + 5 rule files. The user wants the same capability working on a Mac Destination Machine (Apple Silicon or Intel). The user invokes `ab compose --capability cascade-memory` on Linux as before, and expects to drop the resulting bundle on the Mac and run `ab ingest` cleanly — install succeeds, smoke test passes, and `bash rollback.sh` restores the Mac to its pre-install state if anything goes wrong.

Today (post-003), the install path largely works because `Path.home()` resolves correctly on both platforms. But three concrete failures land silently or noisily on the Mac: (1) `_safe_mode_bits` over-fires on macOS-typical paths and chmods JSON files to `0o755`; (2) `rollback.sh` aborts with "manifest home does not match current HOME" because the bundled manifest's `home` field is `/home/user` and the Mac's `$HOME` is `/Users/user`; (3) MCP server entries that reference Linux nvm paths (`/home/u/.nvm/versions/node/v20/bin/npx`) get rewritten to `/Users/u/.nvm/...` which doesn't exist on Apple Silicon (Homebrew lives at `/opt/homebrew/bin/npx`).

Story 1 is fixing all three so a Linux-sealed bundle round-trips cleanly on a fresh Mac sandbox HOME.

**Why this priority**: This is the v1.1 ship gate. It is the smallest possible scope that delivers the user's actual cross-platform need. Without it, Linux→Mac is "kind-of-works-but-rollback-breaks" — the safety net the constitution claims doesn't actually deploy on Mac, which makes the MVP's R12 H#4 hardening false on the cross-platform path.

**Independent Test**: On a fresh sandbox HOME at `/tmp/ab-mac-sandbox-$(date +%s)` mimicking macOS shape (`HOME=/Users/<test-user>` style), `ab compose --capability cascade-memory` from Linux source → bundle copied to sandbox → `ab ingest` succeeds with no chmod-corruption on `~/Library/...` paths → smoke test passes → `bash rollback.sh` succeeds and restores prior state with zero leftover artifacts.

**Acceptance Scenarios**:

1. **Given** a Linux-sealed cascade-memory bundle and a fresh sandbox HOME shaped like `/Users/<u>`, **When** `ab ingest <bundle>` runs, **Then** install succeeds with zero errors and zero unexpected chmod 0o755 on JSON files anywhere under the destination tree.
2. **Given** a successful install, **When** `bash rollback.sh` runs in the sandbox HOME context, **Then** rollback proceeds (does NOT abort with "manifest home does not match current HOME") and restores prior state with zero leftover artifacts.
3. **Given** a Linux-sealed bundle whose `~/.claude.json` mcpServers reference `/home/u/.nvm/versions/node/v20/bin/npx`, **When** ingested into a sandbox HOME marked as macOS Apple Silicon, **Then** the rewritten config uses bare `npx` (resolved via PATH) — NOT `/Users/u/.nvm/...` which would not exist.
4. **Given** an asset whose `dest_path` is `~/Library/Application Support/foo/bin/data.json`, **When** `_safe_mode_bits` runs, **Then** the resulting mode is `0o644` (or whatever the source mode_bits declared) — NOT `0o755` from substring-matching `/bin/`.

---

### User Story 2 — APFS case-insensitive filesystems do not silently merge assets (Priority: P2)

A user bundles a capability whose composer accidentally produces two assets with `dest_path` differing only in case (e.g., `~/.claude/skills/Foo.md` and `~/.claude/skills/foo.md`). On Linux ext4 these are different files; the existing duplicate-dest_path validator (R12 H#9) catches the bug at construction time only when paths are byte-identical. On macOS APFS (case-INSENSITIVE-PRESERVING by default) the two paths point at the same file — last-write-wins with no warning.

Story 2 makes the duplicate-dest_path validator case-fold-aware always, so the two-paths-same-file scenario is rejected at compose time on either platform.

**Why this priority**: This is silent data loss. Likelihood is low (composer rarely produces case-only-different paths today) but the blast radius is real — losing one of two paired assets without a warning is the kind of bug users discover months later when an installed capability mysteriously stops working.

**Independent Test**: Construct a `Capability` with two AssetEntry rows, both `dest_path` differing only in case. Validator must raise `ValueError` with a message naming both indices.

**Acceptance Scenarios**:

1. **Given** two AssetEntry rows with `dest_path="~/.claude/skills/Foo.md"` and `dest_path="~/.claude/skills/foo.md"`, **When** they are passed into a `Capability(...)` constructor, **Then** Pydantic validation raises `ValueError` mentioning "duplicate dest_path (case-insensitive)" and naming both array indices.
2. **Given** a Linux ingestion that succeeds with both files (because ext4 distinguishes them), **When** the same bundle is ingested on a Mac APFS sandbox, **Then** Mac install fails fast with the validator error (not silent overwrite).

---

### User Story 3 — Homebrew-installed binaries on Apple Silicon are discoverable and bundleable (Priority: P3)

A Mac user with Homebrew on Apple Silicon (`/opt/homebrew/bin/`) has installed `gh`, `jq`, `ripgrep` via Homebrew, and a custom skill in `~/.claude/skills/` references `gh`. When the user runs `ab compose --capability my-gh-skill`, today the composer looks in `~/bin/` and `~/.local/bin/` only — it doesn't find `gh` and either bundles the skill without its dependency declaration or fails to anchor.

Story 3 extends the default bin-dir search to include `/opt/homebrew/bin` and `/opt/homebrew/sbin` when running on macOS, so Homebrew-installed binaries are reachable.

**Why this priority**: Homebrew is the de-facto standard package manager on Mac. Without this, a Mac user authoring a capability has to manually `--add` every Homebrew binary, which is friction the Linux user doesn't face. P3 because it's a usability gap, not a correctness gap; capabilities don't fail silently, they just don't auto-discover.

**Independent Test**: On macOS, `script_discovery.discover_referenced_scripts(home=...)` finds a `gh` binary placed at `/opt/homebrew/bin/gh` when a fixture skill body contains `\`/opt/homebrew/bin/gh\` ` references.

**Acceptance Scenarios**:

1. **Given** `sys.platform == "darwin"`, **When** `script_discovery.DEFAULT_BIN_DIRS` is iterated, **Then** `/opt/homebrew/bin` and `/opt/homebrew/sbin` are present.
2. **Given** Linux (`sys.platform == "linux"`), **When** the same is iterated, **Then** Homebrew dirs are NOT present (avoids stat-overhead on dirs that don't exist).
3. **Given** a Mac fixture HOME with `/opt/homebrew/bin/gh` and a skill body strict-referencing `/opt/homebrew/bin/gh`, **When** compose runs, **Then** the bin script is included in the bundle as a COMPANIONS asset.

---

### Edge Cases

- **Mac without Homebrew installed**: `/opt/homebrew/bin/` does not exist. Default bin-dirs include it but `_iter_scannable_files` already skips non-existent roots — no change needed.
- **Apple Silicon vs Intel Mac**: Intel Macs have Homebrew at `/usr/local/bin/` (already in the system search). Apple Silicon has it at `/opt/homebrew/bin/`. Both must be searched on macOS; Linux searches neither (no harm) but only `/usr/local/bin/` is in the existing default.
- **APFS case-SENSITIVE volume**: A user can opt in to case-sensitive APFS at format time. The case-fold validator still works (case-fold over case-sensitive paths is a no-op for distinct paths).
- **Symlinked HOME on macOS**: macOS often symlinks `/var/folders/...` to user temp dirs and APFS firmlinks blur `/Users/<u>` ↔ `/System/Volumes/Data/Users/<u>`. The R12 H#6 fix (no `.resolve()` in snapshot) already covers this — extends to Mac without modification.
- **Mac without `python3`**: rollback.sh shells to `python3` for JSON parsing. Documented dep — bundle's BRIEFING.md must call this out as a destination prerequisite.
- **xattrs on macOS (`com.apple.quarantine`, Spotlight metadata)**: `cp -p` in rollback.sh does not preserve these. R12 H#5 wording softened — accepted limitation per PRD M#5.
- **Linux→Linux still works**: All v1.0 same-platform round-trips must continue passing. The existing 92-test suite is the regression gate.
- **A bundle sealed on Mac and ingested on Linux**: Symmetric to Story 1 but reversed direction. Manifest's `home` is now `/Users/u`; rollback's HOME re-stamp must work in this direction too.
- **Bundle with NO mcpServers entries**: Path-rewrite is a no-op; not testing infrastructure should not regress.
- **mcpServers entry that has `command: "node"` (already bare)**: Path-rewrite leaves it alone; no double-rewrite.
- **macOS user with case-insensitive APFS deliberately bundling two case-different paths** (rare but legal on a case-sensitive HFS+ source): the validator rejects, user must rename one before re-bundling. Documented behavior, not a silent failure.

---

## Requirements *(mandatory)*

### Functional Requirements

**Cross-platform install correctness**

- **FR-001**: `_safe_mode_bits` MUST anchor against path SEGMENTS, not substrings. Specifically: only treat as "bin script" if the asset's destination path matches one of `~/bin/`, `~/.local/bin/`, `/opt/homebrew/bin/`, `/opt/homebrew/sbin/`, `/usr/local/bin/` (using `Path(dest_path).parts` to walk segments). Only treat as "hook script" if the destination path contains `.claude/hooks/` as a directory segment, not as a substring.
- **FR-002**: At ingest time, the receiver's `Path.home()` MUST be substituted into the manifest's `home` field BEFORE invoking `rollback.snapshot()`. The original source-side `home` value is preserved in a new `manifest.source_machine_home` field (additive, schema_version remains 1.0.0 — no breaking change).
- **FR-003**: `rollback.sh` MUST NOT abort when the manifest's `home` differs from the receiver's `$HOME` IF the receiver-side ingest already re-stamped it (FR-002). The privileged-path refusal (`/`, `/etc`, `/root`, `/sys`, `/proc`) MUST remain as the security guard.
- **FR-004**: `rewrite_mcp_servers_for_target_home` MUST accept an optional `target_platform: Literal["linux", "darwin"]` argument. When `target_platform == "darwin"` and a string value contains `~/.nvm/`, the function MUST emit a runtime-lookup form (`command: "<basename>"`, args without absolute paths) instead of literal-path substitution. This forces the Mac receiver to resolve `npx`/`node` via PATH (where Homebrew has placed them).
- **FR-005**: The duplicate-dest_path validator on `Capability` MUST compare paths case-insensitively (`dest_path.casefold()`) on every platform. Costs nothing on case-sensitive Linux ext4 but prevents silent data loss on macOS APFS.

**Cross-platform discovery**

- **FR-006**: `script_discovery.DEFAULT_BIN_DIRS` MUST include `/opt/homebrew/bin` and `/opt/homebrew/sbin` when `sys.platform == "darwin"`. Linux must not include these.

**Backward compatibility**

- **FR-007**: All 92 tests from feature 003 MUST continue to pass after these changes (constitution R5 + R11). Linux→Linux round-trip is unchanged.
- **FR-008**: The `manifest.source_machine_home` field is OPTIONAL on read for backward compat with v1.0 bundles (which don't have it). If missing, the receiver-side ingest treats `manifest.home` as authoritative as before — a v1.0 bundle on a same-OS receiver still works.

**Constitution amendment**

- **FR-009**: `.specify/memory/constitution.md` R3 text MUST be updated from "Linux only (For Now). Target Linux + WSL only" to "Linux + WSL + macOS. Target Linux + WSL + macOS Intel + macOS Apple Silicon."
- **FR-010**: `README.md` Installation section MUST include macOS-specific notes covering Homebrew Python install for the rollback shebang, `/opt/homebrew/bin` PATH considerations on Apple Silicon, and the documented `python3` dependency for `rollback.sh`.

### Out of Scope (deferred to follow-up PRDs or accepted as documented limitations)

- xattrs preservation in rollback (PRD M#5) — DOCUMENTED as accepted limitation in BRIEFING.md template; `cp -p` semantics noted.
- GNU vs PAX tar format (PRD L#9) — leave as-is; macOS bsdtar handles GNU format for current path lengths.
- `mktemp -d` flag drift (PRD L#10) — bare `-d` works on both BSD and GNU; document only.
- `python3` hard dependency (PRD L#8) — DOCUMENTED in BRIEFING.md; accepted.
- macOS-only test fixtures parametrized to `/Users/...` (PRD M#7) — TESTED in this feature via Story 1 acceptance scenarios.
- Native macOS CI runner — out of scope for v1.1; manual Mac verification at cutover. Real-Mac integration test added but skipped unless `sys.platform == "darwin"`.

### Key Entities

- **Source-machine-aware manifest**: New optional `ManifestModel.source_machine_home` field captures the absolute path of the source's `Path.home()` at seal time, separate from `manifest.home` which can be re-stamped at ingest. Drives FR-002 and FR-003.
- **Target-platform hint at ingest**: New optional argument to `rewrite_mcp_servers_for_target_home` that triggers the runtime-lookup rewrite for nvm-style paths when target is macOS. Drives FR-004.
- **Path-segment classifier**: New helper inside `_safe_mode_bits` (or a small new module `bridge/path_classify.py`) that classifies a `dest_path` string into one of `{bin, hook, claude_data, other}` by inspecting `Path(dest_path).parts`. Drives FR-001.
- **Case-folded dest_path key**: Normalized form used by the duplicate-dest_path validator. Drives FR-005.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001 (SHIP GATE)**: On a fresh sandbox HOME shaped like `/Users/<u>` at `/tmp/ab-mac-sandbox-$(date +%s)`, the cascade-memory capability round-trips end-to-end. Linux-sealed bundle ingests cleanly, smoke test passes, `bash rollback.sh` succeeds and restores prior state with zero leftover artifacts (verified by file-tree diff).
- **SC-002**: Path-segment classifier returns `kind=other` (not `bin`) for `dest_path = ~/Library/Application Support/foo/bin/data.json`. Verified by parametrized test in `tests/integration/test_r12_fixes.py::test_h7_safe_mode_bits_clamps`.
- **SC-003**: `rewrite_mcp_servers_for_target_home(..., target_platform="darwin")` over a fixture mcpServers entry with `/home/u/.nvm/versions/node/v20/bin/npx` produces a config with bare `command="npx"` (no absolute path).
- **SC-004**: Constructing a `Capability` with two AssetEntry rows whose `dest_path` differ only in case raises `ValueError` mentioning "duplicate dest_path (case-insensitive)". Verified on Linux (where the underlying filesystem distinguishes them) — proves the validator runs unconditionally.
- **SC-005**: On macOS, `script_discovery.discover_referenced_scripts(home=...)` finds a fixture binary at `/opt/homebrew/bin/gh` when a skill body strict-references it. Test skipped unless `sys.platform == "darwin"`.
- **SC-006**: All 92 tests from feature 003 continue to pass. Total test count rises to ≥ 100.
- **SC-007**: Constitution R3 reads "Linux + WSL + macOS" in the merged tree; README.md installation section has macOS-specific notes.
- **SC-008**: A v1.0 bundle (sealed pre-FR-002) ingests cleanly on a v1.1 receiver — backward compatibility verified with a stored fixture bundle in `tests/fixtures/v1.0_bundle/`.
