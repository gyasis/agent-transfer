"""G6 — capability-declared smoke commands run post-install.

Pre-fix bug: smoke_test.run() only verified file presence + sha + mode +
OS-level deps. Partial installs that pass these checks but leave the
capability functionally broken (binary missing, hook never reached due
to a parse error elsewhere) silently passed smoke.

Post-fix:
- Capability.smoke_commands is a list of shell commands.
- Each runs under `sh -c` with HOME = destination, 10s timeout.
- Non-zero exit → smoke result fails with command + stderr tail.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from agent_transfer.bridge.models import (
    Capability,
    ManifestModel,
)
from agent_transfer.bridge.smoke_test import run as smoke_run


def _manifest(smoke_commands: list[str]) -> ManifestModel:
    return ManifestModel(
        generated_at=datetime.utcnow(),
        source_machine_hint="test",
        capability=Capability(
            name="test-cap",
            description="x",
            intent="x",
            assets=[],
            smoke_commands=smoke_commands,
        ),
    )


def test_g6_no_smoke_commands_passes(tmp_path):
    """Default empty list — no smoke commands to run, smoke still passes."""
    m = _manifest([])
    r = smoke_run(m, home=tmp_path)
    assert r.passed is True
    assert r.failures == []


def test_g6_passing_command(tmp_path):
    m = _manifest(["true"])
    r = smoke_run(m, home=tmp_path)
    assert r.passed is True


def test_g6_failing_command_fails_smoke(tmp_path):
    m = _manifest(["false"])
    r = smoke_run(m, home=tmp_path)
    assert r.passed is False
    assert any("exited 1" in f for f in r.failures)
    assert any("'false'" in f for f in r.failures)


def test_g6_command_stderr_in_failure_message(tmp_path):
    m = _manifest(["sh -c 'echo OUCH 1>&2; exit 7'"])
    r = smoke_run(m, home=tmp_path)
    assert r.passed is False
    assert any("exited 7" in f for f in r.failures)
    assert any("OUCH" in f for f in r.failures)


def test_g6_command_uses_destination_home(tmp_path):
    """HOME env in the smoke command is the destination home, not source's."""
    home = tmp_path / "fake-home"
    home.mkdir()
    marker = home / "ping"
    marker.write_text("pong")

    m = _manifest(["test -f $HOME/ping"])
    r = smoke_run(m, home=home)
    assert r.passed is True


def test_g6_multiple_commands_one_fails(tmp_path):
    m = _manifest(["true", "false", "true"])
    r = smoke_run(m, home=tmp_path)
    assert r.passed is False
    # Only one failure (the false), not three.
    assert len(r.failures) == 1
    assert "'false'" in r.failures[0]


def test_g6_timeout_is_a_failure(tmp_path):
    """Hanging command must NOT block the smoke step forever."""
    # Override the timeout to keep the test fast.
    from agent_transfer.bridge import smoke_test as _st
    original = _st._SMOKE_COMMAND_TIMEOUT_S
    _st._SMOKE_COMMAND_TIMEOUT_S = 1
    try:
        m = _manifest(["sleep 30"])
        r = smoke_run(m, home=tmp_path)
        assert r.passed is False
        assert any("timed out" in f for f in r.failures)
    finally:
        _st._SMOKE_COMMAND_TIMEOUT_S = original
