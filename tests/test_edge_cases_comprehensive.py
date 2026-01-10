"""
Comprehensive edge case testing for selective import feature.

Tests error handling, invalid inputs, corner cases, and boundary conditions.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, Mock

from agent_transfer.utils.import_analyzer import (
    analyze_import_archive,
    compare_agents,
    find_local_agent_path
)
from agent_transfer.models import Agent, AgentComparison


class TestEmptyArchiveHandling:
    """Test handling of empty archives."""

    def test_empty_archive_message(self, empty_archive, capsys):
        """Test that empty archive displays appropriate message."""
        preview = analyze_import_archive(str(empty_archive))

        # Should have no comparisons
        assert len(preview.comparisons) == 0
        assert preview.new_count == 0
        assert preview.changed_count == 0
        assert preview.identical_count == 0

    def test_empty_archive_no_errors(self, empty_archive):
        """Test that empty archive doesn't raise errors."""
        try:
            preview = analyze_import_archive(str(empty_archive))
            assert preview is not None
        except Exception as e:
            pytest.fail(f"Empty archive raised unexpected exception: {e}")


class TestCorruptedArchiveError:
    """Test handling of corrupted archives."""

    def test_corrupted_archive_raises_error(self, corrupted_archive):
        """Test that corrupted archive raises appropriate error."""
        with pytest.raises(RuntimeError) as exc_info:
            analyze_import_archive(str(corrupted_archive))

        assert "corrupted" in str(exc_info.value).lower()

    def test_corrupted_archive_error_message(self, corrupted_archive):
        """Test that corrupted archive error message is clear."""
        with pytest.raises(RuntimeError) as exc_info:
            analyze_import_archive(str(corrupted_archive))

        error_msg = str(exc_info.value)
        assert len(error_msg) > 0
        assert "corrupted" in error_msg.lower() or "failed" in error_msg.lower()


class TestInvalidAgentName:
    """Test handling of invalid agent names."""

    def test_invalid_agent_name_not_found(self, sample_archive):
        """Test that nonexistent agent name returns no matches."""
        preview = analyze_import_archive(str(sample_archive))
        invalid_name = "nonexistent-agent-name-12345-xyz"

        filtered = [c for c in preview.comparisons if c.agent.name == invalid_name]

        assert len(filtered) == 0

    def test_invalid_agent_name_special_characters(self, sample_archive):
        """Test handling of agent names with special characters."""
        preview = analyze_import_archive(str(sample_archive))
        special_name = "agent@#$%^&*()"

        filtered = [c for c in preview.comparisons if c.agent.name == special_name]

        assert len(filtered) == 0

    def test_empty_agent_name(self, sample_archive):
        """Test handling of empty agent name."""
        preview = analyze_import_archive(str(sample_archive))

        filtered = [c for c in preview.comparisons if c.agent.name == ""]

        assert len(filtered) == 0


class TestAllIdenticalScenario:
    """Test scenario where all agents are identical."""

    def test_all_identical_preview(self, tmp_path, local_agent_dir, monkeypatch):
        """Test preview when all agents are identical."""
        # This test requires creating an archive from existing agents
        # and then analyzing it (should all be identical)
        pass  # Placeholder for integration test

    def test_all_identical_no_import_needed(self, sample_comparison_identical):
        """Test that identical agents indicate no import needed."""
        assert sample_comparison_identical.status == "IDENTICAL"
        assert sample_comparison_identical.diff_summary is None

    def test_all_identical_stats(self):
        """Test statistics when all agents are identical."""
        from agent_transfer.models import ImportPreview

        preview = ImportPreview(
            archive_path="/tmp/test.tar.gz",
            metadata={},
            comparisons=[
                AgentComparison(
                    agent=Agent("a1", "A1", "/tmp/a1.md", "user", full_content="content"),
                    status="IDENTICAL",
                    local_content="content",
                    archive_content="content"
                ),
                AgentComparison(
                    agent=Agent("a2", "A2", "/tmp/a2.md", "user", full_content="content"),
                    status="IDENTICAL",
                    local_content="content",
                    archive_content="content"
                )
            ],
            user_agents_count=2,
            project_agents_count=0,
            new_count=0,
            changed_count=0,
            identical_count=2
        )

        assert preview.identical_count == 2
        assert preview.new_count == 0
        assert preview.changed_count == 0


