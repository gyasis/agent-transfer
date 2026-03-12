"""Tests for preflight import gate and CLI integration."""

from __future__ import annotations

import json
import tarfile
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_transfer.utils.preflight import (
    run_preflight_checks,
    read_manifest_from_archive,
    TransferManifest,
)
from agent_transfer.utils.preflight.manifest import (
    CliToolDep,
    DependencyGraph,
    EnvVarDep,
    ContentsInventory,
    write_manifest,
)
from agent_transfer.utils.preflight.report import report_to_json


def _make_test_archive(tmp_path: Path, manifest: TransferManifest) -> Path:
    """Create a tar.gz archive with a manifest.json."""
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest, manifest_path)

    agent_path = tmp_path / "test-agent.md"
    agent_path.write_text("---\ntools: Read, Write\n---\nTest agent\n")

    archive_path = tmp_path / "test.tar.gz"
    with tarfile.open(str(archive_path), "w:gz") as tf:
        tf.add(str(manifest_path), arcname="manifest.json")
        tf.add(str(agent_path), arcname="test-agent.md")

    return archive_path


def _make_legacy_archive(tmp_path: Path) -> Path:
    """Create a tar.gz archive without manifest.json."""
    agent_path = tmp_path / "old-agent.md"
    agent_path.write_text("---\ntools: Read\n---\nOld agent\n")

    archive_path = tmp_path / "legacy.tar.gz"
    with tarfile.open(str(archive_path), "w:gz") as tf:
        tf.add(str(agent_path), arcname="old-agent.md")

    return archive_path


class TestImportGateGreen:
    """All GREEN deps → import proceeds silently."""

    def test_all_green_passes(self, tmp_path):
        manifest = TransferManifest(
            source_os="linux",
            source_arch="x86_64",
            dependencies=DependencyGraph(
                cli_tools=[CliToolDep(name="git", required_by=["test"])],
                env_vars=[EnvVarDep(name="HOME", critical=False, required_by=["test"])],
            ),
        )
        report = run_preflight_checks(manifest)
        assert report.overall_status == "PASS"
        assert report.red_count == 0

    def test_all_green_exit_code_zero(self, tmp_path):
        manifest = TransferManifest(
            source_os="linux",
            dependencies=DependencyGraph(
                cli_tools=[CliToolDep(name="git")],
            ),
        )
        report = run_preflight_checks(manifest)
        assert report.overall_status == "PASS"


class TestImportGateYellow:
    """YELLOW deps → import proceeds with warning."""

    def test_yellow_warns(self, tmp_path):
        manifest = TransferManifest(
            source_os="linux",
            dependencies=DependencyGraph(
                cli_tools=[
                    CliToolDep(name="git"),  # GREEN
                    CliToolDep(name="nonexistent_optional_xyz", optional=True),  # YELLOW
                ],
            ),
        )
        report = run_preflight_checks(manifest)
        assert report.overall_status == "WARN"
        assert report.yellow_count >= 1
        assert report.red_count == 0


class TestImportGateRed:
    """RED deps → import blocked unless --force."""

    def test_red_blocks(self, tmp_path):
        manifest = TransferManifest(
            source_os="linux",
            dependencies=DependencyGraph(
                cli_tools=[CliToolDep(name="nonexistent_required_xyz")],
            ),
        )
        report = run_preflight_checks(manifest)
        assert report.overall_status == "FAIL"
        assert report.red_count >= 1

    def test_red_with_remediation(self, tmp_path):
        manifest = TransferManifest(
            source_os="linux",
            dependencies=DependencyGraph(
                env_vars=[
                    EnvVarDep(name="FAKE_CRITICAL_KEY_XYZ", critical=True),
                ],
            ),
        )
        report = run_preflight_checks(manifest)
        assert report.overall_status == "FAIL"
        # Verify remediation hint exists
        env_results = report.results.get("env_vars", [])
        assert len(env_results) == 1
        assert env_results[0].remediation is not None


class TestLegacyArchive:
    """Archives without manifest.json should be handled gracefully."""

    def test_no_manifest_returns_none(self, tmp_path):
        archive = _make_legacy_archive(tmp_path)
        manifest = read_manifest_from_archive(archive)
        assert manifest is None

    def test_manifest_present_returns_manifest(self, tmp_path):
        m = TransferManifest(source_os="linux", source_arch="x86_64")
        archive = _make_test_archive(tmp_path, m)
        manifest = read_manifest_from_archive(archive)
        assert manifest is not None
        assert manifest.source_os == "linux"


class TestReportJson:
    """JSON output for --json flag."""

    def test_json_output_valid(self):
        manifest = TransferManifest(
            source_os="linux",
            source_arch="x86_64",
            dependencies=DependencyGraph(
                cli_tools=[
                    CliToolDep(name="git"),
                    CliToolDep(name="nonexistent_xyz"),
                ],
            ),
        )
        report = run_preflight_checks(manifest)
        output = report_to_json(report)

        data = json.loads(output)
        assert data["overall_status"] == "FAIL"
        assert "cli_tools" in data["results"]
        assert data["red_count"] >= 1
        assert data["green_count"] >= 1

    def test_json_has_source_info(self):
        manifest = TransferManifest(source_os="linux", source_arch="x86_64")
        report = run_preflight_checks(manifest)
        output = report_to_json(report)
        data = json.loads(output)
        assert data["source"]["os"] == "linux"


class TestMixedDependencies:
    """Tests with multiple dependency categories."""

    def test_mixed_deps_correct_counts(self):
        manifest = TransferManifest(
            source_os="linux",
            dependencies=DependencyGraph(
                cli_tools=[
                    CliToolDep(name="git"),  # GREEN
                    CliToolDep(name="nonexistent_xyz"),  # RED
                ],
                env_vars=[
                    EnvVarDep(name="HOME"),  # GREEN
                    EnvVarDep(name="MISSING_NON_CRIT_XYZ", critical=False),  # YELLOW
                ],
            ),
        )
        report = run_preflight_checks(manifest)
        assert report.green_count == 2
        assert report.yellow_count == 1
        assert report.red_count == 1
        assert report.overall_status == "FAIL"

    def test_empty_manifest_passes(self):
        manifest = TransferManifest(source_os="linux")
        report = run_preflight_checks(manifest)
        assert report.overall_status == "PASS"
        assert report.green_count == 0
        assert report.red_count == 0
