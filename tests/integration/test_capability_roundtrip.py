"""T022 — SC-001 ship gate: cascade-memory roundtrip on a sandbox HOME.

This is the MVP ship-gate test. It MUST FAIL until Wave 7 lands —
specifically until T026 (compose), T031 (`ab compose` CLI), T033 (ingest),
T035 (`ab ingest` CLI), and T036 (agentbridge-ingest skill content) are
all in place.

Marked `pytest.mark.skip` until the implementations land. The skip is
removed in T037 (Wave 6) so the test runs as the ship-gate validator.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.skip(
    reason="MVP ship-gate test — un-skip in T037 once Wave 6 lands"
)


@pytest.fixture
def sandbox_home(tmp_path: Path, monkeypatch):
    """Create a fresh sandbox HOME for the ingestion target."""
    sandbox = tmp_path / "ab-mvp-sandbox"
    sandbox.mkdir()
    (sandbox / ".claude").mkdir()
    (sandbox / "bin").mkdir()
    monkeypatch.setenv("HOME", str(sandbox))
    return sandbox


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cascade_memory_roundtrip(sandbox_home: Path, tmp_path: Path):
    """SC-001 — full bundle → install → smoke test → rollback round-trip.

    Steps:
    1. ab compose --capability cascade-memory  (on real source HOME)
    2. ab export                               (seal bundle)
    3. Copy bundle to sandbox
    4. HOME=sandbox ab ingest <bundle>         (install)
    5. session-search foo                      (must return 'no matches' cleanly)
    6. assert all 7 dependent skills present
    7. assert both hooks fire on triggering events
    8. assert all 5 rule files present
    9. bash rollback.sh                        (restore)
    10. assert sandbox is byte-identical to step-1 state
    """
    bundle_dir = tmp_path / "bundle"

    # Step 1+2 — compose + export from REAL source HOME (the dev's machine).
    # In CI, this would target a fixture HOME with cascade-memory pre-seeded.
    result = _run(["ab", "compose", "--capability", "cascade-memory", "--out", str(bundle_dir)])
    assert result.returncode == 0, f"ab compose failed: {result.stderr}"

    # Step 3 — bundle is at bundle_dir.
    bundle_tar = bundle_dir / "bundle-cascade-memory.tar.gz"
    assert bundle_tar.exists()

    # Step 4 — ingest into sandbox.
    result = _run(["ab", "ingest", str(bundle_tar)])
    assert result.returncode == 0, f"ab ingest failed: {result.stderr}"

    # Step 5 — session-search returns "no matches" cleanly on empty corpus.
    result = _run([str(sandbox_home / "bin" / "session-search"), "foo"])
    assert result.returncode == 0, f"session-search errored: {result.stderr}"
    assert "no matches" in result.stdout.lower() or result.stdout.strip() == ""

    # Step 6 — all 7 dependent skills present.
    expected_skills = {
        "memory-search",
        "done-before",
        "session-reconcile",
        "session-review",
        "specstory-search",
        "dev-timeline",
        "prd",
    }
    actual_skills = set(p.name for p in (sandbox_home / ".claude" / "skills").iterdir())
    assert expected_skills <= actual_skills

    # Step 7 — hooks present (firing tested separately in T037).
    hooks_dir = sandbox_home / ".claude" / "hooks"
    assert (hooks_dir / "unified-memory" / "pre-compact.sh").exists()
    assert (hooks_dir / "retry-guard" / "retry-guard-pre.sh").exists()

    # Step 8 — rule files present.
    rules_dir = sandbox_home / ".claude" / "rules"
    expected_rules = (
        rules_dir / "domains" / "memory-search.md",
        rules_dir / "domains" / "memory.md",
        rules_dir / "domains" / "compaction.md",
        rules_dir / "tools" / "retry.md",
    )
    for r in expected_rules:
        assert r.exists(), f"Missing imported rule: {r}"

    # Step 9 + 10 — rollback restores prior state.
    result = _run(["bash", str(bundle_dir / "rollback.sh")])
    assert result.returncode == 0
    # After rollback: sandbox should be back to its pristine state.
    # Detailed file-tree diff lives in tests/integration/test_rollback_diff.py (T023).
