# Installation Guide

## Quick Install (Automatic - Uses uv)

```bash
# One command - automatically uses uv for isolation
cd agent-transfer
./install.sh

# That's it! Dependencies are isolated from your environment
```

The install script:
- ✅ Checks if uv is installed (installs it if needed)
- ✅ Uses uv for isolated installation
- ✅ Keeps your Python environment clean
- ✅ No manual steps needed

## Installation Methods

### Method 1: uv (Recommended - Isolated Environment)

```bash
# Development installation
uv pip install -e .

# Global installation
uv pip install .
```

**Benefits:**
- ✅ Dependencies isolated from your Python environment
- ✅ Fast installation
- ✅ No environment pollution
- ✅ Works with any Python version

### Method 2: pip

```bash
# Development installation
pip install -e .

# Global installation
pip install .
```

### Method 3: uvx (Run without installation)

```bash
# Run directly without installing
uvx agent-transfer export

# Or install first, then use normally
uv pip install -e .
agent-transfer export
```

## Verify Installation

```bash
# Check version
agent-transfer --version

# Discover Claude Code installation
agent-transfer discover

# List agents
agent-transfer list-agents
```

## Troubleshooting

### "command not found: agent-transfer"

After installation, make sure the installation directory is in your PATH:

```bash
# Check where it was installed
python -m pip show agent-transfer

# Or with uv
uv pip show agent-transfer
```

### "Claude Code not found"

Run the discovery command to see where agent-transfer is looking:

```bash
agent-transfer discover
```

This will show:
- All searched locations
- Installation type (npm-global, virtualenv, conda, etc.)
- Agent directories found

### Dependencies Issues

If you see import errors:

```bash
# With uv (recommended)
uv pip install -e .

# Or with pip
pip install -r requirements.txt
```

## Development Setup

```bash
# Clone/navigate to directory
cd agent-transfer

# Install in development mode with uv
uv pip install -e ".[dev]"

# Or with pip
pip install -e ".[dev]"
```

## Uninstallation

```bash
# With uv
uv pip uninstall agent-transfer

# Or with pip
pip uninstall agent-transfer
```

