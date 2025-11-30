# Agent Transfer Script

A simple script to export and import Claude Code agents between systems.

## Quick Start

### Export Agents

**Interactive Selection (Default - Recommended):**
```bash
# Interactive selection with beautiful UI
./agent-transfer.sh export

# Interactive with custom filename
./agent-transfer.sh export my-agents-backup.tar.gz
```

**Export All Agents:**
```bash
# Export all agents without selection
./agent-transfer.sh export --all

# Export all with custom filename
./agent-transfer.sh export my-agents-backup.tar.gz --all
```

**Interactive Selection Features:**
- Beautiful terminal UI with Rich library
- Shows agent name, description, type (user/project), and tools
- Select specific agents by number
- Select all agents with 'a'
- View detailed information with 'i'
- Ordered list with checkboxes

**First Time Setup:**

**Recommended (Isolated - No Environment Pollution):**
```bash
# Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# That's it! uv automatically handles dependencies in isolated environment
# No need to install anything to your Python environment
```

**Alternative (Traditional):**
```bash
# Install Python dependencies to your environment
./agent-transfer.sh install-deps
```

This will:
- Launch interactive selector (if dependencies installed)
- Show all available agents with summaries
- Let you select specific agents or all
- Create a compressed archive with selected agents
- Include metadata about the backup

### Import Agents

```bash
# Import agents from backup file
./agent-transfer.sh import claude-agents-backup_20250101_120000.tar.gz
```

This will:
- **Auto-detect** if Claude Code is installed
- Extract agents to the correct locations:
  - User-level agents → `~/.claude/agents/`
  - Project-level agents → `.claude/agents/` (in current directory)
- Handle conflicts (asks before overwriting)
- Verify the import

## Examples

### Example 1: Backup Before System Migration

```bash
# On old system
./agent-transfer.sh export my-agents-backup.tar.gz

# Transfer file to new system (USB, network, etc.)

# On new system
./agent-transfer.sh import my-agents-backup.tar.gz
```

### Example 2: Share Agents with Team

```bash
# Export your agents
./agent-transfer.sh export team-agents.tar.gz

# Share the file (email, shared drive, etc.)

# Team members import
./agent-transfer.sh import team-agents.tar.gz
```

### Example 3: Backup Before Updating Agents

```bash
# Create backup
./agent-transfer.sh export backup-before-update.tar.gz

# Make changes to agents...

# If something goes wrong, restore
./agent-transfer.sh import backup-before-update.tar.gz
```

## What Gets Exported?

- **User-level agents**: `~/.claude/agents/*.md`
- **Project-level agents**: `.claude/agents/*.md` (in current and parent directories)
- **Metadata**: System info, timestamp, export version

## What Gets Imported?

- Agents are restored to their original locations
- User-level agents go to `~/.claude/agents/`
- Project-level agents go to `.claude/agents/` in the current directory

## Conflict Handling

If an agent with the same name already exists:
- The script will warn you
- Ask if you want to overwrite
- You can choose to skip or overwrite

## Requirements

- **Bash** (comes with Linux/macOS, use Git Bash on Windows)
- **tar** and **gzip** (standard on Unix systems)
- **Claude Code** (optional for export, recommended for import)

**For Interactive Selection (choose one):**
- **uv** (recommended) - Automatically handles dependencies in isolated environment
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Python 3 + pip** - Install dependencies manually
  ```bash
  ./agent-transfer.sh install-deps
  ```

## Troubleshooting

### "No agent directories found"
- Make sure you've created at least one agent
- Check that agents are in `~/.claude/agents/` or `.claude/agents/`

### "Claude Code not found" (during import)
- This is just a warning - agents will still be extracted
- Install Claude Code: `npm install -g @anthropic-ai/claude-code`
- The script will continue and extract agents anyway

### "Permission denied"
- Make the script executable: `chmod +x agent-transfer.sh`
- Or run with: `bash agent-transfer.sh export`

### Import doesn't work
- Check that the backup file is valid: `tar -tzf backup-file.tar.gz`
- Verify file permissions
- Make sure you have write access to `~/.claude/agents/`

## Advanced Usage

### Export only user-level agents

The script automatically includes both, but you can manually extract just user-level:

```bash
tar -xzf backup.tar.gz
cp user-agents/*.md ~/.claude/agents/
```

### Export only project-level agents

```bash
tar -xzf backup.tar.gz
cp -r project-agents/.claude/agents/ .claude/
```

### View backup contents without importing

```bash
tar -tzf backup-file.tar.gz
```

## File Structure

The backup archive contains:
```
backup.tar.gz
├── metadata.txt          # Backup information
├── user-agents/          # User-level agents
│   ├── agent1.md
│   └── agent2.md
└── project-agents/       # Project-level agents
    └── .claude/agents/
        └── agent3.md
```

## Interactive Selection Guide

When you run `./agent-transfer.sh export`, you'll see:

1. **Agent Table**: Shows all available agents with:
   - Checkbox (✓) for selected agents
   - Number for quick selection
   - Agent name
   - Description (truncated if long)
   - Type (User/Project)
   - Tools list

2. **Controls**:
   - Type a number (1-N) to toggle that agent
   - Type `a` to select all agents
   - Type `d` to deselect all agents
   - Type `i` then a number to view agent details
   - Press Enter to confirm selection
   - Type `q` to quit

3. **Example Session**:
   ```
   Available Claude Code Agents
   ┌───┬─────┬─────────────────────────┬──────────────────────────────────┬──────────┬────────────────────┐
   │ ✓ │  #  │ Name                    │ Description                      │ Type     │ Tools              │
   ├───┼─────┼─────────────────────────┼──────────────────────────────────┼──────────┼────────────────────┤
   │ ✓ │  1  │ frontend-developer      │ Build modern, responsive...      │ Project  │ Read, Edit, Grep   │
   │   │  2  │ backend-developer       │ Develop robust backend systems... │ User     │ Read, Edit, Bash   │
   │ ✓ │  3  │ production-validator    │ Automatically reviews code...      │ Project  │ Read, Grep, Glob   │
   └───┴─────┴─────────────────────────┴──────────────────────────────────┴──────────┴────────────────────┘
   ```

## Tips

1. **Interactive Selection**: Use interactive mode to select only the agents you need
2. **Regular Backups**: Run export periodically to keep backups current
3. **Version Control**: Consider committing project-level agents to Git
4. **Naming**: Use descriptive filenames with dates: `agents-2025-01-15.tar.gz`
5. **Verification**: After import, verify with `claude` then `/agents list`
6. **Dependencies**: 
   - **Recommended**: Use `uv` - automatically handles dependencies in isolated environment
   - **Alternative**: Run `./agent-transfer.sh install-deps` to install to your Python environment

## See Also

- [Complete Agent Guide](./CLAUDE_CODE_AGENTS_GUIDE.md)
- [Claude Code Documentation](https://docs.anthropic.com/claude-code)

