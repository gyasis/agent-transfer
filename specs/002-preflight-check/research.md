# Research: Preflight Check

**Branch**: `002-preflight-check` | **Date**: 2026-03-11

## R1: Script Dependency Parsing

**Decision**: Regex-based pattern matching for CLI tools and env vars in bash/python/js scripts.

**Rationale**: The codebase already uses regex patterns extensively (parser.py, skill_parser.py, tool_checker.py). AST parsing (via shellcheck or Python ast module) would add complexity and dependencies for marginal accuracy gains. Regex catches 80-90% of cases; `.preflight.yml` fills the rest.

**Patterns to use**:
- CLI tools in bash: `r'^\s*(command\s+-v|which)\s+(\S+)'`, shebang `r'^#!\s*/usr/bin/env\s+(\S+)'`, direct invocations via a known-tools set
- Env vars in bash: `r'\$\{?([A-Z_][A-Z0-9_]*)\}?'`
- Env vars in Python: `r'os\.environ\[(["\'])([A-Z_][A-Z0-9_]*)\1\]'`, `r'os\.environ\.get\((["\'])([A-Z_][A-Z0-9_]*)\1'`
- Env vars in JS: `r'process\.env\.([A-Z_][A-Z0-9_]*)'`
- Source directives: `r'^\s*(?:source|\.)\s+(.+)'`

**Alternatives Considered**: Python `ast` module for .py files (too heavy, only catches Python), shellcheck JSON output (external dependency), tree-sitter (overkill).

## R2: Binary Architecture Detection

**Decision**: Read ELF magic bytes with Python's `struct` module. No external dependencies.

**Rationale**: ELF format is standardized. Bytes 0-3 = `\x7fELF` (magic), byte 4 = class (1=32-bit, 2=64-bit), byte 18 = architecture (0x3E=x86_64, 0x28=ARM, 0xB7=AArch64). Confirmed working against the real `task-watchdog` binary on this system.

**Implementation**:
```python
def detect_binary_arch(path: Path) -> Optional[dict]:
    with open(path, 'rb') as f:
        header = f.read(20)
    if header[:4] != b'\x7fELF':
        return None
    arch_map = {0x3E: 'x86_64', 0x28: 'arm', 0xB7: 'aarch64', 0x03: 'i386'}
    return {'format': 'elf', 'arch': arch_map.get(header[18], 'unknown')}
```

**Alternatives Considered**: `file` command via subprocess (works but adds shell dependency), `pyelftools` (external dep), `lief` (heavy).

## R3: Git Remote URL Extraction

**Decision**: Python `configparser` reading `.git/config`.

**Rationale**: All three real git repos tested use identical format. `configparser` handles it natively with the gotcha that section names include quotes: `config['remote "origin"']['url']`. No external dependencies needed.

**Gotcha**: The section name is literally `remote "origin"` with quotes included in the string.

**Alternatives Considered**: Regex (fragile with multiline), `gitpython` (heavy external dep), `subprocess git remote get-url origin` (shells out, requires git CLI).

## R4: MCP Config Merging

**Decision**: Merge configs from multiple sources using existing `config_manager.py` patterns. Check `mcpServers` key in all sources.

**Rationale**: Both `.claude/mcp.json` and `.gemini/settings.json` use identical `mcpServers` dict structure. `tool_checker.py` already handles 3 config formats (servers, mcpServers, direct dict). Reuse that logic.

**Config sources (priority order)**:
1. Project-level: `.claude/settings.local.json`, `.claude/settings.json`
2. User-level: `~/.claude/mcp.json`, `~/.claude/settings.json`
3. Cross-platform: `~/.gemini/settings.json` (for Gemini MCP servers)

**MCP server install type detection** (from command + args):
- `npx -y @package` → npm-on-demand
- `bunx -y @package` → bun-on-demand
- `uv run --directory /path fastmcp run` → git-repo-uv
- `/path/.venv/bin/python script.py` → git-repo-python-venv
- `node /path/script.js` → git-repo-node
- `npx mcp-remote https://...` → remote-sse
- `docker run ...` → docker

## R5: Setup Method Detection Heuristics

**Decision**: Check for indicator files in priority order.

**Rationale**: Real-world analysis of 3 repos confirmed reliable indicators. Order matters — check most specific first.

**Heuristics**:
| Check | Indicator | Setup Method |
|-------|-----------|-------------|
| `Cargo.toml` exists | Rust project | `cargo build --release` |
| `package.json` exists | Node project | `npm install` |
| `pyproject.toml` + `uv` comment in `requirements.txt` | UV-managed Python | `uv sync` |
| `pyproject.toml` with `[build-system]` | Hatchling/setuptools | `pip install -e .` |
| `requirements.txt` only | Pip project | `pip install -r requirements.txt` |
| `Dockerfile` exists | Docker project | `docker build` |
| `setup.py` only | Legacy pip | `pip install -e .` |

## R6: Existing Code Reuse

**Decision**: Compose existing utilities rather than rewriting.

**Rationale**: Every parsing pattern needed already exists in the codebase:

| Need | Existing Function | Module |
|------|------------------|--------|
| Extract MCP tools from agents | `extract_tools_from_agent()` | tool_checker.py |
| Parse MCP tool name → server ID | `parse_mcp_tool_name()` | tool_checker.py |
| Get configured MCP servers | `get_available_mcp_servers()` | tool_checker.py |
| Find MCP config files | `find_mcp_config()` | tool_checker.py |
| Parse agent YAML frontmatter | `parse_agent_file()` | parser.py |
| Parse skill YAML frontmatter | `parse_skill_md()` | skill_parser.py |
| Detect skill dependencies | `detect_dependencies()` | skill_parser.py |
| Parse requirements.txt | `parse_requirements_txt()` | skill_validator.py |
| Parse pyproject.toml | `parse_pyproject_toml()` | skill_validator.py |
| Find agent directories | `find_agent_directories()` | discovery.py |
| Find skill directories | `find_skill_directories()` | skill_discovery.py |
| Resolve platform paths | `get_pathfinder()` | pathfinder.py |
| Read MCP server configs | `read_mcp_json()` | config_manager.py |
| Detect runtimes | `detect_runtimes()` | config_manager.py |

**New code needed**: Script parsing for CLI tools/env vars (regex), binary detection (struct), git remote extraction (configparser), manifest schema (dataclasses + JSON), readiness report (Rich tables), `.preflight.yml` reader (yaml).
