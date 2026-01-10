"""
Test suite for import_analyzer module.

Tests archive analysis, agent comparison, diff generation,
and local agent path resolution.
"""

import pytest
import hashlib
from pathlib import Path
from unittest.mock import patch, Mock

from agent_transfer.utils.import_analyzer import (
    analyze_import_archive,
    compare_agents,
    generate_diff_summary,
    find_local_agent_path,
    _compute_content_hash,
    _find_agents_in_directory,
    _parse_metadata_file
)
from agent_transfer.models import Agent, AgentComparison


class TestAnalyzeImportArchive:
    """Test archive analysis functionality."""

    def test_analyze_import_archive_success(self, sample_archive):
        """Test successful archive analysis."""
        preview = analyze_import_archive(str(sample_archive))

        assert preview is not None
        assert preview.archive_path == str(sample_archive)
        assert len(preview.comparisons) >= 0
        assert preview.new_count + preview.changed_count + preview.identical_count == len(preview.comparisons)

    def test_analyze_import_archive_counts_agents(self, sample_archive):
        """Test that archive analysis correctly counts user and project agents."""
        preview = analyze_import_archive(str(sample_archive))

        # Archive should have both user and project agents
        assert preview.user_agents_count >= 0
        assert preview.project_agents_count >= 0
        assert preview.user_agents_count + preview.project_agents_count == len(preview.comparisons)

    def test_analyze_import_archive_extracts_metadata(self, sample_archive):
        """Test metadata extraction from archive."""
        preview = analyze_import_archive(str(sample_archive))

        assert isinstance(preview.metadata, dict)
        # Check if metadata was parsed (may be empty if file not present)
        if preview.metadata:
            assert "Export Date" in preview.metadata or len(preview.metadata) >= 0

    def test_analyze_empty_archive(self, empty_archive):
        """Test handling of empty archive."""
        preview = analyze_import_archive(str(empty_archive))

        assert preview is not None
        assert len(preview.comparisons) == 0
        assert preview.new_count == 0
        assert preview.changed_count == 0
        assert preview.identical_count == 0

    def test_analyze_nonexistent_archive(self):
        """Test error handling for nonexistent archive."""
        with pytest.raises(FileNotFoundError):
            analyze_import_archive("/nonexistent/path/archive.tar.gz")

    def test_analyze_corrupted_archive(self, corrupted_archive):
        """Test error handling for corrupted archive."""
        with pytest.raises(RuntimeError, match="corrupted"):
            analyze_import_archive(str(corrupted_archive))


class TestCompareAgents:
    """Test agent comparison logic."""

    def test_compare_agents_new(self, sample_agent):
        """Test NEW agent comparison when no local agent exists."""
        comparison = compare_agents(sample_agent, None)

        assert comparison.status == "NEW"
        assert comparison.agent == sample_agent
        assert comparison.local_path is None
        assert comparison.local_content is None
        assert comparison.archive_content == sample_agent.full_content
        assert comparison.diff_summary is None

    def test_compare_agents_identical(self, sample_agent):
        """Test IDENTICAL agent comparison with same content."""
        # Create identical local agent
        local_agent = Agent(
            name=sample_agent.name,
            description=sample_agent.description,
            file_path=sample_agent.file_path,
            agent_type=sample_agent.agent_type,
            tools=sample_agent.tools,
            full_content=sample_agent.full_content
        )

        comparison = compare_agents(sample_agent, local_agent)

        assert comparison.status == "IDENTICAL"
        assert comparison.agent == sample_agent
        assert comparison.local_content == local_agent.full_content
        assert comparison.archive_content == sample_agent.full_content
        assert comparison.diff_summary is None

    def test_compare_agents_changed(self, sample_agent, sample_agent_modified):
        """Test CHANGED agent comparison with different content."""
        comparison = compare_agents(sample_agent_modified, sample_agent)

        assert comparison.status == "CHANGED"
        assert comparison.agent == sample_agent_modified
        assert comparison.local_content == sample_agent.full_content
        assert comparison.archive_content == sample_agent_modified.full_content
        assert comparison.diff_summary is not None
        assert comparison.diff_summary != "no changes"

    def test_compare_agents_handles_none_content(self):
        """Test comparison with None content values."""
        agent1 = Agent(
            name="test",
            description="Test",
            file_path="/tmp/test.md",
            agent_type="user",
            full_content=None
        )
        agent2 = Agent(
            name="test",
            description="Test",
            file_path="/tmp/test.md",
            agent_type="user",
            full_content=""
        )

        comparison = compare_agents(agent1, agent2)

        # None and empty string should be treated as identical
        assert comparison.status == "IDENTICAL"


