# Feature Spec: 001 — Platform-Agnostic Agent Transfer

**Source PRD:** `prd/agent-transfer-v2-platform-agnostic.md`
**Branch:** `001-platform-agnostic-transfer`
**Status:** Specified
**Author:** Gyasi Sutton
**Date:** 2026-02-24

---

## Summary

Evolve `agent-transfer` from a Claude Code-only tool into a platform-agnostic library that transfers AI agent definitions between Claude Code, OpenAI Codex CLI, Gemini CLI, Goose, and OpenCode — using an Intermediate Representation (IR) for cross-platform conversions while keeping same-platform transfers lossless.

---

## User Stories

### US-1: Cross-Platform Agent Conversion
> As a developer who uses both Claude Code and Goose, I want to convert my Claude Code agent into a Goose recipe so I can use the same agent logic on both platforms.

**Acceptance:**
- `agent-transfer convert my-agent --from claude-code --to goose` produces valid Goose YAML
- System prompt preserved, MCP configs preserved
- Hooks converted to recipe steps or instructional shims with warning
- Compatibility report shown before conversion

### US-2: Import from Another Platform
> As a Claude Code user, I want to import a Goose recipe into Claude Code so I can use a teammate's workflow.

**Acceptance:**
- `agent-transfer convert smart-commit --from goose --to claude-code` produces valid `.md` agent
- Recipe steps map to system prompt instructions
- MCP configs preserved, warnings for non-transferable features

### US-3: Platform Discovery
> As a developer, I want to see which platforms are installed on my system and their transfer compatibility.

**Acceptance:**
- `agent-transfer platforms` shows table with detection status
- `agent-transfer compat --from claude-code --to codex` shows feature compatibility

### US-4: Lossless Same-Platform Transfer (Existing Behavior)
> As a Claude Code user, I want to export/import agents between machines with zero loss.

**Acceptance:**
- Existing `export`/`import` work unchanged
- Byte-identical round-trip for Claude Code <-> Claude Code
- No regressions in any existing CLI command

### US-5: Bulk Multi-Platform Export
> As a developer, I want to export an agent to IR format for multi-target conversion.

**Acceptance:**
- `agent-transfer convert my-agent --from claude-code --to aim` produces IR YAML
- IR can then be converted to any target platform

### US-6: Security Fix
> As a user receiving archives, I need protection against malicious archives.

**Acceptance:**
- Path traversal (`../../etc/passwd`) rejected with clear error
- Symlink escapes rejected
- All `tar.extractall()` calls use safe extraction

---

## Technical Design

### Transfer Modes

| Scenario | IR Used? | Lossless? |
|----------|----------|-----------|
| Same platform, same machine | No | Yes, exact copy |
| Same platform, different machines | No | Yes, archive round-trip |
| Different platform, same machine | Yes | Best-effort + warnings |
| Different platform, different machines | Yes | Best-effort + warnings |

### Architecture

```
Same platform:    Source files  ──exact copy──>  Target files  (lossless)
Cross platform:   Source files  ──Ingestor──>  IR/AIM  ──Emitter──>  Target files
```

### Key Components

1. **Platform Abstraction Layer** (`platforms/`)
   - `BasePlatform` ABC: `detect()`, `find_agents()`, `find_skills()`
   - `PlatformRegistry`: plugin-based registration via entry_points
   - Platform implementations: claude_code, codex, gemini_cli, goose, opencode

2. **Intermediate Representation** (`ir/`)
   - `AIIntentManifest`: YAML-based IR with identity, capabilities, triggers, logic, environment, MCP configs
   - Shadow data (`platform_specific`) for round-trip fidelity
   - Canonical tool mapping registry

