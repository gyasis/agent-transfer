"""T018 — Contract test: BRIEFING.md must contain all 7 mandatory sections.

The 7 sections per FR-007 are: Identity, Capability Description, Inventory,
Build Instructions, Ingest Instructions, Verification, Rollback.
"""

from __future__ import annotations

from pathlib import Path

import pytest

TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "003-agentbridge-mvp"
    / "contracts"
    / "briefing.template.md"
)

REQUIRED_SECTIONS = (
    "Identity",
    "Capability Description",
    "Inventory",
    "Build Instructions",
    "Ingest Instructions",
    "Verification",
    "Rollback",
)


def test_template_file_exists():
    assert TEMPLATE_PATH.exists(), f"Missing briefing template at {TEMPLATE_PATH}"


@pytest.mark.parametrize("section", REQUIRED_SECTIONS)
def test_template_contains_section_heading(section):
    text = TEMPLATE_PATH.read_text()
    # Sections are level-2 headings: `## 1. Identity`, `## 2. Capability Description`, etc.
    assert f"## " in text and section in text, (
        f"Template missing required section heading containing '{section}'"
    )


def test_render_function_signature_exists():
    """Stub render() must exist so test_capability_roundtrip can import it.

    Implementation lands in T028 — this just verifies the symbol is present
    and raises NotImplementedError until then.
    """
    from agent_transfer.bridge import briefing

    with pytest.raises(NotImplementedError):
        briefing.render(None)  # type: ignore[arg-type]
