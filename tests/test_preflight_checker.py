"""Unit tests for preflight checker functions and report generation.

Tests cover:
- Individual check functions (check_cli, check_env, check_sourced_files, check_docker)
- Aggregated run_preflight_checks() with overall status logic
- Report serialization (report_to_json) and display smoke test

All external dependencies (shutil.which, os.environ, Path.exists) are mocked
so tests are deterministic and fast.
"""

import json
import os
from unittest.mock import patch

import pytest

from agent_transfer.utils.preflight.checker import (
    CheckResult,
    ReadinessReport,
    check_cli,
    check_docker,
    check_env,
    check_sourced_files,
)
from agent_transfer.utils.preflight.manifest import (
    CliToolDep,
    DependencyGraph,
    DockerDep,
    EnvVarDep,
    SourcedFileDep,
    TransferManifest,
)
from agent_transfer.utils.preflight import run_preflight_checks
from agent_transfer.utils.preflight.report import (
    display_preflight_report,
    report_to_json,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cli_dep():
    """Factory for CliToolDep instances."""
    def _make(name="git", optional=False, install_hint=None):
        return CliToolDep(name=name, optional=optional, install_hint=install_hint)
    return _make


@pytest.fixture
def env_dep():
    """Factory for EnvVarDep instances."""
    def _make(name="HOME", critical=False):
        return EnvVarDep(name=name, critical=critical)
    return _make


@pytest.fixture
def sourced_file_dep():
    """Factory for SourcedFileDep instances."""
    def _make(path="/tmp/test_sourced_file"):
        return SourcedFileDep(path=path)
    return _make


@pytest.fixture
def docker_dep():
    """Factory for DockerDep instances."""
    def _make(file=None, image=None):
        return DockerDep(file=file, image=image)
    return _make


def _make_manifest(**dep_kwargs):
    """Build a minimal TransferManifest with given dependency lists."""
    deps = DependencyGraph(**dep_kwargs)
    return TransferManifest(dependencies=deps)


# ---------------------------------------------------------------------------
# 1-3: check_cli
# ---------------------------------------------------------------------------


class TestCheckCli:
    """Tests for check_cli()."""

    def test_tool_on_path_returns_green(self, cli_dep):
        """1. CLI tool found on PATH -> GREEN."""
        dep = cli_dep(name="git")
        with patch("agent_transfer.utils.preflight.checker.shutil.which", return_value="/usr/bin/git"):
            result = check_cli(dep)
        assert result.status == "GREEN"
        assert "git" in result.message
        assert result.remediation is None

    def test_missing_required_tool_returns_red(self, cli_dep):
        """2. Required CLI tool missing -> RED."""
        dep = cli_dep(name="nonexistent_tool_xyz", optional=False)
        with patch("agent_transfer.utils.preflight.checker.shutil.which", return_value=None):
            result = check_cli(dep)
        assert result.status == "RED"
        assert "nonexistent_tool_xyz" in result.message
        assert result.remediation is not None

    def test_missing_optional_tool_returns_yellow(self, cli_dep):
        """3. Optional CLI tool missing -> YELLOW."""
        dep = cli_dep(name="optional_tool", optional=True)
        with patch("agent_transfer.utils.preflight.checker.shutil.which", return_value=None):
            result = check_cli(dep)
        assert result.status == "YELLOW"
        assert "optional_tool" in result.message

    def test_install_hint_used_when_provided(self, cli_dep):
        """Custom install_hint is passed through to remediation."""
        dep = cli_dep(name="custom", optional=False, install_hint="brew install custom")
        with patch("agent_transfer.utils.preflight.checker.shutil.which", return_value=None):
            result = check_cli(dep)
        assert result.remediation == "brew install custom"


# ---------------------------------------------------------------------------
# 4-7: check_env
# ---------------------------------------------------------------------------


class TestCheckEnv:
    """Tests for check_env()."""

    def test_set_env_var_returns_green(self, env_dep):
        """4. Env var is set -> GREEN."""
        dep = env_dep(name="HOME", critical=False)
        with patch.dict(os.environ, {"HOME": "/home/testuser"}, clear=False):
            result = check_env(dep)
        assert result.status == "GREEN"
        assert "HOME" in result.message

    def test_missing_noncritical_env_var_returns_yellow(self, env_dep):
        """5. Missing non-critical env var -> YELLOW."""
        dep = env_dep(name="UNLIKELY_VAR_XYZ_999", critical=False)
        env_copy = {k: v for k, v in os.environ.items() if k != "UNLIKELY_VAR_XYZ_999"}
        with patch.dict(os.environ, env_copy, clear=True):
            result = check_env(dep)
        assert result.status == "YELLOW"
        assert "non-critical" in result.message.lower() or "not set" in result.message.lower()

    def test_missing_critical_env_var_returns_red(self, env_dep):
        """6. Missing critical env var -> RED."""
        dep = env_dep(name="CRITICAL_SECRET_XYZ", critical=True)
        env_copy = {k: v for k, v in os.environ.items() if k != "CRITICAL_SECRET_XYZ"}
        with patch.dict(os.environ, env_copy, clear=True):
            result = check_env(dep)
        assert result.status == "RED"
        assert "CRITICAL_SECRET_XYZ" in result.message

    def test_r8_compliance_value_never_in_message(self, env_dep):
        """7. R8 compliance: the actual env var VALUE must never appear in the result."""
        secret_value = "super_secret_token_12345"
        dep = env_dep(name="R8_TEST_VAR", critical=False)
        with patch.dict(os.environ, {"R8_TEST_VAR": secret_value}, clear=False):
            result = check_env(dep)
        assert result.status == "GREEN"
        assert secret_value not in result.message
        assert secret_value not in (result.remediation or "")

    def test_r8_compliance_missing_var_no_value_leak(self, env_dep):
        """R8: even remediation text must not contain env var values."""
        dep = env_dep(name="MISSING_SECRET", critical=True)
        env_copy = {k: v for k, v in os.environ.items() if k != "MISSING_SECRET"}
        with patch.dict(os.environ, env_copy, clear=True):
            result = check_env(dep)
        # Remediation should be a template, not a real value
        assert result.remediation is not None
        assert "<value>" in result.remediation


# ---------------------------------------------------------------------------
# 8-9: check_sourced_files
# ---------------------------------------------------------------------------


class TestCheckSourcedFiles:
    """Tests for check_sourced_files()."""

    def test_existing_file_returns_green(self, sourced_file_dep, tmp_path):
        """8. Sourced file exists -> GREEN."""
        real_file = tmp_path / "existing_script.sh"
        real_file.write_text("#!/bin/bash\necho hello")
        dep = sourced_file_dep(path=str(real_file))
        result = check_sourced_files(dep)
        assert result.status == "GREEN"
        assert str(real_file) in result.message

    def test_missing_file_returns_red(self, sourced_file_dep):
        """9. Sourced file missing -> RED."""
        dep = sourced_file_dep(path="/nonexistent/path/to/file.sh")
        result = check_sourced_files(dep)
        assert result.status == "RED"
        assert "not found" in result.message.lower()
        assert result.remediation is not None


# ---------------------------------------------------------------------------
# 10: check_docker
# ---------------------------------------------------------------------------


class TestCheckDocker:
    """Tests for check_docker()."""

    def test_docker_on_path_returns_green(self, docker_dep):
        """10a. Docker on PATH, no compose file -> GREEN."""
        dep = docker_dep()
        with patch("agent_transfer.utils.preflight.checker.shutil.which", return_value="/usr/bin/docker"):
            result = check_docker(dep)
        assert result.status == "GREEN"
        assert "Docker is available" in result.message

    def test_docker_missing_returns_red(self, docker_dep):
        """10b. Docker not on PATH -> RED."""
        dep = docker_dep()
        with patch("agent_transfer.utils.preflight.checker.shutil.which", return_value=None):
            result = check_docker(dep)
        assert result.status == "RED"
        assert "not found" in result.message.lower()

    def test_docker_with_existing_compose_returns_green(self, docker_dep, tmp_path):
        """Docker on PATH + compose file exists -> GREEN."""
        compose = tmp_path / "docker-compose.yml"
        compose.write_text("version: '3'\nservices: {}")
        dep = docker_dep(file=str(compose))
        with patch("agent_transfer.utils.preflight.checker.shutil.which", return_value="/usr/bin/docker"):
            result = check_docker(dep)
        assert result.status == "GREEN"
        assert "compose file" in result.message.lower()

    def test_docker_with_missing_compose_returns_yellow(self, docker_dep):
        """Docker on PATH + compose file missing -> YELLOW."""
        dep = docker_dep(file="/nonexistent/docker-compose.yml")
        with patch("agent_transfer.utils.preflight.checker.shutil.which", return_value="/usr/bin/docker"):
            result = check_docker(dep)
        assert result.status == "YELLOW"
        assert "missing" in result.message.lower()


# ---------------------------------------------------------------------------
# 11-13: run_preflight_checks
# ---------------------------------------------------------------------------


class TestRunPreflightChecks:
    """Tests for the top-level run_preflight_checks() aggregator."""

    def test_mixed_deps_correct_counts(self):
        """11. Mixed results -> correct overall_status and counts."""
        manifest = _make_manifest(
            cli_tools=[
                CliToolDep(name="present_tool"),
                CliToolDep(name="missing_required", optional=False),
                CliToolDep(name="missing_optional", optional=True),
            ],
        )

        def fake_which(name):
            return "/usr/bin/present_tool" if name == "present_tool" else None

        with patch("agent_transfer.utils.preflight.checker.shutil.which", side_effect=fake_which):
            report = run_preflight_checks(manifest)

        assert report.green_count == 1
        assert report.yellow_count == 1
        assert report.red_count == 1
        assert report.overall_status == "FAIL"  # RED present -> FAIL

    def test_all_green_returns_pass(self):
        """12. All GREEN -> PASS."""
        manifest = _make_manifest(
            cli_tools=[
                CliToolDep(name="git"),
                CliToolDep(name="python3"),
            ],
        )
        with patch("agent_transfer.utils.preflight.checker.shutil.which", return_value="/usr/bin/found"):
            report = run_preflight_checks(manifest)

        assert report.overall_status == "PASS"
        assert report.green_count == 2
        assert report.yellow_count == 0
        assert report.red_count == 0

    def test_yellow_no_red_returns_warn(self):
        """13. YELLOW present but no RED -> WARN."""
        manifest = _make_manifest(
            cli_tools=[
                CliToolDep(name="found_tool"),
                CliToolDep(name="missing_opt", optional=True),
            ],
        )

        def fake_which(name):
            return "/usr/bin/found" if name == "found_tool" else None

        with patch("agent_transfer.utils.preflight.checker.shutil.which", side_effect=fake_which):
            report = run_preflight_checks(manifest)

        assert report.overall_status == "WARN"
        assert report.yellow_count == 1
        assert report.red_count == 0

    def test_empty_manifest_returns_pass(self):
        """Empty manifest with no deps -> PASS with zero counts."""
        manifest = _make_manifest()
        report = run_preflight_checks(manifest)
        assert report.overall_status == "PASS"
        assert report.green_count == 0
        assert report.yellow_count == 0
        assert report.red_count == 0
        assert report.results == {}

    def test_multiple_categories_counted(self):
        """Deps across multiple categories all contribute to counts."""
        manifest = _make_manifest(
            cli_tools=[CliToolDep(name="present")],
            env_vars=[EnvVarDep(name="DEFINITELY_MISSING_VAR_XYZ", critical=True)],
        )
        env_copy = {k: v for k, v in os.environ.items() if k != "DEFINITELY_MISSING_VAR_XYZ"}
        with patch("agent_transfer.utils.preflight.checker.shutil.which", return_value="/usr/bin/present"), \
             patch.dict(os.environ, env_copy, clear=True):
            report = run_preflight_checks(manifest)

        assert report.green_count == 1  # cli present
        assert report.red_count == 1    # env missing+critical
        assert report.overall_status == "FAIL"
        assert "cli_tools" in report.results
        assert "env_vars" in report.results


# ---------------------------------------------------------------------------
# 14: report_to_json
# ---------------------------------------------------------------------------


class TestReportToJson:
    """Tests for report_to_json() serialization."""

    def test_returns_valid_json_with_expected_keys(self):
        """14. report_to_json returns valid JSON with all expected fields."""
        report = ReadinessReport(
            target_os="linux",
            target_arch="x86_64",
            overall_status="WARN",
            green_count=3,
            yellow_count=1,
            red_count=0,
            results={
                "cli_tools": [
                    CheckResult(
                        dependency=CliToolDep(name="git"),
                        status="GREEN",
                        message="CLI tool 'git' found on PATH",
                    ),
                    CheckResult(
                        dependency=CliToolDep(name="optional_thing", optional=True),
                        status="YELLOW",
                        message="Optional CLI tool 'optional_thing' not found",
                        remediation="apt install optional_thing",
                    ),
                ],
            },
            manual_checklist=["Verify SSH key access"],
        )

        raw = report_to_json(report)
        data = json.loads(raw)

        assert data["overall_status"] == "WARN"
        assert data["target_os"] == "linux"
        assert data["target_arch"] == "x86_64"
        assert data["green_count"] == 3
        assert data["yellow_count"] == 1
        assert data["red_count"] == 0
        assert "cli_tools" in data["results"]
        assert len(data["results"]["cli_tools"]) == 2
        assert data["manual_checklist"] == ["Verify SSH key access"]

        # Check individual result structure
        first = data["results"]["cli_tools"][0]
        assert "name" in first
        assert "status" in first
        assert "message" in first
        assert "remediation" in first

    def test_json_includes_source_when_manifest_present(self):
        """Source block appears when manifest is attached to report."""
        manifest = TransferManifest(
            source_platform="claude-code",
            source_os="linux",
            source_arch="x86_64",
        )
        report = ReadinessReport(manifest=manifest, target_os="linux", target_arch="x86_64")
        data = json.loads(report_to_json(report))
        assert "source" in data
        assert data["source"]["platform"] == "claude-code"

    def test_json_no_source_when_manifest_none(self):
        """No source block when manifest is None."""
        report = ReadinessReport(target_os="linux", target_arch="x86_64")
        data = json.loads(report_to_json(report))
        assert "source" not in data


# ---------------------------------------------------------------------------
# 15: display_preflight_report smoke test
# ---------------------------------------------------------------------------


class TestDisplayReadinessReport:
    """Smoke tests for display_preflight_report()."""

    def test_does_not_crash_with_populated_report(self):
        """15. display_preflight_report does not raise on a populated report."""
        report = ReadinessReport(
            target_os="linux",
            target_arch="x86_64",
            overall_status="PASS",
            green_count=1,
            results={
                "cli_tools": [
                    CheckResult(
                        dependency=CliToolDep(name="git"),
                        status="GREEN",
                        message="CLI tool 'git' found on PATH",
                    ),
                ],
            },
        )
        # Should not raise
        display_preflight_report(report)

    def test_does_not_crash_with_empty_report(self):
        """display_preflight_report handles empty report without crashing."""
        report = ReadinessReport(target_os="linux", target_arch="x86_64")
        display_preflight_report(report)

    def test_does_not_crash_with_manual_checklist(self):
        """display_preflight_report renders manual checklist items."""
        report = ReadinessReport(
            target_os="linux",
            target_arch="x86_64",
            overall_status="WARN",
            manual_checklist=["Check SSH keys", "Verify API tokens"],
        )
        display_preflight_report(report)

    def test_does_not_crash_with_remediation(self):
        """display_preflight_report renders remediation text."""
        report = ReadinessReport(
            target_os="linux",
            target_arch="x86_64",
            overall_status="FAIL",
            red_count=1,
            results={
                "env_vars": [
                    CheckResult(
                        dependency=EnvVarDep(name="SECRET", critical=True),
                        status="RED",
                        message="Critical env var 'SECRET' is NOT set",
                        remediation="export SECRET=<value>",
                    ),
                ],
            },
        )
        display_preflight_report(report)
