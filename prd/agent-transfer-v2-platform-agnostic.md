# PRD: agent-transfer v2.0 — Platform-Agnostic AI Agent Transfer Library

**Author:** Gyasi Sutton
**Date:** 2026-02-23
**Status:** Draft

---

## 1. Problem Statement

AI coding assistants are fragmenting across platforms (Claude Code, OpenAI Codex CLI, Gemini CLI, Goose, OpenCode). Developers invest significant effort crafting agents, skills, recipes, and hooks for one platform, but cannot reuse that work when switching platforms or working across teams that use different tools.

The current `agent-transfer` tool only handles Claude Code <-> Claude Code transfers. There is no way to convert a Claude Code agent into a Goose recipe, or import an OpenAI Codex skill into Claude Code.

---

## 2. Vision

A **platform-agnostic CLI library** that enables bidirectional transfer of AI agent definitions between major coding assistant platforms — preserving intent while adapting to each platform's native format.

---

## 3. Two Transfer Modes

`agent-transfer` handles two fundamentally different transfer scenarios. Each has distinct workflows, responsibilities, and constraints.

### 3.1 Internal Transfer — Between Platforms on the SAME Machine

**What:** Convert an agent/skill from one platform to another, both installed locally.
**Example:** Claude Code agent → Goose recipe, on the same laptop.

```
┌─────────────────────────────────────────────────────────┐
│                    SAME MACHINE                         │
│                                                         │
│  ~/.claude/agents/my-agent.md                           │
│         │                                               │
│         ▼                                               │
│  ┌─────────────┐    ┌─────────┐    ┌────────────────┐  │
│  │  Ingestor   │───▶│  IR/AIM │───▶│    Emitter     │  │
│  │ (Claude)    │    │         │    │   (Goose)      │  │
│  └─────────────┘    └─────────┘    └───────┬────────┘  │
│                                            │            │
│                          ~/.config/goose/recipes/       │
│                              my-agent.yaml              │
└─────────────────────────────────────────────────────────┘
```

**Workflow:**
1. `agent-transfer platforms` — detect which platforms are installed locally
2. `agent-transfer compat --from claude-code --to goose` — check what transfers
3. `agent-transfer convert my-agent --from claude-code --to goose` — convert
4. **agent-transfer handles everything:** reads source, converts via IR, writes to target platform's config directory
5. No archive file needed — direct filesystem-to-filesystem

**Who handles what:**
| Responsibility | Handled by |
|---------------|------------|
| Read source agent files | **agent-transfer** (via platform-specific Ingestor) |
| Convert format | **agent-transfer** (via IR) |
| Write target agent files | **agent-transfer** (via platform-specific Emitter) |
| Detect installed platforms | **agent-transfer** (via PlatformRegistry) |
| Tool name mapping | **agent-transfer** (via canonical tool map) |
| Hook/trigger translation | **agent-transfer** (shimming or native mapping) |
| MCP server config | **agent-transfer** copies config; **target platform** validates at runtime |
| Runtime execution | **target platform** (agent-transfer does NOT run agents) |

**Same-platform internal transfer (e.g., Claude Code → Claude Code on same machine):**
This is just a copy. No IR needed. Exact/lossless. This is the existing `list-agents` workflow — the agents are already on the machine.

---

### 3.2 External Transfer — Between TWO Different Computers

**What:** Move agents from Machine A to Machine B. Machines may run the same platform OR different platforms.
**Example 1:** Claude Code on laptop → Claude Code on server (same platform, different machines)
**Example 2:** Claude Code on laptop → Goose on coworker's machine (different platform, different machines)

```
┌──────────── MACHINE A ────────────┐     ┌──────────── MACHINE B ────────────┐
│                                   │     │                                   │
│  ~/.claude/agents/my-agent.md     │     │                                   │
│         │                         │     │                                   │
│         ▼                         │     │                                   │
│  ┌─────────────┐                  │     │                  ┌─────────────┐  │
│  │  Ingestor   │                  │     │                  │   Emitter   │  │
│  │ (Claude)    │                  │     │                  │  (Goose)    │  │
│  └──────┬──────┘                  │     │                  └──────┬──────┘  │
│         ▼                         │     │                         ▲         │
│  ┌─────────────┐                  │     │                  ┌──────┴──────┐  │
│  │  Archive    │  ── scp/git ──────────▶│                  │  Archive    │  │
│  │  .tar.gz    │                  │     │                  │  .tar.gz    │  │
│  └─────────────┘                  │     │                  └─────────────┘  │
│                                   │     │                         │         │
│                                   │     │         ~/.config/goose/recipes/  │
│                                   │     │             my-agent.yaml         │
└───────────────────────────────────┘     └───────────────────────────────────┘
```

