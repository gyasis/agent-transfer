# Agent Transfer

A beautiful Python CLI tool to transfer Claude Code agents between systems with interactive selection.

**Standalone Script Available**: The `agent-transfer.sh` script works completely standalone for import operations - no Python package installation needed! See [STANDALONE_USAGE.md](./STANDALONE_USAGE.md) for details.

## Installation

### Automatic Installation (Recommended - Uses uv for Isolation)

```bash
# One command - automatically uses uv for isolated installation
cd agent-transfer
./install.sh
```

**This automatically:**
- ✅ Uses `uv` for isolated installation (no environment pollution)
- ✅ Installs dependencies in isolation
- ✅ Keeps your Python environment clean
- ✅ Creates the `agent-transfer` command

### Manual Installation with uv

```bash
# Install with uv (fast and isolated)
uv pip install -e .

# Or install globally
uv pip install .

# Or use uvx to run without installation
uvx agent-transfer export
```

### Using pip (Not Recommended - Pollutes Environment)

```bash
# ⚠️ This installs to your Python environment
pip install -e .

# Better: Use uv instead (see above)
```

### Development Installation

```bash
# Clone or navigate to the directory
cd agent-transfer

# Install in development mode
pip install -e .
# or
uv pip install -e .
```

## Usage

Once installed, use the `agent-transfer` command:

```bash
# Interactive export (beautiful UI to select agents)
agent-transfer export

# Export all agents (no selection)
agent-transfer export --all

# Export with custom filename
agent-transfer export my-backup.tar.gz

# Import agents
agent-transfer import backup.tar.gz

# List all available agents
agent-transfer list-agents

# Discover Claude Code installation (deep search)
agent-transfer discover

# Or use the flag
agent-transfer list-agents --discover

# Validate tool compatibility for all agents
agent-transfer validate-tools

# Validate with detailed output
agent-transfer validate-tools --verbose

# Launch web viewer on port 7651
agent-transfer view

# Web viewer with custom port
agent-transfer view --port 8080

# Show version
agent-transfer --version
```

## Features

- 🎨 **Beautiful Interactive UI** - Select agents with a rich terminal interface
- 📦 **Selective Export** - Choose specific agents or export all
- 🔍 **Agent Details** - View full information about each agent
- 🚀 **Fast & Isolated** - Works with uv for dependency isolation
- 📋 **Agent Listing** - List all available agents without exporting
- 🔄 **Smart Import** - Detects conflicts and handles overwrites
- 🔀 **Diff-Based Conflict Resolution** - Interactive merge with side-by-side diff viewing
- 🔎 **Deep Discovery** - Finds Claude Code in virtual environments, npm globals, conda, etc.
- 🎯 **Smart Detection** - Automatically finds agent directories in any installation type
- 🌐 **Web Viewer** - Beautiful HTML interface to browse and view agents with markdown rendering
- 📜 **Standalone Script** - `agent-transfer.sh` works without Python installation for import
- 🎨 **Modern UI** - Tailwind CSS for beautiful web interface
- 📁 **Organized Code** - Clean utils folder structure
- 🔧 **Tool Validation** - Check agent compatibility with your system before import

## Examples

### Export Selected Agents

```bash
$ agent-transfer export
# Launches interactive selector
# Select agents by number, view details, then confirm
```

### Export All Agents

```bash
$ agent-transfer export --all my-agents-backup.tar.gz
```

### Import Agents

```bash
$ agent-transfer import my-agents-backup.tar.gz
# Automatically detects Claude Code
# Handles conflicts with interactive diff/merge (default)

# Conflict resolution modes:
$ agent-transfer import backup.tar.gz                     # Interactive diff (default)
$ agent-transfer import backup.tar.gz -c overwrite        # Overwrite all existing
$ agent-transfer import backup.tar.gz -c keep             # Skip conflicts, keep existing
$ agent-transfer import backup.tar.gz -c duplicate        # Save as agent_1.md, etc.
```

### Conflict Resolution

When importing agents that conflict with existing files, you have several options:

- **diff** (default): Interactive mode - view unified diff, side-by-side comparison, and choose per file
- **overwrite**: Replace all existing files with incoming versions
- **keep**: Skip all conflicts, keep existing files untouched
- **duplicate**: Save incoming files with numeric suffix (agent_1.md, agent_2.md, etc.)

In interactive diff mode, you can:
- View unified diff with syntax highlighting
- View side-by-side comparison
- Perform line-by-line selective merge (Python CLI only)
- Choose different resolution per conflict

### List Agents

```bash
$ agent-transfer list-agents
# Shows all available agents in a table
```

