# User Stories

## Overview

This document describes user stories for all features in the Agent Transfer tool.

## Core Features

### US-001: Export Agents with Interactive Selection

**As a** developer with multiple Claude Code agents  
**I want to** selectively export specific agents with a beautiful interactive interface  
**So that** I can choose exactly which agents to transfer without exporting everything

**Acceptance Criteria:**
- ✅ Interactive terminal UI with Rich library
- ✅ Shows agent name, description, type (user/project), and tools
- ✅ Numbered list for easy selection
- ✅ Toggle agents by number
- ✅ Select all / deselect all options
- ✅ View detailed agent information
- ✅ Creates `.tar.gz` archive with selected agents

**Example:**
```bash
agent-transfer export
# Beautiful table appears
# Select agents: 1, 3, 5
# Creates claude-agents-backup_TIMESTAMP.tar.gz
```

---

### US-002: Export All Agents (Quick Export)

**As a** developer  
**I want to** export all agents at once without selection  
**So that** I can quickly backup everything

**Acceptance Criteria:**
- ✅ `--all` flag exports all agents
- ✅ No interactive selection needed
- ✅ Works standalone (no Python dependencies)
- ✅ Creates timestamped `.tar.gz` file

**Example:**
```bash
agent-transfer export --all my-backup.tar.gz
```

---

### US-003: Import Agents (Standalone)

**As a** developer on a new machine  
**I want to** import agents using just the shell script  
**So that** I don't need to install the Python package

**Acceptance Criteria:**
- ✅ Works with just `agent-transfer.sh` script
- ✅ No Python package installation required
- ✅ Extracts `.tar.gz` files
- ✅ Places agents in correct locations (`~/.claude/agents/` or `.claude/agents/`)
- ✅ Handles conflicts (asks before overwriting)
- ✅ Verifies import success

**Example:**
```bash
# Just copy agent-transfer.sh and backup.tar.gz
./agent-transfer.sh import backup.tar.gz
# Agents installed to ~/.claude/agents/
```

---

### US-004: Deep Discovery of Claude Code Installation

**As a** developer  
**I want to** find Claude Code even if it's in a virtual environment or custom location  
**So that** the tool works regardless of how Claude Code was installed

**Acceptance Criteria:**
- ✅ Searches PATH
- ✅ Searches npm global installations
- ✅ Searches virtual environments (venv, .venv, env)
- ✅ Searches conda environments
- ✅ Searches system and user installations
- ✅ Searches custom locations
- ✅ Identifies installation type
- ✅ Finds agent directories relative to installation

**Example:**
```bash
agent-transfer discover
# Shows:
# - Executable location
# - Installation type (npm-global, virtualenv, conda, etc.)
# - Config directory
# - Agent directories found
```

---

### US-005: List All Available Agents

**As a** developer  
**I want to** see all my agents without exporting  
**So that** I can quickly see what agents I have

**Acceptance Criteria:**
- ✅ Lists all agents in a table
- ✅ Shows name, description, type, tools
- ✅ Organized by user/project type
- ✅ Optional discovery info with `--discover` flag

**Example:**
```bash
agent-transfer list-agents
# Beautiful table with all agents
```

---

### US-006: Web Viewer for Browsing Agents

**As a** developer  
**I want to** browse agents in a web browser with beautiful HTML rendering  
**So that** I can easily read and navigate agent files

**Acceptance Criteria:**
- ✅ Launches FastAPI web server
- ✅ Sidebar navigation with all agents
- ✅ Markdown files rendered as HTML
- ✅ Syntax highlighting for code blocks
- ✅ Auto-opens browser
- ✅ Responsive design with Tailwind CSS
- ✅ Click agents in sidebar to view details

**Example:**
```bash
agent-transfer view
# Opens http://127.0.0.1:7651
# Beautiful web interface
# Click agents to view markdown rendered as HTML
```

---

### US-007: Isolated Installation with uv

**As a** developer  
**I want to** install the package without polluting my Python environment  
**So that** dependencies don't conflict with other projects

**Acceptance Criteria:**
- ✅ Uses `uv` for isolated installation
- ✅ Dependencies installed in isolated environment
- ✅ No pollution of system Python
- ✅ Automatic dependency management
- ✅ One-command install script

**Example:**
```bash
./install.sh
# Installs with uv
# Dependencies isolated
# Python environment stays clean
```

---

### US-008: Standalone Shell Script for Import

**As a** developer on a machine without Python package installed  
**I want to** use just the shell script to import agents  
**So that** I can transfer agents without installing anything

**Acceptance Criteria:**
- ✅ Script works with only bash + tar
- ✅ No Python dependencies needed
- ✅ No package installation required
- ✅ Extracts and places agents correctly
- ✅ Handles conflicts intelligently

**Example:**
```bash
# Machine A: agent-transfer export agents.tar.gz --all
# Machine B: ./agent-transfer.sh import agents.tar.gz
# No installation needed on Machine B!
```

---

### US-009: Smart Agent Directory Detection

**As a** developer  
**I want to** the tool to automatically find agent directories  
**So that** I don't have to specify paths manually