**Workflow — Same Platform (Claude Code → Claude Code):**
1. Machine A: `agent-transfer export` → produces `.tar.gz` archive
2. Transfer archive: `scp`, `git`, USB, email, Slack, whatever
3. Machine B: `agent-transfer import backup.tar.gz` → extracts to `~/.claude/agents/`
4. **LOSSLESS.** Byte-identical files. No IR involved. This is the existing v1.x behavior.

**Workflow — Cross Platform (Claude Code → Goose):**
1. Machine A: `agent-transfer export --format aim` → produces `.tar.gz` with IR manifests inside
2. Transfer archive to Machine B
3. Machine B: `agent-transfer import backup.tar.gz --to goose` → converts IR → Goose recipes
4. **Best-effort.** Compatibility report shown. Shims applied where needed.

**Workflow — Cross Platform with pre-conversion (Claude Code → Goose):**
1. Machine A: `agent-transfer convert my-agent --from claude-code --to goose --output my-agent-goose.tar.gz`
2. Transfer archive to Machine B
3. Machine B: `agent-transfer import my-agent-goose.tar.gz` → already in Goose format, direct extract

**Who handles what:**
| Responsibility | Handled by |
|---------------|------------|
| Package agents into archive | **agent-transfer** (export command) |
| Transport archive between machines | **User** (scp, git, email, etc.) |
| Unpack and place agent files | **agent-transfer** (import command) |
| Cross-platform conversion (if needed) | **agent-transfer** (can happen on either machine) |
| Conflict resolution (file already exists) | **agent-transfer** (diff/merge/keep/overwrite/duplicate) |
| Dependency validation | **agent-transfer** (check-ready command on target machine) |
| MCP server availability | **Target machine's platform** (agent-transfer warns if MCP servers referenced but not configured) |

**Same-platform external transfer:**
- The archive contains native platform files (`.md` for Claude Code, `.yaml` for Goose, etc.)
- No conversion needed — direct extract to the correct config directory
- This is the core v1.x use case and remains lossless

**Cross-platform external transfer:**
- The archive contains IR manifests (`.aim.yaml`) or pre-converted target files
- Conversion can happen on Machine A (pre-convert before sending) OR Machine B (convert on import)
- Compatibility report generated either way

---

### 3.3 Summary: When IR is Used vs. Not

| Scenario | IR Used? | Lossless? |
|----------|----------|-----------|
| Same platform, same machine (Claude → Claude) | No | Yes, exact copy |
| Same platform, different machines (Claude → Claude) | No | Yes, archive round-trip |
| Different platform, same machine (Claude → Goose) | Yes | Best-effort + warnings |
| Different platform, different machines (Claude → Goose) | Yes | Best-effort + warnings |

---

## 4. Target Platforms

| Platform | Concept | Native Format | Config Location | MCP Support |
|----------|---------|---------------|-----------------|-------------|
| **Claude Code** | Agents + Skills + Hooks | `.md` (YAML frontmatter) | `~/.claude/` | Yes (native) |
| **OpenAI Codex CLI** | Agent Skills | `SKILL.md` (YAML frontmatter) | `~/.agents/skills/`, TOML | Yes (STDIO) |
| **Gemini CLI** | Skills + Extensions | JSON (`settings.json`) | `~/.gemini/skills/` | Yes (full) |
| **Goose (by Block)** | Recipes | YAML | `~/.config/goose/recipes/` | Yes (native) |
| **OpenCode** | Plugins (JS/TS modules) | JSON (`opencode.json`) | `.opencode/plugins/` | Yes (full) |

---

## 4. Scope