### Web Viewer

```bash
$ agent-transfer view
# Launches web server at http://127.0.0.1:7651
# Opens browser automatically
# Browse agents with beautiful HTML interface
# Markdown files rendered with syntax highlighting

# Custom port
$ agent-transfer view --port 8080

# Don't open browser automatically
$ agent-transfer view --no-browser
```

### Validate Tool Compatibility

Before importing agents, check if they're compatible with your system:

```bash
$ agent-transfer validate-tools
# Scans all agents and checks if required tools are available
# Checks against built-in Claude Code tools and MCP servers

# Detailed output showing which tools are missing
$ agent-transfer validate-tools --verbose
```

**What it checks:**
- Built-in Claude Code tools (Read, Write, Edit, Bash, Grep, Glob, etc.)
- MCP servers configured in `~/.claude/mcp_servers.json`
- Custom tools referenced in agent configurations

**Example output:**
```
Scanning agents for tool compatibility...

✓ frontend-developer - All tools available
  Tools: Read, Edit, Grep, Bash

✗ data-analyst - Missing tools
  Available: Read, Edit, Bash
  Missing: mcp__snowflake__read_query, mcp__snowflake__describe_table

Summary: 1/2 agents compatible
```

## Interactive Selection

When you run `agent-transfer export`, you'll see:

- **Agent Table** with checkboxes, names, descriptions, types, and tools
- **Controls**:
  - Type a number (1-N) to toggle that agent
  - Type `a` to select all agents
  - Type `d` to deselect all agents
  - Type `i` then a number to view agent details
  - Press Enter to confirm selection
  - Type `q` to quit

## Troubleshooting

### Installation Issues

**"command not found: agent-transfer"**

After installation, the command might not be in your PATH:

```bash
# Check where it was installed
uv pip show agent-transfer

# Or with pip
pip show agent-transfer

# Try running directly
python -m agent_transfer.cli export
```

**Solution:** Add the installation directory to your PATH or use the direct Python invocation.

**"No module named 'agent_transfer'"**

Dependencies weren't installed properly:

```bash
# Reinstall with uv (recommended)
cd agent-transfer
uv pip install -e .

# Or with pip
pip install -e .

# Verify installation
agent-transfer --version
```

### Agent Discovery Issues

**"No agent directories found"**

The tool can't find your agents:

```bash
# Run discovery to see what's being searched
agent-transfer discover

# This shows:
# - Where Claude Code is installed
# - Which directories are being searched
# - Whether agents are found
```

**Common causes:**
- No agents created yet - create at least one agent in Claude Code
- Agents in non-standard location - they should be in `~/.claude/agents/` or `.claude/agents/`
- Working directory issue - run from project root or specify path

**"Claude Code not found"**

During import, this is just a warning - agents will still be extracted:

```bash
# Install Claude Code if needed
npm install -g @anthropic-ai/claude-code

# Or continue anyway - agents extract to ~/.claude/agents/
```

### Export Issues

**"No agents selected"**

In interactive mode, you must select at least one agent:

- Type numbers (1, 2, 3) to toggle agents
- Type `a` to select all
- Press Enter to confirm
- Type `q` to quit

**"Interactive selection requires Python dependencies"**

The interactive UI needs the Rich library:

```bash
# Install with uv (isolated)
uv pip install -e .

# Or use --all flag to skip interactive selection
agent-transfer export --all my-backup.tar.gz
```

### Import Issues

**"Permission denied"**

You don't have write access to the agent directory:

```bash
# Check permissions
ls -la ~/.claude/

# Fix permissions
chmod u+w ~/.claude/agents/

# Or run with sudo (not recommended)
sudo agent-transfer import backup.tar.gz
```

**"File already exists" conflicts**

Agents with the same name already exist:

```bash
# Use conflict resolution modes:

# Interactive diff (default) - view changes and decide per file
agent-transfer import backup.tar.gz

# Overwrite all conflicts
agent-transfer import backup.tar.gz -c overwrite

# Keep existing files, skip conflicts
agent-transfer import backup.tar.gz -c keep

# Save as duplicates (agent_1.md, agent_2.md)
agent-transfer import backup.tar.gz -c duplicate
```

**"Corrupt archive" errors**

The tar.gz file is damaged:

```bash
# Verify archive integrity
tar -tzf backup.tar.gz

# If it lists files, the archive is valid
# If it errors, the file is corrupted - try re-exporting
```

### Web Viewer Issues

**"Port already in use"**

Another process is using port 7651:

