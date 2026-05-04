"""T021 — Integration test: ~/.claude.json mcpServers path-rewrite on import.

FR-015 / parent-PRD M1.2 — paths from source machine become destination paths.
"""

from __future__ import annotations

from agent_transfer.utils.transfer import rewrite_mcp_servers_for_target_home


def test_classification_overrides_source_paths():
    """When classifier provides config_after_install, it wins verbatim."""
    servers = {
        "memory": {
            "command": "/home/src-user/.nvm/versions/node/v20.10.0/bin/node",
            "args": ["/home/src-user/projects/foo/dist/index.js"],
        }
    }
    classifications = {
        "memory": {
            "config_after_install": {
                "command": "node",
                "args": ["/home/dst-user/projects/foo/dist/index.js"],
            }
        }
    }
    out = rewrite_mcp_servers_for_target_home(
        servers=servers,
        classifications=classifications,
        target_home="/home/dst-user",
        source_home="/home/src-user",
    )
    assert out["memory"]["command"] == "node"
    assert out["memory"]["args"][0].startswith("/home/dst-user/")


def test_fallback_string_substitution():
    """Without classifier metadata, falls back to source_home → target_home swap."""
    servers = {
        "x": {
            "command": "/home/src-user/bin/foo",
            "args": ["--cfg", "/home/src-user/.config/foo.json"],
            "env": {"DATA": "/home/src-user/data"},
        }
    }
    out = rewrite_mcp_servers_for_target_home(
        servers=servers,
        classifications={},
        target_home="/home/dst",
        source_home="/home/src-user",
    )
    assert out["x"]["command"] == "/home/dst/bin/foo"
    assert out["x"]["args"][1] == "/home/dst/.config/foo.json"
    assert out["x"]["env"]["DATA"] == "/home/dst/data"


def test_no_change_when_homes_match():
    """Same source and target → identity transformation."""
    servers = {"x": {"command": "/home/u/bin/y", "args": []}}
    out = rewrite_mcp_servers_for_target_home(
        servers=servers,
        classifications={},
        target_home="/home/u",
        source_home="/home/u",
    )
    assert out == {"x": {"command": "/home/u/bin/y", "args": []}}


def test_input_not_mutated():
    """Function must not modify caller's dict."""
    servers = {"x": {"command": "/home/src/bin/y", "args": []}}
    snapshot = {k: dict(v) for k, v in servers.items()}
    rewrite_mcp_servers_for_target_home(
        servers=servers,
        classifications={},
        target_home="/home/dst",
        source_home="/home/src",
    )
    assert servers == snapshot, "input mutated"