### In Scope
- Platform-agnostic Intermediate Representation (IR) format for agents/skills/hooks/recipes
- Ingestors: parse each platform's native format into the IR
- Emitters: generate each platform's native format from the IR
- Compatibility matrix: auto-detect what transfers cleanly vs. needs shimming vs. cannot transfer
- CLI commands for cross-platform conversion
- Claude Code skills/hooks that automate the conversion process
- Plugin architecture so community can add new platforms

### Out of Scope (for now)
- Windows native support (Linux only, WSL counts as Linux)
- macOS support (planned for future phase)
- GUI/web interface for conversion (CLI only)
- Runtime agent execution (we transfer definitions, not run them)
- Secret/credential transfer (explicitly excluded for security)

---

## 5. Requirements

### 5.1 Core Requirement: Lossless Same-Platform Transfer

**Claude Code -> Claude Code transfers MUST remain exact and lossless.** The existing behavior (byte-identical `.md` files, exact skill directories, exact hooks) stays unchanged. The IR is ONLY used when crossing platforms.

### 5.2 Intermediate Representation (IR)

The IR (working name: "AI Intent Manifest" / AIM) must:
- Be YAML-based (human-readable, supports comments, git-diffable)
- Capture semantic intent, not platform-specific syntax
- Include: identity (name, description, system prompt), capabilities (tools), triggers (hooks/events), logic (multi-step sequences), environment (deps, env vars), MCP server configs
- Support "shadow data" (`platform_specific` section) to preserve platform-native details for round-tripping
- Be versioned with a schema version field

### 5.3 Ingestor/Emitter Architecture

- Each platform needs an Ingestor (native format -> IR) and Emitter (IR -> native format)
- Plugin-based: `BaseIngestor` / `BaseEmitter` abstract classes
- Third parties can add platforms via Python entry_points
- Existing parser/discovery code is wrapped, not rewritten

### 5.4 Transferability Classification

Every feature must be classified per platform pair:

| Classification | Meaning | Example |
|---------------|---------|---------|
| **Clean transfer** | Direct mapping exists | System prompts, tool lists, MCP configs |
| **Best-effort (shim)** | No direct mapping; fallback available | Hooks -> prompt injection ("instructional shim") |
| **Cannot transfer** | Platform-specific, no equivalent | Auth mechanisms, native integrations, JS/TS plugin code |

The tool must generate a compatibility report BEFORE conversion showing what will transfer and what won't.

### 5.5 CLI Commands

New commands (existing commands unchanged):
- `agent-transfer convert <name> --from <platform> --to <platform>` — cross-platform conversion
- `agent-transfer platforms` — list supported platforms + detection status (installed/not found)
- `agent-transfer compat --from <platform> --to <platform>` — show feature compatibility matrix

### 5.6 Bug Fixes (Blockers for v2.0)

These existing bugs must be fixed before v2.0:

| ID | Severity | Description | File |
|----|----------|-------------|------|
| B1 | CRITICAL | Unsafe `tar.extractall()` — path traversal vulnerability | `transfer.py:331,647`, `import_analyzer.py:52`, `skill_validator.py:654` |
| B2 | CRITICAL | Missing `skill_comparisons` arg crashes `ImportPreview` | `import_analyzer.py:111` |
| B3 | CRITICAL | XSS via `\|safe` on user-controlled markdown in templates | `agent_view.html:442`, `skill_view.html:561` |
| B4 | HIGH | KEEP mode returns truthy path, miscounts imports as skipped | `conflict_resolver.py:428` |
| B5 | MEDIUM | `pyproject.toml` missing `utils` subpackage + HTML templates | `pyproject.toml:57-60` |
| B6 | MEDIUM | Version mismatch `__init__.py` (1.0.0) vs `pyproject.toml` (1.1.0) | Both files |
| B7 | MEDIUM | Hand-rolled TOML parser fails on complex `pyproject.toml` | `skill_validator.py:155-194` |

### 5.7 Claude Code Skills for Automation

Skills that live in `~/.claude/skills/` and automate the transfer workflow:
- `/transfer-agent` — interactive conversion with compatibility audit and user choices
- `/analyze-platform` — scan a new platform's documentation and generate an emitter stub

---

## 6. User Stories

