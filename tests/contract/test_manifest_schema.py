"""T017 — Contract test: ManifestModel ↔ JSON schema round-trip.

Asserts the Pydantic model and the on-disk schema agree, and that an
example round-trips through JSON without loss.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_transfer.bridge.models import (
    AssetEntry,
    BriefingSection,
    Capability,
    Confirmation,
    ManifestModel,
)


SCHEMA_PATH = Path(__file__).resolve().parents[2] / "specs" / "003-agentbridge-mvp" / "contracts" / "manifest.schema.json"


def test_schema_file_exists():
    assert SCHEMA_PATH.exists(), f"Missing contract schema at {SCHEMA_PATH}"


def test_schema_matches_model():
    """The JSON schema generated NOW should equal the contract on disk."""
    fresh = ManifestModel.model_json_schema()
    on_disk = json.loads(SCHEMA_PATH.read_text())
    assert fresh == on_disk, (
        "manifest.schema.json is out of sync with ManifestModel. "
        "Regenerate via: python -c 'from agent_transfer.bridge.models import ManifestModel; "
        "import json; print(json.dumps(ManifestModel.model_json_schema(), indent=2))' "
        "> specs/003-agentbridge-mvp/contracts/manifest.schema.json"
    )


def _example_manifest() -> ManifestModel:
    return ManifestModel(
        generated_at="2026-05-04T10:00:00Z",
        source_machine_hint="linux-wsl2",
        capability=Capability(
            name="cascade-memory",
            description="L1.5 anchor for past-session search",
            intent="Recover prior context across compactions",
            assets=[
                AssetEntry(
                    path="bin/session-search",
                    dest_path="~/bin/session-search",
                    risk="red",
                    conflict="ask",
                    sha256="a" * 64,
                    mode_bits=0o755,
                    notes="executable bit must survive round-trip",
                ),
            ],
            dependencies=["ripgrep"],
        ),
        briefing_sections=[
            BriefingSection(name="identity", content_md="# Identity\n..."),
        ],
        confirmations=[
            Confirmation(
                asset_path="~/bin/session-search",
                risk="red",
                decided_at="2026-05-04T10:01:00Z",
                user_choice="yes",
            ),
        ],
    )


def test_roundtrip_through_json():
    m = _example_manifest()
    blob = m.model_dump_json()
    again = ManifestModel.model_validate_json(blob)
    assert again == m


@pytest.mark.parametrize("bad_risk", ["RED", "Yellow", "blue", "", "  "])
def test_invalid_risk_tag_rejected(bad_risk):
    with pytest.raises(Exception):
        AssetEntry(
            path="x",
            dest_path="~/x",
            risk=bad_risk,  # type: ignore[arg-type]
            conflict="ask",
            sha256="a" * 64,
            mode_bits=0o644,
        )


@pytest.mark.parametrize("bad_conflict", ["SKIP", "Merge", "abort", ""])
def test_invalid_conflict_rejected(bad_conflict):
    with pytest.raises(Exception):
        AssetEntry(
            path="x",
            dest_path="~/x",
            risk="green",
            conflict=bad_conflict,  # type: ignore[arg-type]
            sha256="a" * 64,
            mode_bits=0o644,
        )


def test_negative_mode_bits_rejected():
    with pytest.raises(Exception):
        AssetEntry(
            path="x",
            dest_path="~/x",
            risk="green",
            conflict="skip",
            sha256="a" * 64,
            mode_bits=-1,
        )
