"""specs/004-mac-compat — Linux ↔ macOS cross-platform tests.

Verifies the v1.1 mac-compat fixes:
  FR-001 _safe_mode_bits classifies by path segments, not substrings
  FR-002 ManifestModel.source_machine_home additive field
  FR-004 rewrite_mcp_servers_for_target_home("darwin") rewrites nvm→bare-cmd
  FR-005 Capability validator rejects case-only-different dest_paths
  FR-006 DEFAULT_BIN_DIRS includes /opt/homebrew on darwin
  FR-008 v1.0 bundles (no source_machine_home) still ingest
"""

from __future__ import annotations

import sys
from datetime import datetime

import pytest

from agent_transfer.bridge.ingest import _safe_mode_bits
from agent_transfer.bridge.models import (
    AssetEntry,
    Capability,
    ManifestModel,
)
from agent_transfer.utils.transfer import rewrite_mcp_servers_for_target_home


# --------------------------------------------------------------------- #
# FR-001: segment-anchored mode-bits classifier                          #
# --------------------------------------------------------------------- #


def test_fr001_library_app_support_bin_jsondata_stays_644():
    """The substring '/bin/' inside an Application Support path must NOT
    trigger the exec bit. macOS-typical destination."""
    m = _safe_mode_bits(
        "~/Library/Application Support/foo/bin/data.json", 0o644
    )
    assert m == 0o644, oct(m)


def test_fr001_user_bin_session_search_keeps_exec():
    """A real ~/bin/<cmd> still gets the exec bit forced on."""
    m = _safe_mode_bits("~/bin/session-search", 0o644)
    assert m & 0o100, oct(m)


def test_fr001_local_bin_keeps_exec():
    m = _safe_mode_bits("~/.local/bin/tool", 0o644)
    assert m & 0o100, oct(m)


def test_fr001_opt_homebrew_bin_keeps_exec():
    m = _safe_mode_bits("/opt/homebrew/bin/gh", 0o644)
    assert m & 0o100, oct(m)


def test_fr001_usr_local_bin_keeps_exec():
    m = _safe_mode_bits("/usr/local/bin/tool", 0o644)
    assert m & 0o100, oct(m)


def test_fr001_hooks_segment_keeps_exec():
    m = _safe_mode_bits("~/.claude/hooks/group/event.sh", 0o644)
    assert m & 0o100, oct(m)


def test_fr001_skills_md_no_exec_even_with_bin_in_name():
    """A skill named 'sbinary.md' must not pick up exec bit."""
    m = _safe_mode_bits("~/.claude/skills/sbinary.md", 0o644)
    assert m == 0o644, oct(m)


# --------------------------------------------------------------------- #
# FR-002 / FR-008: source_machine_home additive field                    #
# --------------------------------------------------------------------- #


def test_fr002_manifest_accepts_source_machine_home():
    m = ManifestModel(
        generated_at=datetime.utcnow(),
        source_machine_hint="darwin",
        source_machine_home="/Users/test",
        capability=Capability(name="t", description="d", intent="i", assets=[]),
        briefing_sections=[],
        confirmations=[],
    )
    assert m.source_machine_home == "/Users/test"


def test_fr008_manifest_source_machine_home_is_optional():
    """A 1.0-shape manifest without source_machine_home still validates."""
    m = ManifestModel(
        generated_at=datetime.utcnow(),
        source_machine_hint="linux-wsl2",
        capability=Capability(name="t", description="d", intent="i", assets=[]),
        briefing_sections=[],
        confirmations=[],
    )
    assert m.source_machine_home is None


# --------------------------------------------------------------------- #
# FR-004: nvm → bare-cmd rewrite for darwin                              #
# --------------------------------------------------------------------- #


def test_fr004_darwin_rewrites_nvm_command_to_bare():
    servers = {
        "npx-server": {
            "command": "/home/linuxuser/.nvm/versions/node/v20.11.0/bin/npx",
            "args": ["mcp-server-foo"],
        }
    }
    classifications: dict[str, dict] = {}
    out = rewrite_mcp_servers_for_target_home(
        servers, classifications,
        target_home="/Users/macuser",
        source_home="/home/linuxuser",
        target_platform="darwin",
    )
    assert out["npx-server"]["command"] == "npx"


