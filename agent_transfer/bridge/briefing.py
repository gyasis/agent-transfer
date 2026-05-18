"""Render the 'Dear Receiving Claude' briefing markdown.

Reads the contract template at
specs/003-agentbridge-mvp/contracts/briefing.template.md and substitutes
manifest fields. The template uses `{{...}}` placeholders with optional
`{{#each ...}}{{/each}}` block iteration.

This is a tiny templater, not a full Mustache/Handlebars implementation:
- {{path.to.field}}              — single-value substitution (dot-traversal)
- {{#each list_field}}...{{/each}} — repeats body for each list item with
                                     `{{this}}` and `{{field}}` referring
                                     to item attributes.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, List

from agent_transfer.bridge.models import BriefingSection, ManifestModel


_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "003-agentbridge-mvp"
    / "contracts"
    / "briefing.template.md"
)

_EACH_RE = re.compile(
    r"\{\{#each\s+([a-zA-Z0-9_.]+)\s*\}\}(.*?)\{\{/each\}\}", re.DOTALL
)
_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")


def _traverse(obj: Any, path: str) -> Any:
    """Walk a dotted path through nested dicts/objects/lists."""
    cur = obj
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif hasattr(cur, part):
            cur = getattr(cur, part)
        else:
            return None
    return cur


def _stringify(v: Any) -> str:
    if v is None:
        return ""
    return str(v)


def _render_each(body: str, items: Iterable[Any]) -> str:
    rendered: List[str] = []
    for item in items:
        chunk = body
        # {{this}} is the whole item (used for scalar lists)
        chunk = chunk.replace("{{this}}", _stringify(item))
        # Inner {{field}} references walk the item
        def sub(m: re.Match[str]) -> str:
            field = m.group(1)
            if field == "this":
                return _stringify(item)
            val = _traverse(item, field)
            return _stringify(val)
        chunk = _VAR_RE.sub(sub, chunk)
        rendered.append(chunk)
    return "".join(rendered)


def render(manifest: ManifestModel) -> str:
    """Render BRIEFING.md from a manifest. Implements T028."""
    if manifest is None:
        raise NotImplementedError("manifest is required")
    if not _TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Briefing template missing: {_TEMPLATE_PATH}")

    template = _TEMPLATE_PATH.read_text()
    data = manifest.model_dump(mode="json")

    # Pass 1: {{#each list}}body{{/each}}
    def each_repl(m: re.Match[str]) -> str:
        list_path = m.group(1)
        body = m.group(2)
        items = _traverse(data, list_path)
        if not isinstance(items, (list, tuple)):
            items = []
        return _render_each(body, items)

    out = _EACH_RE.sub(each_repl, template)

    # Pass 2: simple {{var}} (after each-blocks expanded)
    def var_repl(m: re.Match[str]) -> str:
        path = m.group(1)
        if path == "bundle_root":
            return "."  # ingest-time resolved by caller
        val = _traverse(data, path)
        return _stringify(val)

    out = _VAR_RE.sub(var_repl, out)

    # I (C surfacing) — append a Provenance section when the bundle
    # was composed from a registry YAML rather than discovery. Renders
    # the registry path + sha256 so a human receiver can verify the
    # bundle's origin without parsing the manifest JSON.
    reg = manifest.capability.registered_via
    if reg is not None:
        if not out.endswith("\n"):
            out += "\n"
        out += (
            "\n## Provenance\n\n"
            f"This bundle was composed from a registry declaration at "
            f"`{reg.registry_path}` on the source machine.\n\n"
            f"- Registry path: `{reg.registry_path}`\n"
            f"- Registry SHA-256: `{reg.yaml_sha256}`\n\n"
            "Registry-composed bundles produce reproducible asset lists "
            "across machines (G12). To audit, ask the source machine for "
            "the YAML at the path above and verify its sha256 matches.\n"
        )

    return out


def render_sections(manifest: ManifestModel) -> List[BriefingSection]:
    """Convenience: render and split into 7 BriefingSection records.

    Splits on `## N. <Name>` headings. Returns sections in template order.
    """
    text = render(manifest)
    sections: List[BriefingSection] = []
    name_to_id = {
        "Identity": "identity",
        "Capability Description": "capability_description",
        "Inventory": "inventory",
        "Build Instructions": "build_instructions",
        "Ingest Instructions": "ingest_instructions",
        "Verification": "verification",
        "Rollback": "rollback",
        # v1.1 — cross-harness risk mapping appendix.
        "Risk Mapping": "risk_mapping",
    }
    parts = re.split(r"^## \d+\.\s+(.+)$", text, flags=re.MULTILINE)
    # parts: [pre, name1, body1, name2, body2, ...]
    for i in range(1, len(parts) - 1, 2):
        name = parts[i].strip()
        body = parts[i + 1]
        sec_id = name_to_id.get(name)
        if sec_id is None:
            continue
        sections.append(BriefingSection(name=sec_id, content_md=body.strip()))  # type: ignore[arg-type]
    return sections
