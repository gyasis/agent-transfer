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

import os as _os
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


def _is_under_home(path_abs: Path, home_abs: Path) -> bool:
    """Case-aware containment check (M — Hunter A N7).

    `Path.relative_to` is byte-exact. On case-insensitive filesystems
    (macOS APFS by default, Windows NTFS, WSL DrvFs) `/Users/U/x` and
    `/users/u/x` refer to the same file but compare unequal. Without
    this helper, registry assets get false-rejected on every Mac and
    every Windows + WSL setup.

    Strategy: try `relative_to` first (cheap, exact). If that fails,
    re-check using `os.path.normcase` (which is a no-op on case-
    sensitive filesystems but lower-cases on macOS/Windows).
    """
    try:
        path_abs.relative_to(home_abs)
        return True
    except ValueError:
        pass
    # Fallback: case-folded prefix check.
    p = _os.path.normcase(str(path_abs))
    h = _os.path.normcase(str(home_abs)).rstrip(_os.sep)
    return p == h or p.startswith(h + _os.sep)


def _validate_asset_path(raw: str, resolved: Path, home: Path) -> None:
    """Reject paths outside $HOME, symlinks, and traversal escapes (B — F2).

    Registry YAML files at ~/.claude/capabilities/ are writable by any
    local process. Without these guards, a registration could declare
    `/etc/shadow` or `~/../etc/passwd` and AgentBridge would dutifully
    bundle it. The MVP threat model assumes the user owns the source
    machine, but a stricter contract (capability bundles distributable
    across users) requires hard rejection at the trust boundary.

    Rules:
      1. Resolved path MUST be inside $HOME (or be $HOME itself).
         Case-insensitive on macOS APFS / Windows NTFS / WSL DrvFs.
      2. Resolved path MUST NOT be a symlink and MUST NOT traverse one.
         Anywhere along the path that's a symlink → reject.
      3. Raw entry MUST NOT contain `..` segments.
    """
    # 3. Reject `..` in the raw spec — the user shouldn't be writing
    # traversals into the registry, even harmless ones.
    if ".." in raw.split("/"):
        raise RegistryError(
            f"Registered asset path may not contain '..': {raw!r}"
        )

    # 2. Reject symlinks anywhere on the path. We walk the chain and
    # check is_symlink() at every component that exists. resolve()
    # would silently follow them.
    parent = resolved
    while True:
        if parent.is_symlink():
            raise RegistryError(
                f"Registered asset {raw!r} resolves through a symlink "
                f"at {parent} — refusing to follow (B — F2 trust boundary)."
            )
        if parent.parent == parent:
            break
        parent = parent.parent

    # 1. Must be inside $HOME. Case-aware (M).
    abs_resolved = resolved if resolved.is_absolute() else resolved.absolute()
    home_abs = home if home.is_absolute() else home.absolute()
    if not _is_under_home(abs_resolved, home_abs):
        raise RegistryError(
            f"Registered asset {raw!r} (-> {abs_resolved}) is outside "
            f"$HOME ({home_abs}). Registry assets must live under $HOME "
            "to keep capability bundles user-scoped."
        )


def expand_asset_paths(reg: CapabilityRegistration, *, home: Path) -> List[Path]:
    """Resolve `~/`-relative asset paths and recurse into directories.

    Each entry in `reg.assets` may be:
      • A single file path (kept as-is).
      • A directory path (every file under it is included).
      • A path containing `~` (expanded via `home`).

    Missing paths raise RegistryError — registries must be authoritative.
    Paths that escape $HOME, traverse symlinks, or contain `..` are
    rejected (B — F2 trust boundary).
    """
    out: List[Path] = []
    for raw in reg.assets:
        if raw.startswith("~/"):
            p = home / raw[2:]
        elif raw == "~":
            p = home
        else:
            p = Path(raw)

        _validate_asset_path(raw, p, home)

        if not p.exists():
            raise RegistryError(
                f"Registered asset does not exist on this machine: {raw!r} "
                f"(resolved to {p}). Either install it before composing, "
                "or remove it from the registry."
            )
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            # Per B — F2: every recursed sub-path must also pass the
            # symlink + $HOME check, since rglob can yield symlinked
            # children that point outside $HOME.
            for sub in p.rglob("*"):
                if not sub.is_file():
                    continue
                if sub.is_symlink():
                    raise RegistryError(
                        f"Registered dir {raw!r} contains symlink at {sub} "
                        "— refusing to follow."
                    )
                if not _is_under_home(sub.absolute(), home.absolute()):
                    raise RegistryError(
                        f"Registered dir {raw!r} contains path outside $HOME: "
                        f"{sub}"
                    )
                out.append(sub)
        else:
            raise RegistryError(f"Asset is neither file nor dir: {p}")
    return out
