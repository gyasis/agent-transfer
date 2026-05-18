"""v1.1 — AssetEntry.kind + behavior_md + back-compat.

Covers Plan B acceptance:
  • Kind populated on emitted assets (composer path)
  • Literal rejects unknown kind values
  • behavior_md auto-extracted for skill/rule + bin/hook
  • --behavior CLI override wins over auto-extraction
  • Vacuous description refused (exit 7)
  • DESCRIPTION_UNSET_SENTINEL bypasses refusal
  • kind="other" refused at seal (model validator)
  • 1.0.x bundle ingests with kind inferred + DeprecationWarning
  • 2.x bundle rejected at ingest with clear error
  • Briefing template renders §3 behavior subsection + §8 Risk Mapping
"""

from __future__ import annotations

import hashlib
import json
import stat
import warnings
from datetime import datetime
from pathlib import Path

import pytest

from agent_transfer.bridge.compose import (
    DESCRIPTION_UNSET_SENTINEL,
    EXIT_VACUOUS_DESCRIPTION,
    _extract_behavior_md,
    _extract_frontmatter_description,
    compose,
)
from agent_transfer.bridge.models import (
    AssetEntry,
    BriefingSection,
    Capability,
    ManifestModel,
    SCHEMA_VERSION,
)


def _seed_skill(home: Path, slug: str, body: str) -> Path:
    p = home / ".claude" / "skills" / f"{slug}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


def _seed_bin(home: Path, name: str, body: str) -> Path:
    p = home / "bin" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    p.chmod(p.stat().st_mode | stat.S_IXUSR)
    return p


# --------------------------------------------------------------------- #
# Schema-version constant + AssetEntry validator                        #
# --------------------------------------------------------------------- #


def test_schema_version_is_1_1_0():
    assert SCHEMA_VERSION == "1.1.0"


def test_asset_entry_kind_literal_rejects_unknown():
    with pytest.raises(Exception):
        AssetEntry(
            path="x",
            dest_path="~/x",
            risk="green",
            conflict="skip",
            sha256="a" * 64,
            mode_bits=0o644,
            kind="bogus",  # type: ignore[arg-type]
        )


def test_asset_entry_refuses_kind_other_at_seal():
    with pytest.raises(Exception, match="kind='other' is not permitted"):
        AssetEntry(
            path="x",
            dest_path="~/x",
            risk="green",
            conflict="skip",
            sha256="a" * 64,
            mode_bits=0o644,
            kind="other",
        )


# --------------------------------------------------------------------- #
# Compose path — kind + behavior_md emitted                             #
# --------------------------------------------------------------------- #


def test_compose_populates_kind_on_every_asset(tmp_path):
    home = tmp_path / "home"
    _seed_skill(
        home,
        "session-search",
        "---\ndescription: Search past Claude sessions\n---\n# session-search\n\nMines JSONL transcripts.\n",
    )
    cap = compose("session-search", home=home)
    assert cap.assets, "expected at least one CORE asset"
    for a in cap.assets:
        assert a.kind in {"skill", "rule", "hook", "bin", "capability"}


def test_compose_extracts_behavior_md_for_core_skill(tmp_path):
    home = tmp_path / "home"
    _seed_skill(
        home,
        "memory-recall",
        "---\ndescription: Recall how a task was solved\n---\n# memory-recall\n\nThis skill walks the JSONL backwards to find a prior fix.\n",
    )
    cap = compose("memory-recall", home=home)
    core = [a for a in cap.assets if (a.notes or "").startswith("tier=CORE")]
    assert core
    # Either the frontmatter description (chosen for capability.description)
    # OR the first paragraph should populate behavior_md on at least one CORE.
    assert any(a.behavior_md for a in core), (
        "expected at least one CORE asset to have a behavior_md hint"
    )


def test_compose_behavior_override_wins(tmp_path):
    home = tmp_path / "home"
    skill_path = _seed_skill(
        home,
        "ix-build",
        "---\ndescription: Build the index\n---\n# ix-build\n\nDefault paragraph.\n",
    )
    override_text = "Custom user-supplied behavior summary."
    dest_path = f"~/.claude/skills/{skill_path.stem}.md"
    cap = compose(
        "ix-build",
        home=home,
        behavior_overrides={dest_path: override_text},
    )
    matching = [a for a in cap.assets if a.dest_path == dest_path]
    assert matching, "skill should be in the bundle"
    assert matching[0].behavior_md == override_text


def test_compose_bin_anchored_has_comment_block_as_behavior(tmp_path):
    home = tmp_path / "home"
    _seed_bin(
        home,
        "session-search",
        "#!/usr/bin/env bash\n# session-search — token-efficient JSONL miner.\n# Used by the cascade-memory skill.\necho hi\n",
    )
    cap = compose("session-search", home=home)
    bin_assets = [a for a in cap.assets if a.kind == "bin"]
    assert bin_assets
    assert any("token-efficient JSONL miner" in (a.behavior_md or "") for a in bin_assets)


# --------------------------------------------------------------------- #
# Vacuous description refusal                                           #
# --------------------------------------------------------------------- #


def test_compose_refuses_vacuous_description_no_fallback(tmp_path):
    """A CORE skill with no frontmatter + no body paragraph triggers exit 7."""
    home = tmp_path / "home"
    # Truly empty body (only a heading) — _extract_behavior_md strips the
    # `#` and returns the same heading, which would actually satisfy. To
    # genuinely trigger refusal we need NO frontmatter description AND
    # NO non-blank content.
    _seed_skill(home, "empty-skill", "")
    with pytest.raises(SystemExit) as ei:
        compose("empty-skill", home=home)
    assert ei.value.code == EXIT_VACUOUS_DESCRIPTION


