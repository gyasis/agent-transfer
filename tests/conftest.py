"""
Shared pytest fixtures for agent-transfer test suite.

Provides reusable fixtures for creating test archives, sample agents,
and temporary directories for isolated testing.
"""

import pytest
import tempfile
import tarfile
from pathlib import Path
from agent_transfer.models import Agent, AgentComparison, ImportPreview


@pytest.fixture
def temp_dir(tmp_path):
    """Create a temporary directory for test isolation."""
    return tmp_path


@pytest.fixture
def sample_agent():
    """Create a sample agent for testing."""
    return Agent(
        name="test-agent",
        description="Test agent for unit tests",
        file_path="/tmp/test-agent.md",
        agent_type="user",
        tools=["Read", "Edit", "Bash"],
        permission_mode="full",
        model="claude-sonnet-4-5",
        full_content="""---
name: test-agent
description: Test agent for unit tests
tools: Read, Edit, Bash
permissionMode: full
model: claude-sonnet-4-5
---

# Test Agent

This is a test agent used for unit testing.

## Purpose
Verify agent parsing and comparison logic.
"""
    )


@pytest.fixture
def sample_agent_modified():
    """Create a modified version of sample agent."""
    return Agent(
        name="test-agent",
        description="Test agent for unit tests (modified)",
        file_path="/tmp/test-agent.md",
        agent_type="user",
        tools=["Read", "Edit", "Bash", "WebSearch"],
        permission_mode="full",
        model="claude-sonnet-4-5",
        full_content="""---
name: test-agent
description: Test agent for unit tests (modified)
tools: Read, Edit, Bash, WebSearch
permissionMode: full
model: claude-sonnet-4-5
---

# Test Agent

This is a test agent used for unit testing.

## Purpose
Verify agent parsing and comparison logic.

## Modifications
This version includes additional tools and updated description.
"""
    )


@pytest.fixture
def sample_archive(tmp_path):
    """Create a sample tar.gz archive with test agents."""
    archive_dir = tmp_path / "archive_content"
    archive_dir.mkdir()

    # Create user-agents directory
    user_agents = archive_dir / "user-agents"
    user_agents.mkdir()

    # Create test agent file
    agent_file = user_agents / "test-agent.md"
    agent_file.write_text("""---
name: test-agent
description: Test agent from archive
tools: Read, Edit
permissionMode: full
---

# Test Agent
This is a test agent from an archive.
""")

    # Create another agent
    agent_file2 = user_agents / "another-agent.md"
    agent_file2.write_text("""---
name: another-agent
description: Another test agent
tools: Bash
---

# Another Agent
Another test agent for testing.
""")

    # Create project-agents directory
    project_agents = archive_dir / "project-agents"
    project_agents.mkdir()

    # Create project agent file
    project_agent_file = project_agents / "project-agent.md"
    project_agent_file.write_text("""---
name: project-agent
description: Project-specific test agent
tools: Read, Write
---

# Project Agent
Project-specific agent for testing.
""")

    # Create metadata file
    metadata_file = archive_dir / "metadata.txt"
    metadata_file.write_text("""Archive Information
===================
Export Date: 2025-01-10 12:00:00
Hostname: test-machine
User: test-user
Total Agents: 3
""")

    # Create archive
    archive_path = tmp_path / "test-archive.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(user_agents, arcname="user-agents")
        tar.add(project_agents, arcname="project-agents")
        tar.add(metadata_file, arcname="metadata.txt")

    return archive_path


@pytest.fixture
def empty_archive(tmp_path):
    """Create an empty archive with no agents."""
    archive_dir = tmp_path / "empty_archive"
    archive_dir.mkdir()

    # Create empty directories
    (archive_dir / "user-agents").mkdir()
    (archive_dir / "project-agents").mkdir()

    archive_path = tmp_path / "empty-archive.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(archive_dir / "user-agents", arcname="user-agents")
        tar.add(archive_dir / "project-agents", arcname="project-agents")

    return archive_path


@pytest.fixture
def corrupted_archive(tmp_path):
    """Create a corrupted archive file."""
    archive_path = tmp_path / "corrupted.tar.gz"
    archive_path.write_text("This is not a valid tar.gz file")
    return archive_path


@pytest.fixture
def local_agent_dir(tmp_path):
    """Create a temporary local agent directory structure."""
    # Create user agents directory
    user_agents = tmp_path / ".claude" / "agents"
    user_agents.mkdir(parents=True)

    # Create project agents directory
    project_agents = tmp_path / "project" / ".claude" / "agents"
    project_agents.mkdir(parents=True)

    return {
        "user": user_agents,
        "project": project_agents,
        "root": tmp_path
    }


@pytest.fixture
def sample_comparison_new(sample_agent):
    """Create a NEW agent comparison."""
    return AgentComparison(
        agent=sample_agent,
        status="NEW",
        local_path=None,
        local_content=None,
        archive_content=sample_agent.full_content,
        diff_summary=None
    )


@pytest.fixture
def sample_comparison_changed(sample_agent, sample_agent_modified):
    """Create a CHANGED agent comparison."""
    return AgentComparison(
        agent=sample_agent_modified,
        status="CHANGED",
        local_path=Path("/tmp/test-agent.md"),
        local_content=sample_agent.full_content,
        archive_content=sample_agent_modified.full_content,
        diff_summary="+3 -0 ~1"
    )


@pytest.fixture
def sample_comparison_identical(sample_agent):
    """Create an IDENTICAL agent comparison."""
    return AgentComparison(
        agent=sample_agent,
        status="IDENTICAL",
        local_path=Path("/tmp/test-agent.md"),
        local_content=sample_agent.full_content,
        archive_content=sample_agent.full_content,
        diff_summary=None
    )


@pytest.fixture
def sample_preview(sample_comparison_new, sample_comparison_changed, sample_comparison_identical):
    """Create a sample ImportPreview with mixed comparisons."""
    return ImportPreview(
        archive_path="/tmp/test-archive.tar.gz",
        metadata={
            "Export Date": "2025-01-10 12:00:00",
            "Hostname": "test-machine",
            "User": "test-user",
            "Total Agents": "3"
        },
        comparisons=[
            sample_comparison_new,
            sample_comparison_changed,
            sample_comparison_identical
        ],
        user_agents_count=2,
        project_agents_count=1,
        new_count=1,
        changed_count=1,
        identical_count=1
    )