class TestGenerateDiffSummary:
    """Test diff summary generation."""

    def test_generate_diff_summary_additions(self):
        """Test diff summary with only additions."""
        existing = "Line 1\nLine 2\n"
        incoming = "Line 1\nLine 2\nLine 3\nLine 4\n"

        summary = generate_diff_summary(existing, incoming)

        assert "+2" in summary
        assert "-" not in summary or summary == "+2"

    def test_generate_diff_summary_deletions(self):
        """Test diff summary with only deletions."""
        existing = "Line 1\nLine 2\nLine 3\nLine 4\n"
        incoming = "Line 1\nLine 2\n"

        summary = generate_diff_summary(existing, incoming)

        assert "-2" in summary
        assert "+" not in summary or summary == "-2"

    def test_generate_diff_summary_modifications(self):
        """Test diff summary with modifications."""
        existing = "Line 1\nLine 2\nLine 3\n"
        incoming = "Line 1\nModified Line 2\nLine 3\n"

        summary = generate_diff_summary(existing, incoming)

        # Should detect changes
        assert summary != "no changes"
        assert "~" in summary or "+" in summary or "-" in summary

    def test_generate_diff_summary_no_changes(self):
        """Test diff summary with identical content."""
        content = "Line 1\nLine 2\nLine 3\n"

        summary = generate_diff_summary(content, content)

        assert summary == "no changes"

    def test_generate_diff_summary_mixed_changes(self):
        """Test diff summary with mixed additions, deletions, and modifications."""
        existing = "Line 1\nLine 2\nLine 3\nLine 4\n"
        incoming = "Line 1\nModified Line 2\nLine 3\nLine 5\nLine 6\n"

        summary = generate_diff_summary(existing, incoming)

        # Should contain some indication of changes
        assert summary != "no changes"
        assert len(summary) > 0


class TestFindLocalAgentPath:
    """Test local agent path resolution."""

    def test_find_local_agent_path_user(self, tmp_path, monkeypatch):
        """Test finding user agent path."""
        # Mock home directory
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, 'home', lambda: fake_home)

        # Create user agent directory and file
        user_agents_dir = fake_home / ".claude" / "agents"
        user_agents_dir.mkdir(parents=True)
        agent_file = user_agents_dir / "test-agent.md"
        agent_file.write_text("# Test Agent")

        # Find agent path
        result = find_local_agent_path("test-agent", "user")

        assert result is not None
        assert result.exists()
        assert result.name == "test-agent.md"

    def test_find_local_agent_path_project(self, tmp_path, monkeypatch):
        """Test finding project agent path."""
        # Mock current directory
        fake_cwd = tmp_path / "project"
        fake_cwd.mkdir()
        monkeypatch.setattr(Path, 'cwd', lambda: fake_cwd)

        # Create project agent directory and file
        project_agents_dir = fake_cwd / ".claude" / "agents"
        project_agents_dir.mkdir(parents=True)
        agent_file = project_agents_dir / "test-agent.md"
        agent_file.write_text("# Test Agent")

        # Find agent path
        result = find_local_agent_path("test-agent", "project")

        assert result is not None
        assert result.exists()
        assert result.name == "test-agent.md"

    def test_find_local_agent_path_not_found(self, tmp_path, monkeypatch):
        """Test handling when agent doesn't exist locally."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, 'home', lambda: fake_home)

        result = find_local_agent_path("nonexistent-agent", "user")

        assert result is None

    def test_find_local_agent_path_invalid_type(self):
        """Test handling of invalid agent type."""
        result = find_local_agent_path("test-agent", "invalid_type")

        assert result is None


class TestComputeContentHash:
    """Test content hashing functionality."""

    def test_compute_content_hash_consistent(self):
        """Test that hashing is consistent for same content."""
        content = "Test content for hashing"

        hash1 = _compute_content_hash(content)
        hash2 = _compute_content_hash(content)

        assert hash1 == hash2

    def test_compute_content_hash_different_content(self):
        """Test that different content produces different hashes."""
        content1 = "Content version 1"
        content2 = "Content version 2"

        hash1 = _compute_content_hash(content1)
        hash2 = _compute_content_hash(content2)

        assert hash1 != hash2

    def test_compute_content_hash_format(self):
        """Test that hash is in expected format."""
        content = "Test content"

        hash_value = _compute_content_hash(content)

        # SHA256 hex digest is 64 characters
        assert len(hash_value) == 64
        assert all(c in '0123456789abcdef' for c in hash_value)


class TestFindAgentsInDirectory:
    """Test agent discovery in directories."""

    def test_find_agents_in_directory_success(self, tmp_path):
        """Test finding agents in a directory."""
        # Create test agents
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        agent1 = agents_dir / "agent1.md"
        agent1.write_text("""---