def test_fr004_darwin_rewrites_nested_nvm_in_args():
    servers = {
        "x": {
            "command": "node",
            "args": ["/home/u/.nvm/versions/node/v18/bin/node", "script.js"],
        }
    }
    out = rewrite_mcp_servers_for_target_home(
        servers, {},
        target_home="/Users/u",
        source_home="/home/u",
        target_platform="darwin",
    )
    # Nested nvm path in args is reduced to "node"
    assert out["x"]["args"][0] == "node"
    assert out["x"]["args"][1] == "script.js"


def test_fr004_linux_target_preserves_nvm_path():
    """Same target (linux→linux) must NOT rewrite nvm paths."""
    servers = {
        "x": {
            "command": "/home/u/.nvm/versions/node/v20/bin/npx",
            "args": [],
        }
    }
    out = rewrite_mcp_servers_for_target_home(
        servers, {},
        target_home="/home/u",
        source_home="/home/u",
        # target_platform default is None — no darwin rewrite
    )
    assert "/.nvm/" in out["x"]["command"]


def test_fr004_no_double_rewrite_of_bare_command():
    """A command that's already bare (`npx`) is left alone."""
    servers = {"x": {"command": "npx", "args": ["foo"]}}
    out = rewrite_mcp_servers_for_target_home(
        servers, {},
        target_home="/Users/u",
        source_home="/home/u",
        target_platform="darwin",
    )
    assert out["x"]["command"] == "npx"


# --------------------------------------------------------------------- #
# FR-005: case-fold duplicate detection                                  #
# --------------------------------------------------------------------- #


def _asset(dest: str) -> AssetEntry:
    return AssetEntry(
        path=dest.lstrip("~/"),
        dest_path=dest,
        risk="green",
        conflict="overwrite",
        sha256="a" * 64,
        mode_bits=0o644,
        kind="skill",
    )


def test_fr005_capability_rejects_case_only_different_dest_paths():
    with pytest.raises(ValueError, match="case-insensitive"):
        Capability(
            name="t", description="d", intent="i",
            assets=[
                _asset("~/.claude/skills/Foo.md"),
                _asset("~/.claude/skills/foo.md"),
            ],
        )


def test_fr005_capability_accepts_distinct_dest_paths():
    cap = Capability(
        name="t", description="d", intent="i",
        assets=[
            _asset("~/.claude/skills/foo.md"),
            _asset("~/.claude/skills/bar.md"),
        ],
    )
    assert len(cap.assets) == 2


# --------------------------------------------------------------------- #
# FR-006: Homebrew dirs in DEFAULT_BIN_DIRS on darwin                    #
# --------------------------------------------------------------------- #


def test_fr006_default_bin_dirs_includes_homebrew_on_darwin():
    """Verify the platform-aware DEFAULT_BIN_DIRS function. Always
    inspects both branches by re-importing under a sys.platform patch."""
    import importlib

    import agent_transfer.utils.script_discovery as sd

    # Compute the darwin-shape directly via the helper rather than
    # patching sys.platform globally (which would force a re-import
    # cascade through every test).
    expected_darwin = sd._default_bin_dirs.__wrapped__ if hasattr(sd._default_bin_dirs, "__wrapped__") else None
    # Direct inspection: call the helper after monkey-patching sys.platform.
    saved = sys.platform
    try:
        sys.platform = "darwin"
        importlib.reload(sd)
        assert any("/opt/homebrew/bin" in str(p) for p in sd.DEFAULT_BIN_DIRS), (
            f"darwin DEFAULT_BIN_DIRS should include /opt/homebrew/bin; got {sd.DEFAULT_BIN_DIRS}"
        )
        assert any("/opt/homebrew/sbin" in str(p) for p in sd.DEFAULT_BIN_DIRS), (
            f"darwin DEFAULT_BIN_DIRS should include /opt/homebrew/sbin; got {sd.DEFAULT_BIN_DIRS}"
        )
    finally:
        sys.platform = saved
        importlib.reload(sd)


def test_fr006_default_bin_dirs_excludes_homebrew_on_linux():
    import importlib

    import agent_transfer.utils.script_discovery as sd

    saved = sys.platform
    try:
        sys.platform = "linux"
        importlib.reload(sd)
        for p in sd.DEFAULT_BIN_DIRS:
            assert "/opt/homebrew" not in str(p), (
                f"linux DEFAULT_BIN_DIRS must not include Homebrew; got {sd.DEFAULT_BIN_DIRS}"
            )
    finally:
        sys.platform = saved
        importlib.reload(sd)