def test_compose_accepts_unset_sentinel(tmp_path):
    home = tmp_path / "home"
    _seed_skill(home, "anon", "")
    cap = compose("anon", home=home, description=DESCRIPTION_UNSET_SENTINEL)
    assert "unset" in cap.description.lower()
    assert "anon" in cap.description


def test_compose_user_description_wins(tmp_path):
    home = tmp_path / "home"
    _seed_skill(
        home,
        "ix-rebuild",
        "---\ndescription: Auto-extracted description\n---\n# ix-rebuild\n",
    )
    cap = compose(
        "ix-rebuild",
        home=home,
        description="User-provided description",
    )
    assert cap.description == "User-provided description"


# --------------------------------------------------------------------- #
# Behavior extractor helpers (unit-level)                               #
# --------------------------------------------------------------------- #


def test_extract_frontmatter_description_returns_value(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("---\ndescription: One-liner of what this does\n---\n# Body\n")
    assert _extract_frontmatter_description(p) == "One-liner of what this does"


def test_extract_frontmatter_description_returns_none_when_missing(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("# Body only\n\nNo frontmatter.\n")
    assert _extract_frontmatter_description(p) is None


def test_extract_behavior_md_skill_skips_frontmatter(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("---\nname: x\n---\n# Heading\n\nThis is the first real paragraph.\n")
    out = _extract_behavior_md(p, "skill")
    assert out is not None
    assert "first real paragraph" in out or "Heading" in out


def test_extract_behavior_md_bin_returns_comment_block(tmp_path):
    p = tmp_path / "tool"
    p.write_text(
        "#!/usr/bin/env bash\n# Tool: do the thing.\n# Used by widget X.\n\necho hi\n"
    )
    out = _extract_behavior_md(p, "bin")
    assert out is not None
    assert "Tool: do the thing" in out


# --------------------------------------------------------------------- #
# Ingest back-compat                                                    #
# --------------------------------------------------------------------- #


def test_ingest_1_0_bundle_infers_kind_with_deprecation_warning(tmp_path):
    """A 1.0.x manifest (no `kind` field) ingests with kind inferred."""
    from agent_transfer.bridge.ingest import ingest

    home = tmp_path / "home"
    (home / ".claude" / "skills").mkdir(parents=True)
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "bundle").mkdir()
    src = bundle / "bundle" / "test.md"
    src.write_text("# test skill\n")
    sha = hashlib.sha256(src.read_bytes()).hexdigest()

    legacy = {
        "schema_version": "1.0.0",
        "generated_at": datetime.utcnow().isoformat(),
        "source_machine_hint": "test",
        "capability": {
            "name": "t",
            "description": "x",
            "intent": "x",
            "assets": [
                {
                    "path": "test.md",
                    "dest_path": "~/.claude/skills/test.md",
                    "risk": "green",
                    "conflict": "overwrite",
                    "sha256": sha,
                    "mode_bits": 0o644,
                    # NOTE: no "kind" — that's the 1.0.x shape
                }
            ],
            "dependencies": [],
        },
        "briefing_sections": [],
        "confirmations": [],
    }
    (bundle / "manifest.json").write_text(json.dumps(legacy))

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        r = ingest(bundle, home=home, auto_yes=True, interactive=False)

    # 1.0 ingest should emit a DeprecationWarning mentioning the version.
    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert any("1.0" in str(w.message) for w in deprecations), (
        f"expected DeprecationWarning mentioning 1.0; got: "
        f"{[str(w.message) for w in deprecations]}"
    )
    assert not r.errors, f"1.0 bundle should ingest cleanly; errors: {r.errors}"


def test_ingest_2_x_bundle_rejected(tmp_path):
    """A 2.x manifest is hard-rejected with a clear error."""
    from agent_transfer.bridge.ingest import ingest

    home = tmp_path / "home"
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    future = {
        "schema_version": "2.0.0",
        "generated_at": datetime.utcnow().isoformat(),
        "source_machine_hint": "test",
        "capability": {"name": "t", "description": "x", "intent": "x", "assets": []},
        "briefing_sections": [],
        "confirmations": [],
    }
    (bundle / "manifest.json").write_text(json.dumps(future))

    r = ingest(bundle, home=home, auto_yes=True, interactive=False)
    assert r.errors
    assert any("2.0" in e or "not 1.x" in e for e in r.errors)


# --------------------------------------------------------------------- #
# Briefing — §3 behavior subsection + §8 Risk Mapping                   #
# --------------------------------------------------------------------- #


def test_briefing_renders_behavior_subsection_and_risk_mapping(tmp_path):
    from agent_transfer.bridge.briefing import render

    asset = AssetEntry(
        path=".claude/skills/foo.md",
        dest_path="~/.claude/skills/foo.md",
        risk="green",
        conflict="overwrite",
        sha256="a" * 64,
        mode_bits=0o644,
        notes="tier=CORE",
        kind="skill",
        behavior_md="Indexes the embedding store nightly.",
    )
    m = ManifestModel(
        generated_at=datetime.utcnow(),
        source_machine_hint="test",
        capability=Capability(
            name="foo", description="d", intent="i", assets=[asset]
        ),
        briefing_sections=[],
        confirmations=[],
    )
    out = render(m)
    # Per-asset Behavior subsection (under §3 Inventory) must show behavior_md
    assert "Indexes the embedding store nightly." in out
    # §8 Risk Mapping appendix must be present with the kind→harness header
    assert "## 8. Risk Mapping" in out
    assert "OpenClaw" in out
    assert "PromptChain" in out