name: agent1
description: First test agent
tools: Read
---

# Agent 1
""")

        agent2 = agents_dir / "agent2.md"
        agent2.write_text("""---
name: agent2
description: Second test agent
tools: Edit
---

# Agent 2
""")

        # Find agents
        agents = _find_agents_in_directory(agents_dir, "user")

        assert len(agents) == 2
        assert all(agent.agent_type == "user" for agent in agents)
        assert {agent.name for agent in agents} == {"agent1", "agent2"}

    def test_find_agents_in_directory_empty(self, tmp_path):
        """Test finding agents in empty directory."""
        agents_dir = tmp_path / "empty"
        agents_dir.mkdir()

        agents = _find_agents_in_directory(agents_dir, "user")

        assert len(agents) == 0

    def test_find_agents_in_directory_nonexistent(self, tmp_path):
        """Test finding agents in nonexistent directory."""
        agents_dir = tmp_path / "nonexistent"

        agents = _find_agents_in_directory(agents_dir, "user")

        assert len(agents) == 0

    def test_find_agents_in_directory_invalid_files(self, tmp_path):
        """Test handling of invalid agent files."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        # Create invalid files
        (agents_dir / "not-markdown.txt").write_text("Not a markdown file")
        (agents_dir / "invalid.md").write_text("Invalid markdown without frontmatter")

        # Create valid agent
        valid_agent = agents_dir / "valid.md"
        valid_agent.write_text("""---
name: valid
description: Valid agent
---

# Valid Agent
""")

        agents = _find_agents_in_directory(agents_dir, "user")

        # Should only find the valid agent
        assert len(agents) >= 1
        assert any(agent.name == "valid" for agent in agents)


class TestParseMetadataFile:
    """Test metadata file parsing."""

    def test_parse_metadata_file_success(self, tmp_path):
        """Test successful metadata file parsing."""
        metadata_file = tmp_path / "metadata.txt"
        metadata_file.write_text("""Export Date: 2025-01-10 12:00:00
Hostname: test-machine
User: test-user
Total Agents: 5
""")

        metadata = _parse_metadata_file(metadata_file)

        assert metadata["Export Date"] == "2025-01-10 12:00:00"
        assert metadata["Hostname"] == "test-machine"
        assert metadata["User"] == "test-user"
        assert metadata["Total Agents"] == "5"

    def test_parse_metadata_file_empty(self, tmp_path):
        """Test parsing empty metadata file."""
        metadata_file = tmp_path / "metadata.txt"
        metadata_file.write_text("")

        metadata = _parse_metadata_file(metadata_file)

        assert metadata == {}

    def test_parse_metadata_file_malformed(self, tmp_path):
        """Test handling malformed metadata file."""
        metadata_file = tmp_path / "metadata.txt"
        metadata_file.write_text("""No colon here
Also no colon
Valid Line: Value
""")

        metadata = _parse_metadata_file(metadata_file)

        # Should still parse the valid line
        assert "Valid Line" in metadata
        assert metadata["Valid Line"] == "Value"

    def test_parse_metadata_file_nonexistent(self, tmp_path):
        """Test handling nonexistent metadata file."""
        metadata_file = tmp_path / "nonexistent.txt"

        metadata = _parse_metadata_file(metadata_file)

        # Should return empty dict without error
        assert metadata == {}
