# Implementation Plan: Pathfinder Module

**Branch**: `001-pathfinder-module` | **Date**: 2026-03-11 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-pathfinder-module/spec.md`

## Summary

Create `agent_transfer/utils/pathfinder.py` — a centralized path resolution module that replaces 35+ scattered `Path.home() / '.claude'` references across 7 modules with a single, platform-aware resolver. Supports 5 AI platforms (Claude Code, Codex, Gemini CLI, Goose, OpenCode) via pluggable path profiles, with cross-machine remapping, environment variable overrides, and executable discovery consolidation.

## Technical Context

**Language/Version**: Python >= 3.8 (supports 3.8–3.12)
**Primary Dependencies**: pathlib (stdlib), shutil (stdlib), os (stdlib), dataclasses (stdlib). No new external dependencies.
**Storage**: Filesystem paths only — no database or persistent state
**Testing**: pytest >= 7.0.0, pytest-mock >= 3.10.0, pytest-cov >= 4.0.0
**Target Platform**: Linux + WSL (per R3)
**Project Type**: Library + CLI tool
**Performance Goals**: Path resolution < 1ms per call (cached). Executable discovery < 500ms first call, < 1ms cached.
**Constraints**: Python 3.8 minimum means no `match/case`, no `type X = Y` aliases, `str | None` must use `Optional[str]`
**Scale/Scope**: 7 modules to refactor, 5 platform profiles, ~400-500 LOC for pathfinder.py

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Rule | Status | Notes |
|------|--------|-------|
| R1: Lossless Same-Platform | PASS | Pathfinder doesn't touch transfer content, only resolves where files live |
| R2: IR Only Cross-Platform | PASS | No IR involvement — pathfinder is infrastructure |
| R3: Linux Only | PASS | All path profiles target Linux/WSL paths only. No macOS/Windows |
| R4: Wrap Don't Rewrite | PASS | discovery.py, config_manager.py become thin wrappers delegating path logic to pathfinder |
| R5: Backward Compatibility | PASS | All CLI commands unchanged. Modules produce same outputs via pathfinder |
| R6: No Hardcoded Absolute Paths | PASS | Pathfinder uses Path.home(), env vars, and relative profile definitions only |
| R7: Safe Archive Handling | N/A | No archive operations |
| R8: No Secret Transfer | N/A | No secrets involved |
| R9: Plugin Architecture | PASS | PathProfileRegistry supports third-party profiles via entry_points |
| R10: File Naming Discipline | PASS | Single new file: pathfinder.py. No versioned suffixes |
| R11: Test Coverage | PASS | New test file required: test_pathfinder.py |
| R12: Adversarial Bug Hunting | PASS | Will run targeted + general scans before merge |

**Gate result: ALL PASS** — no violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/001-pathfinder-module/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── pathfinder-api.md
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code (repository root)

```text
agent_transfer/
├── cli.py                          # Refactor: use pathfinder for skill/agent paths
├── utils/
│   ├── pathfinder.py               # NEW: centralized path resolution
│   ├── discovery.py                # Refactor: delegate path logic to pathfinder
│   ├── config_manager.py           # Refactor: use pathfinder for config paths + remap
│   ├── transfer.py                 # Refactor: use pathfinder for agent/skill dirs
│   ├── import_analyzer.py          # Refactor: use pathfinder for agent lookup
│   ├── skill_discovery.py          # Refactor: use pathfinder for skill dirs
│   └── tool_checker.py             # Refactor: use pathfinder for MCP config locations

tests/
├── test_pathfinder.py              # NEW: unit tests for pathfinder module
└── [existing test files unchanged]
```

**Structure Decision**: Single new module `pathfinder.py` in existing `agent_transfer/utils/` package. One new test file. Seven existing modules refactored. No new packages or directories needed in source tree.

## Complexity Tracking

> No violations to justify — all constitution gates pass.
