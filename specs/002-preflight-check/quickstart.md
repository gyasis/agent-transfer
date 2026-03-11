# Quickstart: Preflight Check

**Branch**: `002-preflight-check` | **Date**: 2026-03-11

## Test Scenario 1: Standalone Preflight (Happy Path)

**Setup**: Create a mock archive with a `manifest.json` that lists known dependencies.

```bash
# Create mock manifest
mkdir -p /tmp/preflight-test
cat > /tmp/preflight-test/manifest.json << 'EOF'
{
  "manifest_version": "2.0",
  "source_platform": "claude-code",
  "source_os": "linux",
  "source_arch": "x86_64",
  "source_home": "/home/testuser",
  "contents": {"agents": ["test-agent.md"], "skills": [], "hooks": [], "configs": []},
  "dependencies": {
    "mcp_servers": [],
    "git_repos": [],
    "compiled_binaries": [],
    "skill_trees": [],
    "cli_tools": [
      {"name": "git", "required_by": ["test-agent.md"]},
      {"name": "nonexistent-tool-xyz", "required_by": ["test-agent.md"]}
    ],
    "env_vars": [
      {"name": "HOME", "critical": false, "required_by": ["test-agent.md"]},
      {"name": "FAKE_SECRET_KEY_XYZ", "critical": true, "required_by": ["test-agent.md"]}
    ],
    "docker": [],
    "python_packages": [],
    "sourced_files": []
  }
}
EOF

# Create test agent
echo "---\ntools: Read, Write\n---\nTest agent" > /tmp/preflight-test/test-agent.md

# Bundle as archive
cd /tmp/preflight-test && tar czf /tmp/test-archive.tar.gz manifest.json test-agent.md
```

**Run**:
```bash
agent-transfer preflight /tmp/test-archive.tar.gz
```

**Expected**:
- `git`: GREEN (installed)
- `nonexistent-tool-xyz`: RED (not found)
- `HOME`: GREEN (set)
- `FAKE_SECRET_KEY_XYZ`: RED (not set, critical)
- Exit code: 1

## Test Scenario 2: JSON Output

```bash
agent-transfer preflight /tmp/test-archive.tar.gz --json
```

**Expected**: Valid JSON with `overall_status: "FAIL"`, results array with status per item.

## Test Scenario 3: Legacy Archive (No Manifest)

```bash
# Create archive without manifest
cd /tmp && mkdir -p legacy-test
echo "---\ntools: Read\n---\nOld agent" > legacy-test/old-agent.md
tar czf /tmp/legacy-archive.tar.gz -C /tmp legacy-test/

agent-transfer preflight /tmp/legacy-archive.tar.gz
```

**Expected**: Warning "No manifest.json found — this archive was created before preflight support." Exit code: 0.

## Test Scenario 4: Self-Audit

```bash
agent-transfer preflight --self
```

**Expected**: Scans local `~/.claude/agents/`, `~/.claude/skills/`, MCP configs. Shows full dependency inventory with status for each item.

## Test Scenario 5: Export with Manifest

```bash
agent-transfer export -o /tmp/export-test.tar.gz
tar tzf /tmp/export-test.tar.gz | grep manifest.json
```

**Expected**: `manifest.json` appears in archive listing.

## Test Scenario 6: Import with Preflight Gate

```bash
# Import archive that has a missing dependency
agent-transfer import /tmp/test-archive.tar.gz
```

**Expected**: Readiness report shown. Prompted to continue (RED items present). `--force` bypasses prompt.

## Unit Test Quick-Check

```bash
cd /home/gyasisutton/dev/agent-transfer
python -m pytest tests/test_preflight.py -v
```

Key test cases:
- Manifest serialization round-trip (write → read = identical)
- Each checker function with mock data (GREEN/YELLOW/RED paths)
- Collector scanning against fixture agent/skill files
- Binary arch detection against known ELF bytes
- Git remote extraction against fixture `.git/config`
- `.preflight.yml` parsing with valid and malformed YAML
- Legacy archive handling (no manifest)
