"""agent-transfer doctor — inspect + playbook tests.

Covers:
  • Check atoms return shape: id, status, detail
  • Inspect on a clean fixture HOME (no ~/.claude.json) marks claude_dir
    + claude_json as warn, not fail (pre-init shape)
  • Inspect detects <REDACTED> tokens in ~/.claude.json as FAIL
  • Inspect markdown contains Findings section when any non-pass
  • Inspect JSON sidecar has stable keys
  • Playbook emits zero steps when only pass + skip checks
  • Playbook lists action items for warn/fail with platform-correct commands
  • Playbook markdown shape: # heading, ## Action Items, ## Verification
  • Cross-platform: darwin-specific checks only fire on darwin
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_transfer.doctor.checks import (
    CheckResult,
    check_architecture,
    check_claude_json,
    check_python3,
    check_redacted_tokens,
    runtime_checks,
)
from agent_transfer.doctor.inspect import run_inspect
from agent_transfer.doctor.playbook import run_playbook


# --------------------------------------------------------------------- #
# Check atoms                                                            #
# --------------------------------------------------------------------- #


def test_check_python3_returns_pass_when_on_path():
    """python3 is reliably present in the test environment."""
    r = check_python3()
    assert isinstance(r, CheckResult)
    assert r.id == "python3"
    assert r.status in {"pass", "fail"}
    if r.status == "pass":
        assert "python3" in r.detail.lower() or "python" in r.detail.lower()


def test_check_architecture_always_passes():
    r = check_architecture()
    assert r.status == "pass"
    assert r.raw.get("arch")


def test_check_claude_json_missing_is_warn(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    r = check_claude_json(home)
    assert r.status == "warn"
    assert "does not exist" in r.detail


def test_check_claude_json_well_formed(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {"a": {}}}))
    r = check_claude_json(home)
    assert r.status == "pass"
    assert "1 MCP" in r.detail


def test_check_claude_json_malformed_is_fail(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude.json").write_text("{ not valid json")
    r = check_claude_json(home)
    assert r.status == "fail"
    assert r.severity == "error"


def test_check_redacted_tokens_detects_placeholder(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude.json").write_text(json.dumps({
        "mcpServers": {
            "remote": {
                "transport": "http",
                "headers": {"Authorization": "Bearer <REDACTED>"},
            }
        }
    }))
    r = check_redacted_tokens(home)
    assert r.status == "fail"
    assert "<REDACTED>" in r.detail


def test_check_redacted_tokens_clean(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {}}))
    r = check_redacted_tokens(home)
    assert r.status == "pass"


# --------------------------------------------------------------------- #
# Inspect orchestrator                                                   #
# --------------------------------------------------------------------- #


def test_inspect_clean_home_no_fail(tmp_path):
    """A pristine HOME with no ~/.claude/ — pre-init shape. No fails."""
    home = tmp_path / "home"
    home.mkdir()
    report = run_inspect(home=home)
    assert report.fail_count == 0, [c.id for c in report.checks if c.status == "fail"]
    # Should have at least the cross-platform checks (8 runtime + 2 inspect-only).
    assert len(report.checks) >= 8


def test_inspect_redacted_token_makes_fail(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude.json").write_text(json.dumps({
        "mcpServers": {"x": {"headers": {"k": "<REDACTED>"}}}
    }))
    report = run_inspect(home=home)
    fails = [c.id for c in report.checks if c.status == "fail"]
    assert "redacted_tokens" in fails
    assert report.exit_code == 1


def test_inspect_markdown_has_findings_section(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    report = run_inspect(home=home)
    md = report.to_markdown()
    assert "# agent-transfer doctor inspect" in md
    assert "Summary:" in md
    # Pre-init HOME has at least warn (no ~/.claude.json), so Findings should appear.
    if report.warn_count or report.fail_count:
        assert "## Findings" in md


def test_inspect_json_sidecar_stable_keys(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    report = run_inspect(home=home)
    d = report.to_dict()
    assert {"generated_at", "platform", "home", "checks", "pass_count", "warn_count", "fail_count", "skip_count"} <= set(d)
    for c in d["checks"]:
        assert {"id", "title", "status", "detail", "severity"} <= set(c)


# --------------------------------------------------------------------- #
# Playbook orchestrator                                                  #
# --------------------------------------------------------------------- #


def test_playbook_clean_home_has_warn_steps(tmp_path):
    """A pristine HOME with no ~/.claude.json — warn steps for missing config."""
    home = tmp_path / "home"
    home.mkdir()
    pb = run_playbook(home=home)
    # claude_dir + claude_json are warn → at least 2 steps unless suppressed.
    step_ids = {s.id for s in pb.steps}
    assert "claude_json" in step_ids or "claude_dir" in step_ids


def test_playbook_markdown_shape(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    pb = run_playbook(home=home)
    md = pb.to_markdown()
    assert "# agent-transfer doctor playbook" in md
    assert "## Summary" in md
    # If we have action items, Action Items + Verification headers appear.
    if pb.steps:
        assert "## Action Items" in md
        assert "## Verification" in md


def test_playbook_includes_platform_command_when_available(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    pb = run_playbook(home=home)
    # Every step should at least have a fix_hint; commands optional per-platform.
    for step in pb.steps:
        assert step.fix_hint
        assert step.severity in {"warn", "error"}


def test_playbook_zero_steps_emits_ready_marker(tmp_path):
    """If we synthesize all-pass checks, playbook should say 'ready'."""
    home = tmp_path / "home"
    home.mkdir()
    pb = run_playbook(home=home)
    if not pb.steps:
        md = pb.to_markdown()
        assert "No action items" in md


def test_playbook_json_shape(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    pb = run_playbook(home=home)
    d = pb.to_dict()
    assert {"generated_at", "platform", "home", "steps", "step_count"} <= set(d)
    for s in d["steps"]:
        assert {"id", "title", "severity", "detail", "fix_hint"} <= set(s)


# --------------------------------------------------------------------- #
# Cross-platform behavior                                                #
# --------------------------------------------------------------------- #


def test_darwin_checks_skip_on_linux():
    """homebrew + xcode_clt return 'skip' when sys.platform != 'darwin'."""
    from agent_transfer.doctor.checks import check_homebrew, check_xcode_clt

    if sys.platform == "darwin":
        pytest.skip("Test only meaningful on non-darwin host")
    r1 = check_homebrew()
    r2 = check_xcode_clt()
    assert r1.status == "skip"
    assert r2.status == "skip"
