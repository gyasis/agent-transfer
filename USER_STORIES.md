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

## Selective Import Scenarios

### US-013: Preview Before Import

**As a** developer working across multiple machines
**I want to** see what will change before importing agents
**So that** I can avoid overwriting my local work unnecessarily

**Acceptance Criteria:**
- ✅ Interactive preview shows NEW, CHANGED, and IDENTICAL agents
- ✅ Smart defaults: NEW + CHANGED pre-selected
- ✅ View diffs for CHANGED agents before importing
- ✅ Toggle selection per agent
- ✅ Filter by status (NEW/CHANGED/IDENTICAL)
- ✅ Confirm before import

**Example Flow:**
```bash
# Machine A: Export agents
agent-transfer export --all team-backup.tar.gz

# Machine B: Import with preview
agent-transfer import team-backup.tar.gz
# Preview shows:
#   5 NEW agents
#   3 CHANGED agents (with diff option)
#   7 IDENTICAL agents
# Review diffs with 'v' command
# Select desired agents
# Import safely
```

**User Benefit:** Developer can see that 3 agents changed since last sync, review the diffs to see if they're improvements or conflicts, and selectively import only the desired updates without blindly overwriting local work.

---

### US-014: Quick Single Agent Import

**As a** developer
**I want to** import just one specific agent from an archive
**So that** I don't have to browse through an entire backup

**Acceptance Criteria:**
- ✅ `--agent` flag imports specific agent by name
- ✅ No interactive selection needed
- ✅ Fast extraction of single agent
- ✅ Works with any backup archive

**Example:**
```bash
agent-transfer import backup.tar.gz --agent data-analyst
# Directly imports data-analyst.md
# Skips all other agents
```

**User Benefit:** Team member receives a backup with 50 agents but only needs the updated "data-analyst" agent. They can extract just that one without scrolling through the entire list.

---

### US-015: Multi-System Development Workflow

**As a** team member collaborating on agents
**I want to** merge agent improvements from colleagues
**So that** we can share work without conflicts

**Acceptance Criteria:**
- ✅ Preview shows which agents changed
- ✅ Filter to see only CHANGED agents
- ✅ View side-by-side diffs
- ✅ Selective import of improvements
- ✅ Keep local changes for some agents

**Example Flow:**
```bash
# Receive teammate's backup
agent-transfer import colleague-agents.tar.gz

# Preview shows:
#   2 NEW agents (new work)
#   5 CHANGED agents (improvements to existing)
#   10 IDENTICAL agents

# Use 'f' to filter CHANGED only
# Review each diff with 'v' and 's'
# Select improvements to merge
# Import selected agents
```

**User Benefit:** Developer receives updated agents from a colleague. The preview shows that 5 agents were improved. They review the diffs, see valuable improvements in 3 agents but want to keep their local versions of 2 others. They selectively import only the 3 improved agents.

---

### US-016: Safe Backup Restoration

**As a** developer restoring from backup
**I want to** see what's different from my current setup
**So that** I don't lose recent changes

**Acceptance Criteria:**
- ✅ Compare backup to current local agents
- ✅ Identify which backup agents are outdated
- ✅ Identify which backup agents are newer
- ✅ Selectively restore only what's needed

**Example:**
```bash
# Restore from last week's backup
agent-transfer import weekly-backup.tar.gz

# Preview detects:
#   0 NEW agents
#   8 CHANGED agents (backup is older than local)
#   15 IDENTICAL agents

# Review diffs - see local versions are newer
# Deselect all CHANGED agents
# Import nothing (keep current work)
```

**User Benefit:** Developer accidentally deleted their backup disk and starts fresh install. When importing their backup, they discover their local agents are actually newer than the backup. They safely skip the outdated backup versions.

---

### US-017: Bulk Import for Automation

**As a** DevOps engineer
**I want to** import agents in CI/CD without manual interaction
**So that** I can automate agent deployment

**Acceptance Criteria:**
- ✅ `--bulk` flag skips interactive preview
- ✅ Imports all agents automatically
- ✅ Works in non-interactive environments
- ✅ Suitable for scripts and automation

**Example:**
```bash
# In CI/CD pipeline
agent-transfer import production-agents.tar.gz --bulk
# All agents imported automatically
# No user interaction required
```

**User Benefit:** Automated deployment pipeline needs to provision agents to new developer machines. The bulk import flag allows the script to run without requiring manual selection.

---

### US-018: Incremental Agent Updates

**As a** developer maintaining agents across environments
**I want to** only import new or updated agents
**So that** I minimize unnecessary file operations

**Acceptance Criteria:**
- ✅ Smart detection of IDENTICAL agents
- ✅ Auto-deselect IDENTICAL agents
- ✅ Focus on NEW and CHANGED only
- ✅ Skip redundant imports

**Example:**
```bash
# Daily sync workflow
agent-transfer import daily-sync.tar.gz

# Preview auto-selects:
#   2 NEW agents ✓
#   1 CHANGED agent ✓
#   20 IDENTICAL agents ✗ (auto-deselected)

# Press enter to import only 3 agents
# Skip re-importing 20 unchanged agents
```

**User Benefit:** Developer syncs agents daily between work laptop and home desktop. Most agents are identical, so the preview automatically focuses on only the 3 that actually changed, saving time and avoiding unnecessary file writes.

---

## Success Metrics

- ✅ Users can transfer agents between machines with one command
- ✅ Standalone script works without Python installation
- ✅ Web viewer provides easy browsing experience
- ✅ Deep discovery finds Claude Code in 95%+ of installations
- ✅ Installation is one-command with uv
- ✅ No environment pollution from dependencies
- ✅ Interactive preview prevents accidental overwrites
- ✅ Selective import saves time on large agent collections
- ✅ Diff viewing enables informed merge decisions

