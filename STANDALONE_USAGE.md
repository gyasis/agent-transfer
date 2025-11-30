# Standalone Usage Guide

## Quick Start - No Installation Needed!

The `agent-transfer.sh` script works **completely standalone** for import operations. No Python package installation required!

## Workflow

### Machine A (Export - with agent-transfer installed)

```bash
# Install agent-transfer (one time)
cd agent-transfer
./install.sh

# Export agents
agent-transfer export my-agents.tar.gz --all
```

### Machine B (Import - NO INSTALLATION NEEDED!)

```bash
# Just copy these two files:
# 1. agent-transfer.sh (this script)
# 2. my-agents.tar.gz (the backup file)

# Make script executable
chmod +x agent-transfer.sh

# Import agents - works standalone!
./agent-transfer.sh import my-agents.tar.gz
```

**That's it!** No Python, no dependencies, no installation needed for import!

## What Works Standalone

### ✅ Import (Fully Standalone)
- **No dependencies required**
- **No Python needed**
- **No installation needed**
- Just bash + tar (standard on all Unix systems)

### ✅ Export with --all (Fully Standalone)
```bash
./agent-transfer.sh export --all my-agents.tar.gz
```
- Exports all agents
- No Python needed
- Just bash commands

### ⚙️ Interactive Export (Optional - Requires Python)
```bash
./agent-transfer.sh export my-agents.tar.gz
```
- Beautiful interactive UI
- Requires Python + rich library
- Or use `--all` flag for standalone export

## Standalone Import Features

- ✅ Extracts `.tar.gz` files
- ✅ Detects Claude Code installation
- ✅ Creates `~/.claude/agents/` if needed
- ✅ Creates `.claude/agents/` for project agents
- ✅ Handles conflicts (asks before overwriting)
- ✅ Preserves agent metadata
- ✅ Verifies imported agents

## Requirements for Standalone Import

**None!** Just:
- Bash (comes with Linux/macOS)
- `tar` and `gzip` (standard on Unix systems)

That's it! No Python, no dependencies, no installation.

## Example: Transfer Between Machines

```bash
# On Machine A (source)
agent-transfer export team-agents.tar.gz --all

# Copy to Machine B:
# 1. Copy agent-transfer.sh
# 2. Copy team-agents.tar.gz

# On Machine B (destination - NO INSTALL NEEDED!)
chmod +x agent-transfer.sh
./agent-transfer.sh import team-agents.tar.gz

# Done! Agents are now in ~/.claude/agents/
```

## Why This Works

The import function uses only standard Unix tools:
- `tar` - Extract archive
- `find` - Find agent files
- `cp` - Copy files
- `mkdir` - Create directories
- `bash` - Script execution

No Python, no dependencies, no installation required!

