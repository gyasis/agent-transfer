# Quick Start Guide

## Installation (One Command - Automatic Isolation)

```bash
# Navigate to agent-transfer directory
cd agent-transfer

# Run install script (automatically uses uv)
./install.sh
```

**That's it!** The script:
- ✅ Automatically uses `uv` for isolated installation
- ✅ Keeps your Python environment clean
- ✅ Installs dependencies in isolation
- ✅ Creates the `agent-transfer` command

## Basic Usage

```bash
# Discover where Claude Code is installed
agent-transfer discover

# Export agents (interactive selection)
agent-transfer export

# Export all agents
agent-transfer export --all

# Import agents
agent-transfer import backup.tar.gz

# List agents
agent-transfer list-agents

# Launch web viewer (beautiful HTML interface)
agent-transfer view

# Validate tool compatibility
agent-transfer validate-tools
```

## Why uv?

**Isolated Installation:**
- Dependencies don't pollute your Python environment
- No conflicts with other packages
- Fast and reliable
- Automatic dependency resolution

**Your Python environment stays clean!** 🎉

## Manual Installation (if needed)

If you prefer to install manually:

```bash
# Install uv (if not installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install agent-transfer with uv
cd agent-transfer
uv pip install -e .
```

## Verify Installation

```bash
agent-transfer --version
agent-transfer discover
```