**Acceptance Criteria:**
- ✅ Finds `~/.claude/agents/` (user-level)
- ✅ Finds `.claude/agents/` in current/project directories
- ✅ Searches parent directories (up to 5 levels)
- ✅ Finds agents in virtual environment contexts
- ✅ Works with any Claude Code installation type

**Example:**
```bash
agent-transfer export
# Automatically finds agents in:
# - ~/.claude/agents/
# - .claude/agents/ (current and parents)
# - venv/.claude/agents/ (if in venv)
```

---

### US-010: Beautiful Terminal UI

**As a** developer  
**I want to** see a beautiful, easy-to-use terminal interface  
**So that** selecting agents is intuitive and pleasant

**Acceptance Criteria:**
- ✅ Rich library for beautiful tables
- ✅ Color-coded agent types
- ✅ Checkboxes for selection
- ✅ Clear instructions
- ✅ Agent details view
- ✅ Status indicators

**Example:**
```bash
agent-transfer export
# Beautiful table with:
# ✓ Checkboxes
# Color-coded types
# Clear instructions
```

---

### US-011: Markdown Rendering in Web Viewer

**As a** developer  
**I want to** see agent markdown files rendered as beautiful HTML  
**So that** I can easily read agent documentation and code

**Acceptance Criteria:**
- ✅ Markdown converted to HTML
- ✅ Syntax highlighting for code blocks
- ✅ Tables rendered properly
- ✅ GitHub-style markdown rendering
- ✅ Responsive layout

**Example:**
```bash
agent-transfer view
# Click agent in sidebar
# Markdown rendered as beautiful HTML
# Code blocks syntax highlighted
```

---

### US-012: Conflict Handling

**As a** developer importing agents  
**I want to** be warned about conflicts and choose to overwrite  
**So that** I don't accidentally lose existing agents

**Acceptance Criteria:**
- ✅ Detects existing agents with same name
- ✅ Prompts before overwriting
- ✅ Shows which agents conflict
- ✅ Option to skip conflicting agents
- ✅ Option to overwrite all

**Example:**
```bash
./agent-transfer.sh import backup.tar.gz
# Warning: agent-name.md already exists
# Overwrite? (y/N)
```

---

## User Workflows

### Workflow 1: Transfer Agents Between Machines

1. **Machine A (Source):**
   ```bash
   agent-transfer export team-agents.tar.gz --all
   ```

2. **Transfer Files:**
   - Copy `team-agents.tar.gz`
   - Copy `agent-transfer.sh` (optional - for standalone import)

3. **Machine B (Destination):**
   ```bash
   # Option 1: With agent-transfer installed
   agent-transfer import team-agents.tar.gz
   
   # Option 2: Standalone (no installation)
   ./agent-transfer.sh import team-agents.tar.gz
   ```

**Result:** Agents installed in correct locations on Machine B.

---

### Workflow 2: Browse Agents Locally

1. **Launch Web Viewer:**
   ```bash
   agent-transfer view
   ```

2. **Browse:**
   - See all agents in sidebar
   - Click agent to view details
   - Read markdown rendered as HTML
   - Navigate between agents

**Result:** Easy browsing and reading of agent files.

---

### Workflow 3: Selective Backup Before Update

1. **Discover Current Setup:**
   ```bash
   agent-transfer discover
   ```

2. **Selective Export:**
   ```bash
   agent-transfer export pre-update-backup.tar.gz
   # Select only important agents
   ```

3. **After Update:**
   ```bash
   agent-transfer import pre-update-backup.tar.gz
   ```

**Result:** Only important agents restored.

---

## Technical Stories

### TS-001: Utils Folder Organization

**As a** developer maintaining the codebase  
**I want to** have utility modules organized in a `utils/` folder  
**So that** the codebase is clean and maintainable

**Implementation:**
- ✅ `utils/discovery.py` - Claude Code discovery
- ✅ `utils/parser.py` - Agent file parsing
- ✅ `utils/selector.py` - Interactive UI
- ✅ `utils/transfer.py` - Export/import logic
- ✅ `utils/web_server.py` - FastAPI server

---

### TS-002: Deep Installation Discovery

**As a** developer  
**I want to** the tool to find Claude Code in any installation type  
**So that** it works regardless of how Claude Code was installed

**Implementation:**
- ✅ Multiple search strategies
- ✅ Virtual environment detection
- ✅ npm global detection
- ✅ Conda environment detection
- ✅ System/user installation detection

---

### TS-003: Isolated Dependencies

**As a** developer  
**I want to** use uv for dependency isolation  
**So that** my Python environment stays clean

**Implementation:**
- ✅ `uv pip install` for installation
- ✅ Automatic dependency management
- ✅ Isolated environment
- ✅ No system Python pollution

---

## Success Metrics

- ✅ Users can transfer agents between machines with one command
- ✅ Standalone script works without Python installation
- ✅ Web viewer provides easy browsing experience
- ✅ Deep discovery finds Claude Code in 95%+ of installations
- ✅ Installation is one-command with uv
- ✅ No environment pollution from dependencies

