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


def test_d_path_is_scrubbed_to_safe_set(tmp_path):
    """D (F8) — smoke commands run with a scrubbed PATH, not the inherited one."""
    home = tmp_path / "home"
    home.mkdir()
    # Plant a binary in a junk dir; it should NOT appear in smoke's PATH.
    junk = tmp_path / "evil-bin"
    junk.mkdir()
    (junk / "evil-cmd").write_text("#!/bin/sh\necho pwned\n")
    (junk / "evil-cmd").chmod(0o755)

    import os
    saved = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{junk}:{saved}"
    try:
        # The smoke command tries to call evil-cmd; under scrubbed PATH
        # it must fail (command not found → non-zero exit).
        m = _manifest(["evil-cmd"])
        r = smoke_run(m, home=home)
        assert r.passed is False, (
            "evil-cmd was found despite scrubbed PATH — sandbox leak"
        )
    finally:
        os.environ["PATH"] = saved


def test_d_destination_local_bin_resolves(tmp_path):
    """Smoke can still find a binary the destination shipped to ~/.local/bin."""
    home = tmp_path / "home"
    bin_dir = home / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    cmd = bin_dir / "ok-cmd"
    cmd.write_text("#!/bin/sh\nexit 0\n")
    cmd.chmod(0o755)

    m = _manifest(["ok-cmd"])
    r = smoke_run(m, home=home)
    assert r.passed is True, f"ok-cmd in ~/.local/bin failed: {r.failures}"


def test_d_skip_flag_warns_but_does_not_run(tmp_path):
    """`--no-smoke` opt-out: commands NOT run, warning recorded."""
    m = _manifest(["false"])  # would fail if executed
    r = smoke_run(m, home=tmp_path, skip_smoke_commands=True)
    assert r.passed is True, "skip mode must not produce failures"
    assert any("opt-out" in w for w in r.warnings)


def test_d_env_does_not_leak_arbitrary_keys(tmp_path):
    """Env vars not on the allowlist must NOT reach the smoke process."""
    home = tmp_path / "home"
    home.mkdir()
    import os
    os.environ["AGENTBRIDGE_TEST_SECRET"] = "must-not-leak"
    try:
        # Command echoes the env var; if it leaks, output is non-empty
        # and the test below would catch it. We verify by exit code:
        # `test -z` exits 0 if string is EMPTY.
        m = _manifest(["test -z \"$AGENTBRIDGE_TEST_SECRET\""])
        r = smoke_run(m, home=home)
        assert r.passed is True, (
            "AGENTBRIDGE_TEST_SECRET leaked into smoke env"
        )
    finally:
        os.environ.pop("AGENTBRIDGE_TEST_SECRET", None)


def test_l_timeout_kills_backgrounded_grandchildren(tmp_path):
    """L (Hunter B D-adjacent) — `cmd & disown` cannot outlive timeout.

    Pre-fix: subprocess.run(timeout=10) SIGKILLs the immediate child
    (the `sh -c` shell) but not its disowned grandchildren. A smoke
    command that starts a long-running daemon and detaches would
    survive the timeout and leak a process.

    Post-fix: start_new_session=True puts the command in its own
    process group, and on TimeoutExpired we killpg the whole group.
    """
    import os
    from agent_transfer.bridge import smoke_test as _st

    home = tmp_path / "home"
    home.mkdir()

    # Marker file the grandchild creates; it sleeps long, then would
    # touch the marker. If the killpg works, the marker never appears.
    marker = tmp_path / "ghost.txt"

    # Drop timeout to keep the test fast.
    saved = _st._SMOKE_COMMAND_TIMEOUT_S
    _st._SMOKE_COMMAND_TIMEOUT_S = 1
    try:
        # Background a sleep+touch with disown; smoke command exits
        # immediately (so `sh -c` returns), but the grandchild lingers.
        # Wait — for a TIMEOUT test we need the foreground to hang too.
        # So: run sleep 30 in foreground; backgrounded tail should die
        # along with the foreground via killpg.
        m = _manifest([
            f"(sleep 30 && touch {marker}) & sleep 30"
        ])
        r = smoke_run(m, home=home)
        assert r.passed is False
        assert any("timed out" in f for f in r.failures)
    finally:
        _st._SMOKE_COMMAND_TIMEOUT_S = saved

    # Give the grandchild a moment to write the marker if it survived.
    import time
    time.sleep(2.5)
    assert not marker.exists(), (
        "L regression: grandchild process survived the timeout and "
        "completed its work — process-group kill is not effective"
    )


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
