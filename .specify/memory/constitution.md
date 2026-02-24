# Project Constitution: agent-transfer

## Identity
- **Project**: agent-transfer — Platform-Agnostic AI Agent Transfer Library
- **Language**: Python >= 3.8
- **CLI Framework**: Click
- **TUI**: Rich
- **Package Manager**: uv (preferred), pip (fallback)

## Rules

### R1: Lossless Same-Platform Transfer
Claude Code -> Claude Code transfers MUST remain byte-identical. No IR involved. The fast path writes `original_content` verbatim. This is non-negotiable.

### R2: IR Only for Cross-Platform
The Intermediate Representation (AI Intent Manifest) is ONLY used when source and target are different platforms. Never inject IR into same-platform workflows.

### R3: Linux Only (For Now)
Target Linux + WSL only. No Windows native paths. No macOS paths. macOS is a future phase — do not add macOS-specific code yet.

### R4: Wrap, Don't Rewrite
Existing parser.py, skill_parser.py, discovery.py, skill_discovery.py become internal implementation details of the Claude Code platform/ingestor. They are imported and delegated to, NOT replaced or rewritten.

### R5: Backward Compatibility
All existing CLI commands (export, import, list-agents, list-skills, discover, view, validate-tools, validate-skills, check-ready) MUST work unchanged. New commands are additions only.

### R6: No Hardcoded Absolute Paths
Use `Path.home()`, `Path.cwd()`, and platform config abstractions. Never hardcode `/home/user/` or `~/.claude/` as literals in logic (display strings are fine).

### R7: Safe Archive Handling
All `tarfile.extractall()` calls MUST use the safe extraction utility. Reject path traversal, symlink escapes, and absolute paths in archive members.

### R8: No Secret Transfer
Never transfer API keys, tokens, credentials, or auth config between machines or platforms. The IR defines `auth_requirements` but never carries actual secrets.

### R9: Plugin Architecture
Platforms, ingestors, and emitters use abstract base classes. Third parties can add platforms via Python entry_points. No hardcoded platform lists in core logic.

### R10: File Naming Discipline
Do not rename files for versioning. We version by git history. Do not create _v2, _new, _old suffixes.

### R11: Test Coverage
Every new module must have corresponding tests. The critical test is the lossless round-trip: Claude Code -> IR -> Claude Code = byte-identical.

### R12: Adversarial Bug Hunting
Before merging any sprint, run adversarial bug hunter agents (targeted + general scan). Fix all CRITICAL and HIGH findings before merge.
