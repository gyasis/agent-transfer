"""T038 — SC-009 post-ship validation: prd-planning capability roundtrip.

Story 2 from spec.md. Exercises the COMBINATION of binary + skill +
hook + settings.json fragment + companion skills + rule. The hook is
RED-tier (it enforces blocking behavior).

This test is post-ship validation, NOT a ship blocker. If MVP shipped
on Wave 6's SC-001, this proves the architecture extends to the
prd-planning shape.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agent_transfer.bridge.briefing import render as _render, render_sections
from agent_transfer.bridge.ingest import ingest
from agent_transfer.bridge.models import (
    AssetEntry,
    Capability,
    ManifestModel,
)
from agent_transfer.bridge.rollback import snapshot as _rollback_snapshot


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _build_prd_bundle(tmp_path: Path) -> Path:
    """Hand-build a minimal prd-planning bundle.

    Faster + more deterministic than running compose() against a fixture
    that would itself need the full prd ecosystem reproduced.
    """
    bundle = tmp_path / "bundle-prd-planning"
    bundle.mkdir()
    asset_root = bundle / "bundle"
    asset_root.mkdir()

    # 1. The prd CLI binary
    prd_bin_bytes = b"#!/usr/bin/env bash\n# prd CLI stub for test\necho prd $@\n"
    (asset_root / "bin").mkdir()
    (asset_root / "bin" / "prd").write_bytes(prd_bin_bytes)
    (asset_root / "bin" / "prd").chmod(0o755)

    # 2. The prd skill markdown
    prd_skill_bytes = b"---\nname: prd\ndescription: PRD lifecycle CLI\n---\n# prd\n"
    (asset_root / ".claude" / "skills").mkdir(parents=True)
    (asset_root / ".claude" / "skills" / "prd.md").write_bytes(prd_skill_bytes)

    # 3. The plan-persistence rule
    rule_bytes = b"# Plan & Task Persistence\nDecision Rule for prd new vs append-note...\n"
    (asset_root / ".claude" / "rules" / "domains").mkdir(parents=True)
    (asset_root / ".claude" / "rules" / "domains" / "plan-persistence.md").write_bytes(rule_bytes)

    # 4. The prd-guard hook
    hook_bytes = b"#!/usr/bin/env bash\n# prd-guard PreToolUse hook\nexit 0\n"
    (asset_root / ".claude" / "hooks" / "prd-guard").mkdir(parents=True)
    (asset_root / ".claude" / "hooks" / "prd-guard" / "pre-tool-use.sh").write_bytes(hook_bytes)
    (asset_root / ".claude" / "hooks" / "prd-guard" / "pre-tool-use.sh").chmod(0o755)

    # 5. The settings.json fragment that wires the hook
    settings_fragment = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Edit|Write|MultiEdit",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "$HOME/.claude/hooks/prd-guard/pre-tool-use.sh",
                        }
                    ],
                }
            ]
        }
    }
    settings_fragment_bytes = json.dumps(settings_fragment, indent=2).encode("utf-8")
    (asset_root / ".claude" / "settings.json").write_bytes(settings_fragment_bytes)

    # Build manifest
    assets = [
        AssetEntry(
            path="bin/prd",
            dest_path="~/bin/prd",
            risk="red",  # state-writing CLI
            conflict="ask",
            sha256=_sha(prd_bin_bytes),
            mode_bits=0o755,
            kind="bin",
        ),
        AssetEntry(
            path=".claude/skills/prd.md",
            dest_path="~/.claude/skills/prd.md",
            risk="green",
            conflict="overwrite",
            sha256=_sha(prd_skill_bytes),
            mode_bits=0o644,
            kind="skill",
        ),
        AssetEntry(
            path=".claude/rules/domains/plan-persistence.md",
            dest_path="~/.claude/rules/domains/plan-persistence.md",
            risk="green",
            conflict="overwrite",
            sha256=_sha(rule_bytes),
            mode_bits=0o644,
            kind="rule",
        ),
        AssetEntry(
            path=".claude/hooks/prd-guard/pre-tool-use.sh",
            dest_path="~/.claude/hooks/prd-guard/pre-tool-use.sh",
            risk="red",  # PreToolUse hook — blocks tool calls
            conflict="ask",
            sha256=_sha(hook_bytes),
            mode_bits=0o755,
            kind="hook",
        ),
        AssetEntry(
            path=".claude/settings.json",
            dest_path="~/.claude/settings.json",
            risk="yellow",  # settings fragment
            conflict="merge",
            sha256=_sha(settings_fragment_bytes),
            mode_bits=0o644,
            kind="capability",
        ),
    ]
    cap = Capability(
        name="prd-planning",
        description="PRD lifecycle CLI + skill + guard hook + persistence rule.",
        intent="Persist multi-step plans across compactions and sessions.",
        assets=assets,
        dependencies=[],
    )
    manifest = ManifestModel(
        generated_at=datetime.now(timezone.utc),
        source_machine_hint="linux-wsl2",
        capability=cap,
    )
    manifest = manifest.model_copy(update={"briefing_sections": render_sections(manifest)})

    (bundle / "manifest.json").write_text(
        json.dumps(json.loads(manifest.model_dump_json()), indent=2)
    )
    (bundle / "BRIEFING.md").write_text(_render(manifest))

    _rollback_snapshot(
        [a.dest_path for a in cap.assets], bundle, home=tmp_path / "src-home"
    )
    return bundle


def test_prd_capability_roundtrip(tmp_path: Path):
    """SC-009 — prd-planning round-trips with binary, skill, hook, rule, settings.json."""
    (tmp_path / "src-home").mkdir()
    bundle = _build_prd_bundle(tmp_path)

    sandbox = tmp_path / "dst-home"
    sandbox.mkdir()
    (sandbox / ".claude").mkdir()

    result = ingest(bundle, home=sandbox, auto_yes=True, interactive=False)

    assert not result.errors, f"errors: {result.errors}"

    # Binary present + executable
    prd = sandbox / "bin" / "prd"
    assert prd.exists()
    assert prd.stat().st_mode & 0o111

    # Skill present
    assert (sandbox / ".claude" / "skills" / "prd.md").exists()

    # Hook present + executable
    hook = sandbox / ".claude" / "hooks" / "prd-guard" / "pre-tool-use.sh"
    assert hook.exists()
    assert hook.stat().st_mode & 0o111

    # Rule present
    assert (sandbox / ".claude" / "rules" / "domains" / "plan-persistence.md").exists()

    # settings.json was merged (not overwritten) — and it's idempotent
    settings_path = sandbox / ".claude" / "settings.json"
    assert settings_path.exists()
    after = json.loads(settings_path.read_text())
    assert "hooks" in after
    assert "PreToolUse" in after["hooks"]
    assert after["hooks"]["PreToolUse"], "PreToolUse hook entries empty"


def test_prd_settings_merge_does_not_clobber_existing_user_hooks(tmp_path: Path):
    """User had a different hook configured; ingest must NOT remove it."""
    (tmp_path / "src-home").mkdir()
    bundle = _build_prd_bundle(tmp_path)

    sandbox = tmp_path / "dst-home"
    sandbox.mkdir()
    (sandbox / ".claude").mkdir()
    pre_existing = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "/user/own/hook.sh"}]}
            ]
        },
        "theme": "dark",
    }
    (sandbox / ".claude" / "settings.json").write_text(json.dumps(pre_existing, indent=2))

    result = ingest(bundle, home=sandbox, auto_yes=True, interactive=False)
    assert not result.errors

    after = json.loads((sandbox / ".claude" / "settings.json").read_text())
    assert after["theme"] == "dark", "user scalar preference clobbered"
    assert any(
        h.get("matcher") == "Bash" for h in after["hooks"]["PreToolUse"]
    ), "user's pre-existing PreToolUse hook removed"
    assert any(
        h.get("matcher", "").startswith("Edit") for h in after["hooks"]["PreToolUse"]
    ), "bundle's prd-guard hook entry not added"


def test_prd_ingest_twice_idempotent_settings(tmp_path: Path):
    """Re-running ingest must not duplicate hook entries (FR-014)."""
    (tmp_path / "src-home").mkdir()
    bundle = _build_prd_bundle(tmp_path)

    sandbox = tmp_path / "dst-home"
    sandbox.mkdir()
    (sandbox / ".claude").mkdir()

    ingest(bundle, home=sandbox, auto_yes=True, interactive=False)
    after_first = json.loads((sandbox / ".claude" / "settings.json").read_text())

    ingest(bundle, home=sandbox, auto_yes=True, interactive=False)
    after_second = json.loads((sandbox / ".claude" / "settings.json").read_text())

    assert after_first == after_second, "second ingest changed settings.json"
