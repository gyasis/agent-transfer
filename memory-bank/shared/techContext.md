# Technical Context

**Purpose**: Technical constraints and environment

## Tech Stack

- **Language**: Python >= 3.8 (supports 3.8-3.12)
- **CLI**: Click (existing)
- **TUI**: Rich (selection matrix, briefing preview)
- **Config parsing**: PyYAML (frontmatter, .preflight.yml)
- **Data models**: Pydantic BaseModel (ManifestModel, AssetEntry — potential new dep if not already transitive)
- **stdlib**: pathlib, tarfile, shutil, hashlib, configparser, struct
- **Storage**: Filesystem only (no database). Bundles are directories or `.tar.gz`.
- **Platform**: Linux + WSL only (constitution R3). No macOS/Windows-native paths.

## Dependencies

- Click: CLI framework (existing)
- Rich: TUI tables and panels (existing)
- PyYAML: frontmatter + .preflight.yml (existing)
- Pydantic: BaseModel for ManifestModel, AssetEntry, RiskTag (added by 003 if not already pulled in)
- All other deps: Python stdlib (pathlib, tarfile, shutil, hashlib, configparser)

## Environment

- Development: Linux/WSL2. `~/.claude/` is the source tree. `/tmp/ab-mvp-sandbox-*` is the test sandbox.
- No production deployment — this is a local CLI tool.

---

## Reusable Utils (R4 — Wrap, Don't Rewrite)

Constitution rule R4 mandates these modules are **wrapped, not rewritten**. All new capability-level code in `agent_transfer/bridge/` delegates to these. They must not be modified in behavior unless explicitly extending for this feature (e.g., adding a risk-tag field or tightening the secret regex).

| Module | Path | Purpose |
|---|---|---|
| config_manager | `agent_transfer/utils/config_manager.py` | Exports rules, hooks, CLAUDE.md, settings, MCP servers from `~/.claude/`. Reads canonical `~/.claude.json` (21 servers). |
| mcp_classifier | `agent_transfer/utils/mcp_classifier.py` | Classifies all 21 MCP servers, 100% coverage, secret redaction, per-server `install_steps` + `config_after_install`. |
| script_discovery | `agent_transfer/utils/script_discovery.py` | Two-pass discovery of bin scripts referenced in skills/hooks/rules. Captured 7 user scripts including `session-search`. |
| mcp_source_bundler | `agent_transfer/utils/mcp_source_bundler.py` | Tars local MCP server dirs, soft 50MB / hard 500MB limits, redacts auth tokens in git remotes. 9 of 10 local servers bundle (~62MB). |
| transfer | `agent_transfer/utils/transfer.py` | Orchestrator — round-trip works in sandbox. Gains import-time mcpServers path-rewrite step (FR-015). |
| skill_parser | `agent_transfer/skill_parser.py` (or utils/) | Parses skill SKILL.md frontmatter and body. |
| skill_discovery | `agent_transfer/skill_discovery.py` (or utils/) | Discovers skills under `~/.claude/skills/`. |

---

## New Code — `agent_transfer/bridge/` Subpackage (planned, not yet created)

All capability-level work lives here. Does not exist as of 2026-05-04. Planned modules:

| Module | Purpose |
|---|---|
| `__init__.py` | Package init |
| `models.py` | ManifestModel, AssetEntry (path, dest_path, risk, conflict, sha256, mode_bits), RiskTag, ConflictPolicy, BriefingSection, Capability, Confirmation — all Pydantic BaseModel |
| `compose.py` | `ab compose --capability` core: graph walk over `~/.claude/` + selection-matrix data |
| `briefing.py` | Renders `BRIEFING.md` ("Dear Receiving Claude") from manifest + assets |
| `selection_matrix.py` | Rich-based 3-tier (CORE/COMPANIONS/CONTEXT) selection matrix UI — used on both export AND ingest sides |
| `preview.py` | Briefing Preview UI (Rich); enforces y/n gate on Yellow/Red assets before bundle seal |
| `rollback.py` | Snapshots `~/.claude`, `~/bin`, `~/.claude.json` regions before any write; produces `rollback.tar.gz` + `rollback.sh` |
| `ingest.py` | Destination-side: reads briefing, walks inventory, installs per conflict policy |
| `smoke_test.py` | Post-install self-interrogation + drift detection |
| `secrets.py` | Merged secret regex (Bearer / `sk-` / `ghp_` / `xox*` / generic) — called pre-seal AND post-seal (FR-010, SC-006) |

## Constitution Constraints Summary

| Rule | What it means in practice |
|---|---|
| R1 | CORE assets must round-trip byte-identical on same-platform transfers |
| R3 | All paths via `Path.home()` / `Path.cwd()` — no hardcoded absolute paths (R6 also) |
| R4 | Wrap existing utils — do not rewrite them |
| R5 | 9 existing CLI commands must keep working after adding `ab compose` group |
| R7 | Safe-extract on every tarfile.open in ingestion + rollback restore |
| R8 | No secrets in any shipped bundle |
| R10 | Rename at package/CLI/README level only — no file renames |
| R11 | New `tests/integration/test_capability_roundtrip.py` covers SC-001 |
| R12 | Adversarial scan (targeted + general) required before MVP merge (Wave 11) |