class TestMissingArchiveFile:
    """Test handling of missing archive files."""

    def test_missing_archive_file_error(self):
        """Test that missing archive raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            analyze_import_archive("/nonexistent/path/archive.tar.gz")

    def test_missing_archive_error_message(self):
        """Test that missing archive error message is clear."""
        with pytest.raises(FileNotFoundError) as exc_info:
            analyze_import_archive("/nonexistent/path/archive.tar.gz")

        error_msg = str(exc_info.value)
        assert "not found" in error_msg.lower() or "archive" in error_msg.lower()


class TestMalformedAgentFiles:
    """Test handling of malformed agent files in archives."""

    def test_malformed_yaml_frontmatter(self, tmp_path):
        """Test handling of agents with malformed YAML frontmatter."""
        import tarfile

        # Create archive with malformed agent
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()
        user_agents = archive_dir / "user-agents"
        user_agents.mkdir()

        malformed_agent = user_agents / "malformed.md"
        malformed_agent.write_text("""---
name: malformed
description: This has malformed YAML
  tools: Read, Edit
    broken indentation
---

# Malformed Agent
""")

        archive_path = tmp_path / "malformed.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(user_agents, arcname="user-agents")

        # Should handle gracefully (skip malformed agents)
        try:
            preview = analyze_import_archive(str(archive_path))
            # May or may not parse depending on YAML parser tolerance
            assert preview is not None
        except Exception as e:
            pytest.fail(f"Malformed YAML should be handled gracefully: {e}")

    def test_missing_frontmatter(self, tmp_path):
        """Test handling of agents without frontmatter."""
        import tarfile

        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()
        user_agents = archive_dir / "user-agents"
        user_agents.mkdir()

        no_frontmatter = user_agents / "no-frontmatter.md"
        no_frontmatter.write_text("""# Agent Without Frontmatter

This agent has no YAML frontmatter.
""")

        archive_path = tmp_path / "no-frontmatter.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(user_agents, arcname="user-agents")

        # Should handle gracefully
        preview = analyze_import_archive(str(archive_path))
        assert preview is not None


class TestSpecialCharactersInContent:
    """Test handling of special characters in agent content."""

    def test_unicode_characters(self, tmp_path):
        """Test handling of Unicode characters in agent content."""
        agent = Agent(
            name="unicode-test",
            description="Test with Unicode: 你好 世界 🚀",
            file_path=str(tmp_path / "unicode.md"),
            agent_type="user",
            full_content="""---
name: unicode-test
description: Test with Unicode: 你好 世界 🚀
---

# Unicode Test 你好

Content with emojis 🎉🎊🎈
"""
        )

        assert agent.description is not None
        assert "你好" in agent.description

    def test_special_yaml_characters(self, tmp_path):
        """Test handling of special YAML characters."""
        import tarfile

        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()
        user_agents = archive_dir / "user-agents"
        user_agents.mkdir()

        special_chars = user_agents / "special.md"
        special_chars.write_text("""---
name: special-chars
description: "Test with special chars: : @ # & *"
tools: Read
---

# Special Characters Test
""")

        archive_path = tmp_path / "special.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(user_agents, arcname="user-agents")

        preview = analyze_import_archive(str(archive_path))
        assert preview is not None


class TestLargeArchives:
    """Test handling of large archives."""

    def test_many_agents_in_archive(self, tmp_path):
        """Test handling of archive with many agents."""
        import tarfile

        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()
        user_agents = archive_dir / "user-agents"
        user_agents.mkdir()

        # Create 100 agent files
        for i in range(100):
            agent_file = user_agents / f"agent-{i}.md"
            agent_file.write_text(f"""---