### US-1: Cross-Platform Agent Conversion
> As a developer who uses both Claude Code and Goose, I want to convert my Claude Code agent into a Goose recipe so I can use the same agent logic on both platforms.

**Acceptance criteria:**
- `agent-transfer convert my-agent --from claude-code --to goose` produces a valid Goose recipe YAML
- System prompt is preserved
- MCP server configs are preserved
- Hooks are converted to recipe steps (or instructional shims with warning)
- Compatibility report is shown before conversion

### US-2: Import from Another Platform
> As a Claude Code user, I want to import a Goose recipe into Claude Code so I can use a teammate's workflow in my preferred tool.

**Acceptance criteria:**
- `agent-transfer convert smart-commit --from goose --to claude-code` produces a valid `.md` agent
- Recipe steps map to system prompt instructions
- MCP configs are preserved
- Warning shown if recipe features have no Claude Code equivalent

### US-3: Platform Discovery
> As a developer, I want to see which AI coding platforms are installed on my system and their compatibility for transfer.

**Acceptance criteria:**
- `agent-transfer platforms` shows a table of all supported platforms with detection status
- `agent-transfer compat --from claude-code --to codex` shows feature-by-feature compatibility

### US-4: Lossless Same-Platform Transfer (Existing Behavior)
> As a Claude Code user, I want to export and import agents between machines with zero loss.

**Acceptance criteria:**
- `agent-transfer export` / `agent-transfer import` work exactly as they do today
- No regressions. Byte-identical round-trip for Claude Code <-> Claude Code.

### US-5: Bulk Multi-Platform Export
> As a developer maintaining agents across platforms, I want to export an agent to IR format so I can generate outputs for multiple target platforms.

**Acceptance criteria:**
- `agent-transfer convert my-agent --from claude-code --to aim` produces an IR YAML file
- That IR file can then be converted to any target: `agent-transfer convert my-agent.aim.yaml --from aim --to goose`

### US-6: Security Fix
> As a user receiving agent archives from others, I need protection against malicious archives that could write files outside the target directory.

**Acceptance criteria:**
- Archives with path traversal (`../../etc/passwd`) are rejected with clear error
- Archives with symlink escapes are rejected
- All `tar.extractall()` calls use safe extraction

---

## 7. Technical Architecture (High Level)

```
Same platform:    Source files  ──exact copy──>  Target files  (lossless)

Cross platform:   Source files  ──Ingestor──>  IR/AIM  ──Emitter──>  Target files
                                                  │
                                          Compatibility check
                                          + warnings/shims
```

### 7.1 Canonical Tool Mapping

Tools are mapped through a canonical registry:

```
Claude Code "Read"  ←→  Canonical "file_read"  ←→  Codex "read_file"
Claude Code "Bash"  ←→  Canonical "shell_exec"  ←→  Gemini "run_shell_command"
MCP tools (mcp__server__tool) pass through directly (all platforms support MCP)
```

### 7.2 Hook/Trigger Translation

| Source | Target with hooks | Target without hooks |
|--------|------------------|---------------------|
| Claude Code `PreToolUse` hook | Map to equivalent event | Generate "instructional shim" (prompt injection) |
| Goose recipe step | Map to hook or skill step | Embed in system prompt |

### 7.3 Plugin Architecture

```
BasePlatform  →  detect(), find_agents(), find_skills()
BaseIngestor  →  ingest_agent(path) -> AIIntentManifest
BaseEmitter   →  emit_agent(manifest, target_dir) -> Path
```

Third parties register via `pyproject.toml` entry_points:
```toml
[project.entry-points."agent_transfer.platforms"]
my-platform = "my_package:MyPlatform"
```

---

## 8. What Transfers vs. What Doesn't

### Transfers Cleanly
- System prompts / persona instructions
- Tool lists (via canonical mapping)
- MCP server configurations (all 5 platforms support MCP)
- Agent name, description, metadata
- Python dependencies (requirements.txt)

### Transfers with Shimming (Best Effort)
- Hooks / lifecycle events → instructional shims or recipe steps
- Multi-step workflows → recipe sequences or prompt instructions
- Permission modes → platform-specific safety settings