3. **Ingestors** (`ingestors/`)
   - `BaseIngestor` ABC: `ingest_agent(path) -> AIIntentManifest`
   - One per platform, wraps existing parsers (R4: wrap, don't rewrite)

4. **Emitters** (`emitters/`)
   - `BaseEmitter` ABC: `emit_agent(manifest, target_dir) -> Path`
   - One per platform

5. **Compatibility** (`compat/`)
   - Feature compatibility matrix for all 20 platform pairs
   - Instructional shim generation for non-transferable hooks
   - Rich table reporter

6. **Safe Archive Handling** (`utils/tar_safety.py`)
   - Rejects path traversal, symlink escapes, absolute paths
   - Used by ALL `tar.extractall()` calls

### New CLI Commands

- `agent-transfer convert <name> --from <platform> --to <platform>`
- `agent-transfer platforms`
- `agent-transfer compat --from <platform> --to <platform>`

### Canonical Tool Mapping

```
Claude Code "Read"  <-->  Canonical "file_read"  <-->  Codex "read_file"
Claude Code "Bash"  <-->  Canonical "shell_exec"  <-->  Gemini "run_shell_command"
MCP tools (mcp__server__tool) pass through directly
```

### Hook/Trigger Translation

| Source | Target with hooks | Target without hooks |
|--------|------------------|---------------------|
| Claude Code `PreToolUse`/`PostToolUse` | Map to equivalent event | Instructional shim in system prompt |
| Codex CLI `onToolCall` | Map to equivalent event | Instructional shim in system prompt |
| Gemini CLI triggers | Map to equivalent event | Instructional shim in system prompt |
| Goose recipe step | Map to hook/skill step | Embed in system prompt |
| OpenCode JS plugin hooks | Map to equivalent event | Instructional shim in system prompt |

**Hook import policy (Resolved Q4):** When converting INTO Claude Code, incoming hooks from other platforms become instructional shims in the system prompt — no automatic `PreToolUse` generation. Conversion report documents shimmed hooks for manual review.

---

## Constraints

- **R1**: Same-platform = byte-identical, no IR
- **R2**: IR only for cross-platform
- **R3**: Linux + WSL only (macOS future phase)
- **R4**: Wrap existing parsers, don't rewrite
- **R5**: All existing CLI commands unchanged
- **R6**: No hardcoded absolute paths — use `Path.home()` and platform config abstractions
- **R7**: Safe tar extraction everywhere
- **R8**: Never transfer secrets
- **R9**: Plugin architecture with ABCs and entry_points
- **R10**: File naming discipline — no `_v2`, `_new`, `_old` suffixes

---

## Success Criteria

1. Claude Code -> IR -> Claude Code = byte-identical (lossless round-trip)
2. System prompts preserved in 100% of cross-platform conversions
3. Compatibility matrix covers all 20 platform pairs (5 x 4)
4. Zero path traversal or XSS vulnerabilities
5. All existing CLI commands work unchanged
6. All existing tests pass (zero regressions)

---

## Known Bugs (Must Fix First)

| ID | Severity | Description |
|----|----------|-------------|
| B1 | CRITICAL | Unsafe `tar.extractall()` — path traversal |
| B2 | CRITICAL | Missing `skill_comparisons` arg crashes `ImportPreview` |
| B3 | CRITICAL | XSS via `\|safe` on user-controlled markdown |
| B4 | HIGH | KEEP mode miscounts imports |
| B5 | MEDIUM | `pyproject.toml` missing subpackage + templates |
| B6 | MEDIUM | Version mismatch `__init__.py` vs `pyproject.toml` |
| B7 | MEDIUM | Hand-rolled TOML parser fails on complex files |

---

## Target Platforms

| Platform | Format | Config Dir | MCP |
|----------|--------|------------|-----|
| Claude Code | `.md` YAML frontmatter | `~/.claude/` | Yes (native) |
| Codex CLI | `SKILL.md` YAML frontmatter | `~/.agents/skills/` | Yes (STDIO) |
| Gemini CLI | JSON `settings.json` | `~/.gemini/skills/` | Yes (full) |
| Goose | YAML recipes | `~/.config/goose/recipes/` | Yes (native) |
| OpenCode | JSON/JS plugins | `.opencode/plugins/` | Yes (full) |

---

## Resolved Questions

1. **IR file extension**: `.aim.yaml` — consistent with the AIM (AI Intent Manifest) naming throughout the spec and CLI (`--to aim`).
2. **Version strategy**: Bug fixes ship as `v1.2.0`, platform abstraction ships as `v2.0.0`. Sprint 1 checkpoint = `v1.2.0-security`, Sprint 6 checkpoint = `v2.0.0`.
3. **Priority order**: Codex first (most similar format), then Goose + Gemini (Sprint 5), then OpenCode (Sprint 6). Matches sprint plan.
4. **Hook import from other platforms**: Best-effort only. Goose recipe steps and Gemini CLI triggers map to instructional shims in system prompt when converting INTO Claude Code. No automatic `PreToolUse` hook generation — hooks require manual review. Emitters must document shimmed hooks in conversion report.
