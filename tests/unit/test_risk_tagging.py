"""T020 — Unit test: risk-tag classification (FR-008).

Default rules from research.md:
- MCP server with no env / no headers / no warnings → green
- MCP server with env or warnings but no detected secret → yellow
- MCP server with detected secret OR auth headers → red
- Bin script with read-only tokens (grep/find/cat) only → green
- Bin script with state-writing tokens (rm/git push/sed -i/etc.) → red
- Bin script otherwise → yellow
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from agent_transfer.utils.mcp_classifier import classify_servers
from agent_transfer.utils.script_discovery import tag_script


# --- MCP server risk tags --- #


def test_clean_server_is_green():
    res = classify_servers({"clean": {"command": "npx", "args": ["-y", "foo"]}})
    assert res[0].risk_tag == "green"


def test_server_with_env_is_yellow():
    res = classify_servers(
        {"with_env": {"command": "npx", "args": [], "env": {"DEBUG": "true"}}}
    )
    assert res[0].risk_tag == "yellow"


def test_server_with_api_key_env_is_red():
    res = classify_servers(
        {
            "auth": {
                "command": "npx",
                "args": [],
                "env": {"API_KEY": "sk-abcdefghijklmnopqrstuvwxyz12"},
            }
        }
    )
    assert res[0].risk_tag == "red"


def test_server_with_auth_headers_is_red():
    res = classify_servers(
        {
            "http_auth": {
                "url": "https://example.com/mcp",
                "headers": {"Authorization": "Bearer xyz"},
            }
        }
    )
    assert res[0].risk_tag == "red"


# --- Bin script risk tags --- #


@pytest.fixture
def make_script(tmp_path: Path):
    """Return a helper that writes a script with given content and returns path."""

    def _mk(name: str, content: str) -> Path:
        p = tmp_path / name
        p.write_text("#!/usr/bin/env bash\n" + content)
        p.chmod(p.stat().st_mode | stat.S_IXUSR)
        return p

    return _mk


def test_readonly_script_is_green(make_script):
    p = make_script("rdonly", 'grep "$@" /tmp/foo.log\nfind . -name "*.txt"\n')
    assert tag_script(p) == "green"


def test_state_writing_script_is_red(make_script):
    p = make_script("destructive", 'rm -rf /tmp/cache\nfind . -name "*.tmp"\n')
    assert tag_script(p) == "red"


def test_script_with_curl_post_is_red(make_script):
    p = make_script("poster", 'curl -X POST https://api.example.com/foo\n')
    assert tag_script(p) == "red"


def test_script_with_pip_install_is_red(make_script):
    p = make_script("installer", 'pip install requests\n')
    assert tag_script(p) == "red"


def test_neutral_script_is_yellow(make_script):
    p = make_script("neutral", 'date\nuname -a\n')
    assert tag_script(p) == "yellow"


def test_unreadable_script_defaults_to_red(tmp_path):
    fake = tmp_path / "does-not-exist"
    assert tag_script(fake) == "red"