### Cannot Transfer
- Authentication / API keys / secrets (security exclusion)
- Platform-native integrations (e.g., Gemini's Google Cloud tools)
- JS/TS plugin code (OpenCode) — requires manual rewrite
- Platform-specific UI features (web viewers, TUI elements)

---

## 9. Success Metrics

- **Lossless round-trip:** Claude Code -> IR -> Claude Code produces byte-identical output
- **Cross-platform accuracy:** System prompts preserved in 100% of conversions; tool mappings correct for all canonical tools
- **Compatibility coverage:** Matrix covers all 20 platform pairs (5 x 4)
- **Security:** Zero path traversal or XSS vulnerabilities (all existing bugs fixed)
- **Backward compatibility:** All existing CLI commands work unchanged; existing tests pass

---

## 10. Suggested Implementation Roadmap

### Sprint 1: Foundation (Bug Fixes + Security)
1. Create `tar_safety.py` — safe extraction utility
2. Fix all `tar.extractall()` calls across codebase (B1)
3. Fix missing `skill_comparisons` arg (B2)
4. Sanitize HTML output in web server to fix XSS (B3)
5. Fix KEEP mode return value (B4)
6. Fix pyproject.toml packaging, version sync, TOML parser, lint (B5-B7)
7. Run existing tests — ensure zero regressions

### Sprint 2: Platform Abstraction Layer
1. Create `platforms/base.py` — `PlatformConfig`, `BasePlatform`, `PlatformRegistry`
2. Create `platforms/claude_code.py` — wrap existing discovery/parser code
3. Create stub platforms for Codex, Gemini CLI, Goose, OpenCode (detect + config only)
4. Add `agent-transfer platforms` CLI command
5. Tests: platform detection, config correctness

### Sprint 3: IR Schema + Claude Code Ingestor/Emitter
1. Create `ir/manifest.py` — `AIIntentManifest` + YAML serialization
2. Create `ir/capability.py` — canonical tool mapping registry
3. Create `ir/validators.py` — IR validation
4. Create `ingestors/base.py` + `ingestors/claude_code.py` — parse agents/skills -> IR
5. Create `emitters/base.py` + `emitters/claude_code.py` — IR -> Claude Code files
6. **Critical test:** Claude Code -> IR -> Claude Code = byte-identical (lossless round-trip)
7. Add `agent-transfer convert` CLI command (Claude Code <-> IR only at this point)

### Sprint 4: Compatibility Matrix + First Cross-Platform Target (Codex)
1. Create `compat/matrix.py` — feature compatibility data
2. Create `compat/reporter.py` — Rich table display
3. Create `compat/shims.py` — instructional shim generation
4. Add `agent-transfer compat` CLI command
5. Create `ingestors/codex.py` + `emitters/codex.py` — Codex is most similar format
6. Test: Claude Code -> IR -> Codex and Codex -> IR -> Claude Code

### Sprint 5: Goose + Gemini CLI Support
1. Create `ingestors/goose.py` + `emitters/goose.py` — YAML recipe format
2. Create `ingestors/gemini_cli.py` + `emitters/gemini_cli.py` — JSON settings
3. Test cross-platform conversions for all 3 platforms
4. Update compatibility matrix with real test results

### Sprint 6: OpenCode + Claude Code Skills
1. Create `ingestors/opencode.py` + `emitters/opencode.py` — JS/TS plugin stubs
2. Create Claude Code skills: `/transfer-agent`, `/analyze-platform`
3. Entry_points plugin registration for third-party platforms
4. Documentation and examples

### Future: macOS Support
- Add `/opt/homebrew/bin/` to discovery paths (Apple Silicon)
- Test all path handling on macOS
- Add macOS to CI matrix

---

## 11. Open Questions

1. **IR file extension?** `.aim.yaml`? `.agent.yaml`? `.transfer.yaml`?
2. **Should IR files be committable to git repos?** (Yes seems right — they're human-readable YAML)
3. **Priority order for cross-platform support?** Proposed: Codex first (most similar format), then Goose, Gemini CLI, OpenCode
4. **Should we support converting hooks into Claude Code hooks FROM other platforms?** (Goose recipe steps -> Claude Code hooks)
5. **Version strategy?** Bug fixes ship as v1.2.0, platform abstraction as v2.0.0?
