"""H2 — shared hook files merge by section markers.

Pre-fix bug: shared hook files like ~/.claude/hooks/session-start.sh are
co-owned by multiple capabilities (memory + retry-guard + sio + specstory).
The composer pulled them as whole-file assets; ingest's overwrite path
would clobber peer-owned sections; rollback would clobber the destination's
NEW peer additions made since.

Post-fix:
- Top-level hook files default to conflict=merge (section-marker mode).
- _merge_shell extracts the agentbridge:<name> block and replaces in-place
  or appends, preserving everything outside the block.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_transfer.bridge.ingest import (
    _merge_shell,
    _MarkdownMergeError,
)
from agent_transfer.utils.config_manager import emit_asset_entries


def _seed_hook(home: Path, rel: str, content: str) -> Path:
    p = home / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


# -- Default conflict policy ------------------------------------------------


def test_h2_top_level_hook_defaults_to_merge(tmp_path):
    """session-start.sh is at top-level of hooks/ → default conflict=merge."""
    home = tmp_path / "home"
    p = _seed_hook(home, ".claude/hooks/session-start.sh", "#!/bin/bash\n")

    [entry] = emit_asset_entries([p], home=home)
    assert entry["conflict"] == "merge"
    assert entry["risk"] == "red"


def test_h2_subdir_hook_defaults_to_overwrite(tmp_path):
    """Subdir hook (retry-guard/run.sh) is owned by retry-guard, not shared."""
    home = tmp_path / "home"
    p = _seed_hook(home, ".claude/hooks/retry-guard/run.sh", "#!/bin/bash\n")

    [entry] = emit_asset_entries([p], home=home)
    assert entry["conflict"] == "overwrite"


# -- Shell section merge ----------------------------------------------------


def test_h2_merge_appends_when_block_absent(tmp_path):
    target = tmp_path / "session-start.sh"
    target.write_text(
        "#!/bin/bash\n"
        "# user's existing pre-startup logic\n"
        "echo starting\n"
    )

    incoming = (
        "# BEGIN agentbridge:sio\n"
        "sio briefing 2>/dev/null || true\n"
        "# END agentbridge:sio\n"
    )
    _merge_shell(target, incoming)

    out = target.read_text()
    assert "echo starting" in out, "user's existing logic must survive"
    assert "# BEGIN agentbridge:sio" in out
    assert "sio briefing" in out


def test_h2_merge_replaces_block_idempotent(tmp_path):
    """Second ingest of an updated fragment replaces in-place."""
    target = tmp_path / "session-start.sh"
    target.write_text(
        "#!/bin/bash\n"
        "# memory hook\n"
        "load_memory\n\n"
        "# BEGIN agentbridge:sio\n"
        "OLD_SIO_LINE\n"
        "# END agentbridge:sio\n\n"
        "# specstory hook\n"
        "specstory_sync\n"
    )

    incoming = (
        "# BEGIN agentbridge:sio\n"
        "NEW_SIO_LINE_v2\n"
        "# END agentbridge:sio\n"
    )
    _merge_shell(target, incoming)
    out = target.read_text()

    assert "load_memory" in out
    assert "specstory_sync" in out
    assert "OLD_SIO_LINE" not in out
    assert "NEW_SIO_LINE_v2" in out
    assert out.count("BEGIN agentbridge:sio") == 1


def test_h2_merge_does_not_touch_other_capability_blocks(tmp_path):
    target = tmp_path / "session-start.sh"
    target.write_text(
        "#!/bin/bash\n\n"
        "# BEGIN agentbridge:cascade-memory\n"
        "memory_logic\n"
        "# END agentbridge:cascade-memory\n\n"
        "# BEGIN agentbridge:sio\n"
        "old_sio\n"
        "# END agentbridge:sio\n"
    )

    incoming = (
        "# BEGIN agentbridge:sio\n"
        "new_sio\n"
        "# END agentbridge:sio\n"
    )
    _merge_shell(target, incoming)
    out = target.read_text()

    assert "memory_logic" in out
    assert "new_sio" in out
    assert "old_sio" not in out


def test_h2_merge_rejects_no_markers(tmp_path):
    target = tmp_path / "session-start.sh"
    target.write_text("#!/bin/bash\n")
    with pytest.raises(_MarkdownMergeError, match="exactly one"):
        _merge_shell(target, "raw_command_no_markers\n")


def test_h2_merge_handles_indentation_in_markers(tmp_path):
    """Marker lines with leading whitespace are still recognized."""
    target = tmp_path / "session-start.sh"
    target.write_text(
        "#!/bin/bash\n"
        "if true; then\n"
        "    # BEGIN agentbridge:sio\n"
        "    OLD\n"
        "    # END agentbridge:sio\n"
        "fi\n"
    )

    incoming = (
        "# BEGIN agentbridge:sio\n"
        "NEW\n"
        "# END agentbridge:sio\n"
    )
    _merge_shell(target, incoming)
    out = target.read_text()

    assert "OLD" not in out
    assert "NEW" in out
    assert "if true" in out  # surrounding scaffold preserved
