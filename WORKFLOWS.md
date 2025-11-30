# Common Workflows

This guide shows practical, real-world workflows for using agent-transfer.

## Table of Contents

- [1. Transfer Agents Between Machines](#1-transfer-agents-between-machines)
- [2. Backup Before System Update](#2-backup-before-system-update)
- [3. Share Agents with Team](#3-share-agents-with-team)
- [4. Browse and Validate Agents](#4-browse-and-validate-agents)
- [5. Selective Agent Migration](#5-selective-agent-migration)
- [6. Emergency Restore](#6-emergency-restore)

---

## 1. Transfer Agents Between Machines

**Scenario:** Moving to a new development machine

### On Source Machine (Machine A)

```bash
# First, see what you have
agent-transfer list-agents

# Export all agents
agent-transfer export my-agents-backup.tar.gz --all

# Or selectively choose agents
agent-transfer export my-agents-backup.tar.gz
# (interactive selection)

# Copy these files to new machine:
# - my-agents-backup.tar.gz
# - agent-transfer.sh (optional, for standalone import)
```

### On Destination Machine (Machine B)

**Option 1: With agent-transfer installed**

```bash
# Install agent-transfer
cd agent-transfer
./install.sh

# Validate compatibility first
agent-transfer validate-tools --verbose

# Import agents
agent-transfer import my-agents-backup.tar.gz

# Verify import
agent-transfer list-agents
```

**Option 2: Standalone (no installation)**

```bash
# Just copy agent-transfer.sh and backup file
chmod +x agent-transfer.sh

# Import agents (works without Python!)
./agent-transfer.sh import my-agents-backup.tar.gz

# Agents are now in ~/.claude/agents/
```

---

## 2. Backup Before System Update

**Scenario:** Backing up before OS upgrade or system maintenance

```bash
# Step 1: Create timestamped backup
agent-transfer export backup-$(date +%Y%m%d).tar.gz --all

# Step 2: Verify backup contents
tar -tzf backup-20251130.tar.gz

# Step 3: Store backup safely
# - External drive
# - Cloud storage
# - Network location

# Step 4: After update, verify agents
agent-transfer list-agents

# Step 5: If needed, restore
agent-transfer import backup-20251130.tar.gz
```

---

## 3. Share Agents with Team

**Scenario:** Sharing custom agents with team members

### Create Team Agent Package

```bash
# Step 1: Export team-specific agents
agent-transfer export team-agents.tar.gz
# Select only agents suitable for sharing

# Step 2: Document what's included
tar -tzf team-agents.tar.gz > agent-list.txt

# Step 3: Share files
# - team-agents.tar.gz
# - agent-list.txt
# - agent-transfer.sh (for easy import)
```

### Team Member Import

```bash
# Step 1: Check compatibility
agent-transfer validate-tools --verbose

# Step 2: Review what will be imported
tar -tzf team-agents.tar.gz

# Step 3: Import with conflict handling
agent-transfer import team-agents.tar.gz -c keep
# This keeps your existing agents, only adds new ones

# Step 4: Verify import
agent-transfer list-agents
```

---

## 4. Browse and Validate Agents

**Scenario:** Reviewing agents before import or after changes

```bash
# Step 1: Launch web viewer
agent-transfer view
# Opens http://127.0.0.1:7651

# Step 2: Browse agents in browser
# - View markdown rendered as HTML
# - Check agent descriptions
# - Review tool requirements

# Step 3: Validate tool compatibility
agent-transfer validate-tools --verbose

# Example output:
# ✓ frontend-developer - All tools available
#   Tools: Read, Edit, Grep, Bash
#
# ✗ data-analyst - Missing tools
#   Available: Read, Edit, Bash
#   Missing: mcp__snowflake__read_query

# Step 4: Install missing MCP servers if needed
# Check ~/.claude/mcp_servers.json
```

---

## 5. Selective Agent Migration

**Scenario:** Moving only specific agents to a new project

```bash
# Step 1: Discover current setup
agent-transfer discover

# Shows:
# - Claude Code installation location
# - User agents: ~/.claude/agents/
# - Project agents: .claude/agents/

# Step 2: Export selective agents
agent-transfer export project-agents.tar.gz
# Select only project-relevant agents

# Step 3: Switch to new project directory
cd /path/to/new/project

# Step 4: Import as project agents
agent-transfer import project-agents.tar.gz

# Agents now in /path/to/new/project/.claude/agents/
```

---

## 6. Emergency Restore

**Scenario:** Accidentally deleted agents or configuration corrupted

```bash
# Step 1: Don't panic! Check what's actually there
agent-transfer list-agents

# Step 2: Find most recent backup
ls -lt *.tar.gz | head -5

# Step 3: Review backup contents
tar -tzf latest-backup.tar.gz

# Step 4: Restore with careful conflict handling
agent-transfer import latest-backup.tar.gz -c diff
# Interactive diff mode - review each conflict

# Or restore everything
agent-transfer import latest-backup.tar.gz -c overwrite

# Step 5: Verify restoration
agent-transfer list-agents
agent-transfer validate-tools
```

---

## Advanced Workflows

### Maintaining Multiple Agent Sets

```bash
# Separate backups for different purposes
agent-transfer export work-agents.tar.gz
# (select work-related agents)

agent-transfer export personal-agents.tar.gz
# (select personal agents)

agent-transfer export experimental-agents.tar.gz
# (select experimental/test agents)

# Restore specific set as needed
agent-transfer import work-agents.tar.gz -c keep
```

### Pre-Import Validation Pipeline

```bash
# Complete validation before importing
#!/bin/bash

BACKUP_FILE="$1"

echo "Step 1: Verify archive integrity"
tar -tzf "$BACKUP_FILE" || exit 1

echo "Step 2: Check current system compatibility"
agent-transfer validate-tools --verbose

echo "Step 3: Review conflicts"
agent-transfer import "$BACKUP_FILE" -c keep --dry-run
# (if --dry-run existed)

echo "Step 4: Proceed with import"
agent-transfer import "$BACKUP_FILE" -c diff
```

### Version Control Integration

```bash
# For project-level agents
cd /path/to/project

# Export project agents
agent-transfer export project-agents-v1.tar.gz --all

# Add to git
git add .claude/agents/
git commit -m "feat: Add Claude Code agents for project"

# Team members can clone and have agents ready
git clone <repo>
cd <repo>
# Agents automatically available in .claude/agents/
```

---

## Troubleshooting Common Workflow Issues

### Issue: Import Fails with Permission Error

```bash
# Check permissions
ls -la ~/.claude/

# Fix permissions
chmod u+w ~/.claude/agents/

# Retry import
agent-transfer import backup.tar.gz
```

### Issue: Agents Not Showing After Import

```bash
# Verify import location
agent-transfer discover

# Check if agents are in correct location
ls -la ~/.claude/agents/
ls -la .claude/agents/

# Verify file format
head -20 ~/.claude/agents/my-agent.md
# Should show YAML frontmatter
```

### Issue: MCP Tools Not Available

```bash
# Check MCP server configuration
cat ~/.claude/mcp_servers.json

# Install missing MCP server
npm install -g @modelcontextprotocol/server-<name>

# Update configuration
# Edit ~/.claude/mcp_servers.json

# Validate again
agent-transfer validate-tools --verbose
```

---

## Best Practices

1. **Regular Backups**: Schedule weekly exports
   ```bash
   # Cron job (every Sunday at 2 AM)
   0 2 * * 0 /path/to/agent-transfer export ~/backups/agents-$(date +\%Y\%m\%d).tar.gz --all
   ```

2. **Descriptive Filenames**: Use dates and purposes
   ```bash
   agent-transfer export agents-before-migration-20251130.tar.gz
   ```

3. **Validate Before Import**: Always check compatibility
   ```bash
   agent-transfer validate-tools --verbose
   ```

4. **Test Imports**: Use conflict modes carefully
   ```bash
   # First time: use 'keep' to be safe
   agent-transfer import backup.tar.gz -c keep

   # Review what was skipped, then decide
   agent-transfer import backup.tar.gz -c diff
   ```

5. **Document Agent Dependencies**: Note MCP servers needed
   ```bash
   # Create README for agent package
   echo "Required MCP Servers:" > AGENT_README.txt
   agent-transfer validate-tools --verbose >> AGENT_README.txt
   ```

6. **Version Your Exports**: Keep multiple backups
   ```bash
   agent-transfer export agents-v1.0.tar.gz
   agent-transfer export agents-v1.1.tar.gz
   # Keep version history
   ```

---

## Quick Reference

| Task | Command |
|------|---------|
| Quick backup all | `agent-transfer export --all` |
| Selective export | `agent-transfer export` |
| Import safely | `agent-transfer import backup.tar.gz -c keep` |
| Import with review | `agent-transfer import backup.tar.gz -c diff` |
| Check compatibility | `agent-transfer validate-tools --verbose` |
| Browse agents | `agent-transfer view` |
| List agents | `agent-transfer list-agents` |
| Find installation | `agent-transfer discover` |
| Verify archive | `tar -tzf backup.tar.gz` |
