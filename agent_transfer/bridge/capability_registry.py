"""G12 — capability registry.

Pre-fix bug: `ab compose --capability X` was a free-text command that ran
discovery against whatever ~/.claude/ files happened to be on the source
machine. Two machines with the same capability name produced DIFFERENT
bundles based on local file contents. There was no way for a user to
say "this is what the SIO capability is" with reproducible identity.

Post-fix: a capability can be REGISTERED at
    ~/.claude/capabilities/<name>.yaml
which declares the canonical asset list. When that file exists, compose()
uses it directly (skipping discovery); otherwise falls back to the
existing anchor + BFS discovery.

Schema:
    name: sio                          # required, must match filename stem
    description: Session Intelligence  # required, one-sentence
    intent: Mine errors, gen rules     # required, why-it-exists
    assets:                            # required, list of paths (~/ ok)
      - ~/.claude/skills/sio-scan/
      - ~/.claude/rules/tools/sio.md
    dependencies: []                   # optional, OS binaries on PATH
    smoke_commands:                    # optional, see G6
      - sio --version
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator


REGISTRY_DIR_NAME = "capabilities"


class CapabilityRegistration(BaseModel):
    """Parsed contents of a ~/.claude/capabilities/<name>.yaml file."""

    name: str
    description: str
    intent: str
    assets: List[str] = Field(..., min_length=1)
    dependencies: List[str] = Field(default_factory=list)
    smoke_commands: List[str] = Field(default_factory=list)

    @field_validator("assets")
    @classmethod
    def _no_blank_assets(cls, v: List[str]) -> List[str]:
        if any(not str(a).strip() for a in v):
            raise ValueError("assets list contains a blank entry")
        return v


class RegistryError(RuntimeError):
    """Raised when a capability registry file is malformed or unreadable."""


def registry_path_for(name: str, *, home: Path) -> Path:
    """Return the canonical YAML path for a registered capability name."""
    return home / ".claude" / REGISTRY_DIR_NAME / f"{name}.yaml"


def load_registered(name: str, *, home: Path) -> Optional[CapabilityRegistration]:
    """Return the registration if `name` has one; else None.

    Raises RegistryError if the file exists but is malformed (we want a
    clear error, not a silent fall-through to discovery — that's how the
    "two machines, two different bundles" bug got introduced).
    """
    p = registry_path_for(name, home=home)
    if not p.exists():
        return None
    try:
        raw = yaml.safe_load(p.read_text()) or {}
    except yaml.YAMLError as e:
        raise RegistryError(f"Malformed YAML in {p}: {e}") from e
    if not isinstance(raw, dict):
        raise RegistryError(f"{p} must be a YAML mapping at the top level")
    if raw.get("name") not in (None, name):
        raise RegistryError(
            f"{p} declares name={raw.get('name')!r} but filename stem is {name!r}"
        )
    raw["name"] = name
    try:
        return CapabilityRegistration(**raw)
    except ValidationError as e:
        raise RegistryError(f"Invalid registration in {p}: {e}") from e


def expand_asset_paths(reg: CapabilityRegistration, *, home: Path) -> List[Path]:
    """Resolve `~/`-relative asset paths and recurse into directories.

    Each entry in `reg.assets` may be:
      • A single file path (kept as-is).
      • A directory path (every file under it is included).
      • A path containing `~` (expanded via `home`).

    Missing paths raise RegistryError — registries must be authoritative.
    """
    out: List[Path] = []
    for raw in reg.assets:
        if raw.startswith("~/"):
            p = home / raw[2:]
        elif raw == "~":
            p = home
        else:
            p = Path(raw)

        if not p.exists():
            raise RegistryError(
                f"Registered asset does not exist on this machine: {raw!r} "
                f"(resolved to {p}). Either install it before composing, "
                "or remove it from the registry."
            )
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            out.extend(sub for sub in p.rglob("*") if sub.is_file())
        else:
            raise RegistryError(f"Asset is neither file nor dir: {p}")
    return out