```bash
# Use a different port
agent-transfer view --port 8080

# Or find and kill the process using 7651
lsof -i :7651
kill <PID>
```

**"Browser doesn't open automatically"**

Auto-open failed:

```bash
# Manually open browser
# Server address is shown in terminal output
# Usually: http://127.0.0.1:7651

# Or disable auto-open
agent-transfer view --no-browser
```

### Tool Validation Issues

**"validate-tools shows missing tools"**

Some agents require tools not available on your system:

```bash
# View detailed report
agent-transfer validate-tools --verbose

# Install missing MCP servers
# Check ~/.claude/mcp_servers.json for configuration

# Or only import compatible agents
```

**"MCP server not detected"**

The tool can't find your MCP server configuration:

```bash
# Check if MCP config exists
ls -la ~/.claude/mcp_servers.json

# Example MCP server config:
cat ~/.claude/mcp_servers.json
{
  "mcpServers": {
    "snowflake": {
      "command": "mcp-server-snowflake",
      "args": []
    }
  }
}
```

### Standalone Script Issues

**"agent-transfer.sh: Permission denied"**

The script isn't executable:

```bash
# Make executable
chmod +x agent-transfer.sh

# Or run with bash
bash agent-transfer.sh import backup.tar.gz
```

**"Python dependencies not found" during export**

The standalone script needs Python only for interactive export:

```bash
# Option 1: Install with uv
cd agent-transfer
./install.sh

# Option 2: Use --all flag (no Python needed)
./agent-transfer.sh export --all my-backup.tar.gz
```

### General Tips

1. **Always run discovery first** when troubleshooting:
   ```bash
   agent-transfer discover
   ```

2. **Check agent file format** - agents must be `.md` files with YAML frontmatter:
   ```yaml
   ---
   name: my-agent
   description: What it does
   tools: Read, Edit, Bash
   ---

   Agent instructions...
   ```

3. **Use verbose mode** for detailed output:
   ```bash
   agent-transfer validate-tools --verbose
   agent-transfer list-agents --discover
   ```

4. **Verify archive contents** before importing:
   ```bash
   tar -tzf backup.tar.gz
   ```

5. **Test with a single agent** first:
   ```bash
   # Export just one agent to test
   agent-transfer export test.tar.gz
   # (select one agent in interactive mode)
   ```

## Requirements

- Python 3.8+
- Claude Code (optional, for verification)

## Dependencies

- `rich` - Beautiful terminal UI
- `pyyaml` - YAML parsing for agent metadata
- `click` - CLI framework
- `fastapi` - Web framework for viewer
- `uvicorn` - ASGI server
- `markdown` - Markdown to HTML conversion
- `pygments` - Syntax highlighting
- `jinja2` - HTML templating (server-side template engine)
- `tailwindcss` - Modern CSS framework (via CDN for beautiful styling)

All dependencies are automatically installed when you install the package.

## Project Structure

```
agent-transfer/
├── agent_transfer/           # Main package
│   ├── __init__.py
│   ├── cli.py                # CLI entry point (Click commands)
│   ├── models.py             # Data models (Agent class)
│   ├── templates/            # HTML templates for web viewer
│   │   ├── index.html        # Main page with agent list
│   │   └── agent_view.html   # Agent detail view
│   └── utils/                # Utility modules
│       ├── __init__.py
│       ├── discovery.py       # Deep Claude Code discovery
│       ├── parser.py         # Agent file parsing
│       ├── selector.py       # Interactive selection UI (Rich)
│       ├── transfer.py       # Export/import logic
│       └── web_server.py     # FastAPI web server
├── agent-transfer.sh         # Standalone shell script (works without Python!)
├── install.sh                 # Automatic installation script (uv)
├── pyproject.toml            # Package configuration
├── requirements.txt          # Dependencies (for reference)
├── README.md                 # This file
├── STANDALONE_USAGE.md       # Standalone script usage guide
├── INSTALL.md                # Detailed installation guide
├── QUICK_START.md            # Quick reference
└── USER_STORIES.md           # User stories for all features
```

## Development

```bash
# Install in development mode
pip install -e .

# Run directly
python -m agent_transfer.cli export

# Or use the installed command
agent-transfer export
```

## Standalone Script Usage

The `agent-transfer.sh` script works **completely standalone** for import operations:

```bash
# On Machine A (with agent-transfer installed)
agent-transfer export my-agents.tar.gz --all

# On Machine B (NO INSTALLATION NEEDED!)
./agent-transfer.sh import my-agents.tar.gz
```

See [STANDALONE_USAGE.md](./STANDALONE_USAGE.md) for complete details.

## License

MIT