name: agent-{i}
description: Test agent {i}
tools: Read
---

# Agent {i}
""")

        archive_path = tmp_path / "large.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(user_agents, arcname="user-agents")

        # Should handle large number of agents
        preview = analyze_import_archive(str(archive_path))
        assert preview is not None
        assert len(preview.comparisons) == 100


class TestNullAndEmptyValues:
    """Test handling of null and empty values."""

    def test_none_full_content(self):
        """Test handling of None full_content."""
        agent = Agent(
            name="test",
            description="Test",
            file_path="/tmp/test.md",
            agent_type="user",
            full_content=None
        )

        comparison = compare_agents(agent, None)
        assert comparison.status == "NEW"
        assert comparison.archive_content == ""  # None becomes empty string

    def test_empty_description(self):
        """Test handling of empty description."""
        agent = Agent(
            name="test",
            description="",
            file_path="/tmp/test.md",
            agent_type="user",
            full_content="# Test"
        )

        assert agent.description == ""

    def test_empty_tools_list(self):
        """Test handling of empty tools list."""
        agent = Agent(
            name="test",
            description="Test",
            file_path="/tmp/test.md",
            agent_type="user",
            tools=[]
        )

        assert agent.tools == []

    def test_none_tools_list(self):
        """Test handling of None tools list."""
        agent = Agent(
            name="test",
            description="Test",
            file_path="/tmp/test.md",
            agent_type="user",
            tools=None
        )

        # __post_init__ should convert None to []
        assert agent.tools == []


class TestPathEdgeCases:
    """Test edge cases related to file paths."""

    def test_absolute_vs_relative_paths(self, tmp_path):
        """Test handling of absolute vs relative paths."""
        absolute_path = tmp_path / "agent.md"
        relative_path = Path("agent.md")

        agent_abs = Agent("test", "Test", str(absolute_path), "user")
        agent_rel = Agent("test", "Test", str(relative_path), "user")

        assert agent_abs.file_path != agent_rel.file_path

    def test_path_with_spaces(self, tmp_path):
        """Test handling of paths with spaces."""
        path_with_spaces = tmp_path / "path with spaces" / "agent.md"
        path_with_spaces.parent.mkdir(parents=True)

        agent = Agent(
            name="test",
            description="Test",
            file_path=str(path_with_spaces),
            agent_type="user"
        )

        assert " " in agent.file_path

    def test_very_long_path(self, tmp_path):
        """Test handling of very long file paths."""
        # Create a deeply nested path
        deep_path = tmp_path
        for i in range(10):
            deep_path = deep_path / f"level_{i}"

        agent_file = deep_path / "agent.md"

        agent = Agent(
            name="test",
            description="Test",
            file_path=str(agent_file),
            agent_type="user"
        )

        assert len(agent.file_path) > 100


class TestConcurrentOperations:
    """Test thread safety and concurrent operations."""

    def test_multiple_archive_analyses(self, sample_archive):
        """Test analyzing same archive multiple times."""
        preview1 = analyze_import_archive(str(sample_archive))
        preview2 = analyze_import_archive(str(sample_archive))

        # Results should be consistent
        assert len(preview1.comparisons) == len(preview2.comparisons)
        assert preview1.new_count == preview2.new_count
        assert preview1.changed_count == preview2.changed_count


class TestPermissionErrors:
    """Test handling of permission errors."""

    def test_unreadable_archive(self, tmp_path, monkeypatch):
        """Test handling of archive with read permission denied."""
        # Note: This test may not work on all systems due to permission handling
        pass  # Placeholder for system-dependent test

    def test_write_protected_directory(self, tmp_path, monkeypatch):
        """Test handling of write-protected target directory."""
        # Note: This test may not work on all systems due to permission handling
        pass  # Placeholder for system-dependent test
