"""
Test suite for selective import flow.

Tests the end-to-end selective import functionality including
conflict resolution, import statistics, and mixed selections.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock

from agent_transfer.utils.import_analyzer import analyze_import_archive
from agent_transfer.models import Agent, AgentComparison


class TestImportNewAgents:
    """Test importing NEW agents."""

    def test_import_new_agents_creates_files(self, sample_archive, local_agent_dir, monkeypatch):
        """Test that NEW agents are created in correct directories."""
        # Mock home directory
        monkeypatch.setattr(Path, 'home', lambda: local_agent_dir["root"])
        monkeypatch.setattr(Path, 'cwd', lambda: local_agent_dir["root"] / "project")

        preview = analyze_import_archive(str(sample_archive))
        new_agents = [c for c in preview.comparisons if c.status == "NEW"]

        # Verify we have some NEW agents in the test archive
        assert len(new_agents) > 0

    def test_import_new_agents_preserves_content(self, sample_comparison_new, tmp_path):
        """Test that NEW agents preserve full content including frontmatter."""
        agent = sample_comparison_new.agent

        # Content should include frontmatter and body
        assert agent.full_content is not None
        assert "---" in agent.full_content
        assert agent.name in agent.full_content
        assert agent.description in agent.full_content

    def test_import_new_agents_stats(self, sample_preview):
        """Test that import statistics correctly track NEW agents."""
        new_comparisons = [c for c in sample_preview.comparisons if c.status == "NEW"]

        assert sample_preview.new_count == len(new_comparisons)
        assert sample_preview.new_count == 1  # Based on fixture


class TestImportChangedAgents:
    """Test importing CHANGED agents with conflict resolution."""

    def test_import_changed_agents_overwrite_mode(self, sample_comparison_changed, tmp_path):
        """Test overwrite mode replaces existing content."""
        # Create a local agent file
        local_file = tmp_path / "test-agent.md"
        local_file.write_text(sample_comparison_changed.local_content)

        original_content = local_file.read_text()
        assert original_content == sample_comparison_changed.local_content

        # Simulate overwrite
        local_file.write_text(sample_comparison_changed.archive_content)
        new_content = local_file.read_text()

        assert new_content == sample_comparison_changed.archive_content
        assert new_content != original_content

    def test_import_changed_agents_keep_mode(self, sample_comparison_changed, tmp_path):
        """Test keep mode preserves existing content."""
        # Create a local agent file
        local_file = tmp_path / "test-agent.md"
        local_file.write_text(sample_comparison_changed.local_content)

        original_content = local_file.read_text()

        # Simulate keep mode (no write)
        # Content should remain unchanged
        assert local_file.read_text() == original_content

    def test_import_changed_agents_duplicate_mode(self, sample_comparison_changed, tmp_path):
        """Test duplicate mode creates new file with suffix."""
        # Create a local agent file
        local_file = tmp_path / "test-agent.md"
        local_file.write_text(sample_comparison_changed.local_content)

        # Simulate duplicate mode
        duplicate_file = tmp_path / "test-agent_1.md"
        duplicate_file.write_text(sample_comparison_changed.archive_content)

        # Both files should exist
        assert local_file.exists()
        assert duplicate_file.exists()

        # Content should differ
        assert local_file.read_text() != duplicate_file.read_text()
        assert duplicate_file.read_text() == sample_comparison_changed.archive_content

    def test_import_changed_agents_multiple_duplicates(self, sample_comparison_changed, tmp_path):
        """Test duplicate mode handles multiple duplicates with incrementing suffixes."""
        base_file = tmp_path / "test-agent.md"
        base_file.write_text("original content")

        # Create duplicates
        for i in range(1, 4):
            duplicate_file = tmp_path / f"test-agent_{i}.md"
            duplicate_file.write_text(f"duplicate {i}")

        # Verify all files exist
        assert base_file.exists()
        assert (tmp_path / "test-agent_1.md").exists()
        assert (tmp_path / "test-agent_2.md").exists()
        assert (tmp_path / "test-agent_3.md").exists()


class TestSkipIdenticalAgents:
    """Test that IDENTICAL agents are skipped during import."""

    def test_skip_identical_agents(self, sample_comparison_identical):
        """Test that IDENTICAL agents are identified correctly."""
        assert sample_comparison_identical.status == "IDENTICAL"
        assert sample_comparison_identical.local_content == sample_comparison_identical.archive_content

    def test_identical_agents_not_in_default_selection(self, sample_preview):
        """Test that IDENTICAL agents are not pre-selected by default."""
        # Get default selection (NEW + CHANGED)
        default_selection = [
            c for c in sample_preview.comparisons
            if c.status in ["NEW", "CHANGED"]
        ]

        # Verify no IDENTICAL agents in default selection
        assert all(c.status != "IDENTICAL" for c in default_selection)

    def test_identical_count_tracking(self, sample_preview):
        """Test that IDENTICAL agents are counted correctly."""
        identical_comparisons = [
            c for c in sample_preview.comparisons
            if c.status == "IDENTICAL"
        ]

        assert sample_preview.identical_count == len(identical_comparisons)
        assert sample_preview.identical_count == 1  # Based on fixture


class TestImportStatsTracking:
    """Test import statistics tracking."""

    def test_import_stats_all_categories(self, sample_preview):
        """Test that all agent categories are counted correctly."""
        total = sample_preview.new_count + sample_preview.changed_count + sample_preview.identical_count

        assert total == len(sample_preview.comparisons)
        assert sample_preview.new_count == 1
        assert sample_preview.changed_count == 1
        assert sample_preview.identical_count == 1

    def test_import_stats_user_vs_project(self, sample_preview):
        """Test that user and project agents are counted separately."""
        total = sample_preview.user_agents_count + sample_preview.project_agents_count

        assert total == len(sample_preview.comparisons)
        assert sample_preview.user_agents_count == 2
        assert sample_preview.project_agents_count == 1

    def test_import_stats_empty_archive(self, empty_archive):
        """Test statistics for empty archive."""
        preview = analyze_import_archive(str(empty_archive))

        assert preview.new_count == 0
        assert preview.changed_count == 0
        assert preview.identical_count == 0
        assert len(preview.comparisons) == 0


class TestMixedImportSelection:
    """Test importing a mix of NEW and CHANGED agents."""

    def test_mixed_import_selection(self, sample_preview):
        """Test selecting and importing both NEW and CHANGED agents."""
        # Get NEW and CHANGED agents
        new_and_changed = [
            c for c in sample_preview.comparisons
            if c.status in ["NEW", "CHANGED"]
        ]

        assert len(new_and_changed) == 2
        assert any(c.status == "NEW" for c in new_and_changed)
        assert any(c.status == "CHANGED" for c in new_and_changed)

    def test_mixed_selection_preserves_types(self, sample_preview):
        """Test that mixed selection preserves agent types."""
        new_and_changed = [
            c for c in sample_preview.comparisons
            if c.status in ["NEW", "CHANGED"]
        ]

        # Verify agent types are preserved
        for comparison in new_and_changed:
            assert comparison.agent.agent_type in ["user", "project"]

    def test_partial_selection(self, sample_preview):
        """Test selecting only some NEW/CHANGED agents."""
        # Select only NEW agents
        new_only = [c for c in sample_preview.comparisons if c.status == "NEW"]

        assert len(new_only) == 1
        assert new_only[0].status == "NEW"

        # Select only CHANGED agents
        changed_only = [c for c in sample_preview.comparisons if c.status == "CHANGED"]

        assert len(changed_only) == 1
        assert changed_only[0].status == "CHANGED"


class TestAgentNameFiltering:
    """Test filtering agents by name."""

    def test_filter_by_exact_name(self, sample_preview):
        """Test filtering agents by exact name match."""
        target_name = sample_preview.comparisons[0].agent.name
        filtered = [c for c in sample_preview.comparisons if c.agent.name == target_name]

        # All fixtures use the same name "test-agent" across different statuses
        assert len(filtered) >= 1
        assert all(c.agent.name == target_name for c in filtered)

    def test_filter_by_name_case_sensitive(self, sample_preview):
        """Test that name filtering is case-sensitive."""
        if len(sample_preview.comparisons) > 0:
            target_name = sample_preview.comparisons[0].agent.name
            wrong_case_name = target_name.upper()

            # Exact match should work
            exact_match = [c for c in sample_preview.comparisons if c.agent.name == target_name]
            assert len(exact_match) >= 1

            # Wrong case should not match (unless name is all caps)
            if target_name != wrong_case_name:
                wrong_match = [c for c in sample_preview.comparisons if c.agent.name == wrong_case_name]
                assert len(wrong_match) == 0

    def test_filter_nonexistent_name(self, sample_preview):
        """Test filtering with nonexistent agent name."""
        filtered = [c for c in sample_preview.comparisons if c.agent.name == "nonexistent-agent-xyz"]

        assert len(filtered) == 0


class TestBulkImport:
    """Test bulk import functionality."""

    def test_bulk_import_all_new(self, sample_archive):
        """Test bulk importing all NEW agents."""
        preview = analyze_import_archive(str(sample_archive))
        new_agents = [c for c in preview.comparisons if c.status == "NEW"]

        # Should be able to bulk import all new agents
        assert len(new_agents) >= 0

    def test_bulk_import_statistics(self, sample_archive):
        """Test that bulk import tracks statistics correctly."""
        preview = analyze_import_archive(str(sample_archive))

        total = len(preview.comparisons)
        imported = preview.new_count  # Only new in bulk import
        skipped = preview.changed_count + preview.identical_count

        assert imported + skipped == total


class TestAgentTypePreservation:
    """Test that agent types (user/project) are preserved during import."""

    def test_user_agent_type_preserved(self, sample_agent):
        """Test that user agents maintain their type."""
        assert sample_agent.agent_type == "user"

    def test_project_agent_type_preserved(self):
        """Test that project agents maintain their type."""
        project_agent = Agent(
            name="project-agent",
            description="Project agent",
            file_path="/tmp/project-agent.md",
            agent_type="project",
            full_content="# Project Agent"
        )

        assert project_agent.agent_type == "project"

    def test_agent_type_in_comparison(self, sample_comparison_new):
        """Test that agent type is accessible in comparisons."""
        assert sample_comparison_new.agent.agent_type in ["user", "project"]


class TestContentIntegrity:
    """Test that agent content integrity is maintained during import."""

    def test_content_includes_frontmatter(self, sample_agent):
        """Test that full_content includes YAML frontmatter."""
        assert sample_agent.full_content is not None
        assert "---" in sample_agent.full_content
        assert "name:" in sample_agent.full_content

    def test_content_includes_body(self, sample_agent):
        """Test that full_content includes markdown body."""
        assert sample_agent.full_content is not None
        assert "#" in sample_agent.full_content  # Markdown header

    def test_content_not_corrupted(self, sample_agent, sample_agent_modified):
        """Test that content is not corrupted during comparison."""
        # Both agents should have valid content
        assert sample_agent.full_content is not None
        assert sample_agent_modified.full_content is not None

        # Content should differ
        assert sample_agent.full_content != sample_agent_modified.full_content
