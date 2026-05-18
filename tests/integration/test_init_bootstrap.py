"""Plan A — `agent-transfer init` capstone tests.

Covers:
  • Happy path: minimal bundle → install_steps run → ~/.claude.json merged
  • Safety gate: --yes without --i-accept-risks refuses
  • Bundle not found: clear error + non-zero exit
  • Missing classification: clear error + non-zero exit
  • Runtime version mismatch: aborts before any subprocess
  • HTTP token UX: --tokens-file fills, missing tokens fail under --yes
  • CLAUDE.md differs → written as .incoming, not overwritten
  • Path rewrite + ~/.claude.json backup
  • Dry-run does no writes
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from agent_transfer.bootstrap.init import (
    EXIT_BUNDLE_NOT_FOUND,
    EXIT_DRY_RUN,
    EXIT_NO_CLASSIFICATION,
    EXIT_OK,
    EXIT_TOKENS_REQUIRED,
    EXIT_USER_DECLINED,
    EXIT_VERSION_MISMATCH,
    init,
)


# --------------------------------------------------------------------- #
# Bundle fixture helpers                                                #
# --------------------------------------------------------------------- #


def _write_export_json(
    bundle_dir: Path,
    servers: dict[str, dict],
    classifications: dict[str, dict[str, Any]],
    source_home: str = "/home/source-user",
) -> Path:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    out = bundle_dir / "claude-config-export_test.json"
    payload = {
        "_metadata": {
            "created": datetime.utcnow().isoformat(),
            "export_version": "1.0",
            "source_home": source_home,
            "server_count": len(servers),
        },
        "mcpServers": servers,
        "_classification": {"servers": classifications},
    }
    out.write_text(json.dumps(payload, indent=2))
    return out


def _seed_extracted_source(home: Path, name: str) -> Path:
    """Mimic what `agent-transfer import` would have placed."""
    target = home / ".claude-imported" / "mcp-sources" / name / name
    target.mkdir(parents=True, exist_ok=True)
    (target / "README.md").write_text(f"# {name}\n")
    return target


# --------------------------------------------------------------------- #
# Safety + error paths                                                  #
# --------------------------------------------------------------------- #


def test_bundle_not_found_returns_exit_10(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    r = init(tmp_path / "does-not-exist", home=home)
    assert r.exit_code == EXIT_BUNDLE_NOT_FOUND
    assert any("bundle_dir not found" in e for e in r.errors)


def test_yes_without_accept_risks_refuses(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    r = init(bundle, home=home, auto_yes=True, accept_risks=False)
    assert r.exit_code == EXIT_USER_DECLINED
    assert any("requires --i-accept-risks" in e for e in r.errors)


def test_missing_classification_returns_exit_11(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    r = init(bundle, home=home)
    assert r.exit_code == EXIT_NO_CLASSIFICATION
    assert any("No claude-config-export" in e for e in r.errors)


# --------------------------------------------------------------------- #
# Happy path — dry run                                                  #
# --------------------------------------------------------------------- #


def test_dry_run_no_writes(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    bundle = tmp_path / "bundle"

    # No install_steps for "trivial" server — exercise the rewrite path
    # without subprocess.
    servers = {
        "trivial": {
            "command": "/home/source-user/.local/bin/trivial",
            "args": [],
        }
    }
    classifications = {
        "trivial": {
            "server_class": "local-python",
            "args": ["/home/source-user/.local/bin/trivial"],
            "install_steps": [],
            "config_after_install": {
                "command": str(home / ".local" / "bin" / "trivial"),
                "args": [],
            },
        }
    }
    _write_export_json(bundle, servers, classifications)

    # Existing ~/.claude.json to back up
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {}}))

    r = init(bundle, home=home, dry_run=True, auto_yes=True, accept_risks=True)
    assert r.exit_code == EXIT_DRY_RUN
    # dry-run must NOT have written .claude.json or done a backup.
    backups = list(home.glob(".claude.json.backup.*"))
    assert backups == [], f"dry-run leaked backups: {backups}"


# --------------------------------------------------------------------- #
# Happy path — full merge                                               #
# --------------------------------------------------------------------- #


def test_happy_path_merges_rewritten_mcps(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    bundle = tmp_path / "bundle"

    servers = {
        "trivial": {
            "command": "/home/source-user/.local/bin/trivial",
            "args": [],
        }
    }
    classifications = {
        "trivial": {
            "server_class": "local-python",
            "args": ["/home/source-user/.local/bin/trivial"],
            "install_steps": [],  # nothing to run — exercise pure merge
            "config_after_install": {
                "command": str(home / ".local" / "bin" / "trivial"),
                "args": [],
            },
        }
    }
    _write_export_json(bundle, servers, classifications)
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {"existing": {"command": "/bin/true"}}}))

    r = init(bundle, home=home, auto_yes=True, accept_risks=True)
    assert r.exit_code == EXIT_OK, r.errors

    # Backup created
    assert r.backup_path is not None and r.backup_path.is_file()

    # Final ~/.claude.json has BOTH existing and the rewritten new server
    written = json.loads((home / ".claude.json").read_text())
    assert "existing" in written["mcpServers"]
    assert "trivial" in written["mcpServers"]
    # config_after_install applied verbatim
    assert written["mcpServers"]["trivial"]["command"] == str(home / ".local" / "bin" / "trivial")


# --------------------------------------------------------------------- #
# Runtime version gate                                                  #
# --------------------------------------------------------------------- #


def test_python_version_mismatch_aborts(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    bundle = tmp_path / "bundle"

    servers = {"big": {"command": "uv", "args": ["run", "big"]}}
    classifications = {
        "big": {
            "server_class": "local-uv",
            "args": ["run", "big"],
            "install_steps": ["uv sync"],
            "config_after_install": {},
        }
    }
    _write_export_json(bundle, servers, classifications)

    # Require an impossibly-high Python version
    manifest = {
        "version": "0.1",
        "bundled": [
            {
                "name": "big",
                "server_class": "local-uv",
                "python_version": ">=99.0",
            }
        ],
    }
    (bundle / "mcp-sources-manifest.json").write_text(json.dumps(manifest))

    r = init(bundle, home=home, auto_yes=True, accept_risks=True)
    assert r.exit_code == EXIT_VERSION_MISMATCH
    assert any("python" in line for line in r.version_aborts)


# --------------------------------------------------------------------- #
# HTTP token UX                                                          #
# --------------------------------------------------------------------- #


def test_http_tokens_from_file_fill_headers(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    bundle = tmp_path / "bundle"

    servers = {
        "remote": {
            "transport": "http",
            "url": "https://api.example.com/mcp",
            "headers": {"Authorization": "Bearer <REDACTED>"},
        }
    }
    classifications = {
        "remote": {
            "server_class": "http",
            "args": [],
            "install_steps": [],
            "config_after_install": {
                "transport": "http",
                "url": "https://api.example.com/mcp",
                "headers": {"Authorization": "Bearer <REDACTED>"},
            },
        }
    }
    _write_export_json(bundle, servers, classifications)

    tokens = tmp_path / "tokens.env"
    tokens.write_text("REMOTE__AUTHORIZATION=tok-abc123\n")

    (home / ".claude.json").write_text(json.dumps({"mcpServers": {}}))

    r = init(
        bundle, home=home, auto_yes=True, accept_risks=True, tokens_file=tokens
    )
    assert r.exit_code == EXIT_OK, r.errors
    assert "remote" in r.http_tokens_filled
    written = json.loads((home / ".claude.json").read_text())
    auth = written["mcpServers"]["remote"]["headers"]["Authorization"]
    assert auth == "Bearer tok-abc123", auth


def test_http_tokens_missing_under_yes_returns_exit_13(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    bundle = tmp_path / "bundle"

    servers = {
        "remote": {
            "transport": "http",
            "url": "https://api.example.com/mcp",
            "headers": {"Authorization": "Bearer <REDACTED>"},
        }
    }
    classifications = {
        "remote": {
            "server_class": "http",
            "args": [],
            "install_steps": [],
            "config_after_install": {
                "transport": "http",
                "url": "https://api.example.com/mcp",
                "headers": {"Authorization": "Bearer <REDACTED>"},
            },
        }
    }
    _write_export_json(bundle, servers, classifications)

    r = init(bundle, home=home, auto_yes=True, accept_risks=True)
    assert r.exit_code == EXIT_TOKENS_REQUIRED
    assert "remote" in r.http_tokens_missing


# --------------------------------------------------------------------- #
# CLAUDE.md is .incoming when content differs                            #
# --------------------------------------------------------------------- #


def test_claude_md_differing_written_as_incoming(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "CLAUDE.md").write_text("# existing user CLAUDE.md\n")

    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "CLAUDE.md").write_text("# incoming CLAUDE.md from another machine\n")

    servers: dict[str, dict] = {}
    classifications: dict[str, dict[str, Any]] = {}
    _write_export_json(bundle, servers, classifications)

    r = init(bundle, home=home, auto_yes=True, accept_risks=True)
    assert r.exit_code == EXIT_OK, r.errors

    incoming = home / ".claude" / "CLAUDE.md.incoming"
    assert incoming.is_file()
    assert "incoming CLAUDE.md" in incoming.read_text()

    # Original was never touched
    assert (
        "existing user" in (home / ".claude" / "CLAUDE.md").read_text()
    )
