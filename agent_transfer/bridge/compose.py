"""Capability composition — `ab compose --capability <name>`.

Walks ~/.claude/ to enumerate skills/hooks/rules and ~/bin/* scripts
that compose a named capability. Algorithm per research.md §1:

1. Anchor pass — case-insensitive name match across filenames, frontmatter,
   first 2 KiB of file body.
2. Cross-reference expansion — depth-bounded BFS (max 2 hops) following
   skill→skill, skill→bin, hook→rule, rule→skill references.
3. Tier assignment — anchored = CORE, 1-hop = COMPANIONS, 2-hop = CONTEXT.

The deterministic output is a Capability with assets pre-tiered. The
caller (CLI in T031) hands this to selection_matrix.present() for user
trim, then to the bundler.

Constitution: R6 (no hardcoded absolute paths — caller passes home).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from agent_transfer.bridge.capability_registry import (
    CapabilityRegistration,
    expand_asset_paths,
    load_registered,
)
from agent_transfer.bridge.models import AssetEntry, Capability
from agent_transfer.utils.config_manager import emit_asset_entries
from agent_transfer.utils.script_discovery import (
    DEFAULT_BIN_DIRS,
    discover_referenced_scripts,
)

# Tier label for each candidate asset before user trim.
Tier = str  # "CORE" | "COMPANIONS" | "CONTEXT"

# Bytes read from each candidate file for the anchor pass. Spec says "first
# 2 KiB" — captures frontmatter + section headers without paying full read.
_ANCHOR_READ_BYTES = 2048

# Max BFS hops from anchored seeds.
_MAX_HOPS = 2

_SLUG_REF_RE = re.compile(r"/([a-z][a-z0-9_\-]+)\b")


@dataclass
class _Candidate:
    """One file under consideration during composition."""

    path: Path
    tier: Tier
    asset_kind: str  # "skill" | "hook" | "rule" | "bin" | "claude_md_section"


def _norm_name(s: str) -> str:
    """Lowercase + non-alnum→space for fuzzy matching."""
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _split_synonyms(capability_name: str) -> Set[str]:
    """Build a small synonym set for the anchor pass."""
    base = _norm_name(capability_name)
    parts = base.split()
    out = {base, *parts}
    out.update(p.strip("-") for p in parts)
    return {s for s in out if len(s) >= 3}


def _safe_read_head(p: Path) -> str:
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            return f.read(_ANCHOR_READ_BYTES)
    except OSError:
        return ""


def _walk_dir(root: Path, suffixes: Tuple[str, ...]) -> List[Path]:
    if not root.exists():
        return []
    out: List[Path] = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in suffixes:
            out.append(p)
    return out


def _classify_kind(p: Path, claude_dir: Path) -> str:
    rel = p.resolve()
    rel_str = str(rel)
    if "/skills/" in rel_str or rel_str.startswith(str(claude_dir / "skills")):
        return "skill"
    if "/hooks/" in rel_str:
        return "hook"
    if "/rules/" in rel_str:
        return "rule"
    if rel.name == "CLAUDE.md":
        return "claude_md_section"
    return "skill"  # default — unknown markdown under .claude/ treated as skill-like


def _is_skill_package_anchor(p: Path, claude_dir: Path) -> Optional[Path]:
    """Return the package directory if `p` is a SKILL.md inside one.

    A "skill package" is a directory under ~/.claude/skills/ whose
    SKILL.md is the entry point and whose siblings (scripts/, *.css,
    requirements.txt, etc.) belong to the same shipping unit. Detected
    when `p.name == "SKILL.md"` and the parent dir lives directly under
    skills/ or learned/.
    """
    if p.name != "SKILL.md":
        return None
    skills_root = claude_dir / "skills"
    try:
        rel = p.parent.relative_to(skills_root)
    except ValueError:
        return None
    # parent is either <slug>/ (depth 1) or <subdir>/<slug>/ (depth 2 e.g. learned/foo/)
    parts = rel.parts
    if 1 <= len(parts) <= 2:
        return p.parent
    return None


def _expand_skill_package(pkg_dir: Path) -> List[Path]:
    """Return every file inside a skill-package directory.

    G2 — pre-fix `_walk_dir` filtered to .md only, silently dropping
    scripts/, requirements.txt, .css/.html/.js companions inside skill
    packages (e.g. planning-enhanced/, kami/, data-analyzer/). Now we
    pull the whole package tree.
    """
    if not pkg_dir.is_dir():
        return []
    return [p for p in pkg_dir.rglob("*") if p.is_file()]


def _anchor_pass(
    capability_name: str,
    claude_dir: Path,
) -> List[_Candidate]:
    """Return CORE-tier candidates whose name/body matches the capability."""
    synonyms = _split_synonyms(capability_name)
    candidates: List[_Candidate] = []
    seen: Set[Path] = set()

    md_files: List[Path] = []
    md_files += _walk_dir(claude_dir / "skills", (".md",))
    md_files += _walk_dir(claude_dir / "rules", (".md",))
    md_files += _walk_dir(claude_dir / "hooks", (".md",))

    for p in md_files:
        norm_name = _norm_name(p.stem)
        norm_body = _norm_name(_safe_read_head(p))
        # G4 — word-boundary match on BOTH name and body. Substring match
        # on name produced absurd false positives (capability "sio" matched
        # "session", "decision", "mission" — every word containing s-i-o
        # in sequence). _norm_name already collapses non-alnum to single
        # spaces, so wrapping with leading/trailing spaces gives token
        # equality without regex.
        hit = any(f" {s} " in f" {norm_name} " for s in synonyms) or any(
            f" {s} " in f" {norm_body} " for s in synonyms
        )
        # Special case: skill-package SKILL.md — match against package
        # slug too, since the SKILL.md filename itself is generic.
        if not hit:
            pkg = _is_skill_package_anchor(p, claude_dir)
            if pkg is not None:
                slug_norm = _norm_name(pkg.name)
                hit = any(f" {s} " in f" {slug_norm} " for s in synonyms)
        if hit:
            if p in seen:
                continue
            candidates.append(_Candidate(p, "CORE", _classify_kind(p, claude_dir)))
            seen.add(p)
            # G2 — expand skill-package directories to include sibling
            # files (scripts/, assets, requirements.txt, ...).
            pkg = _is_skill_package_anchor(p, claude_dir)
            if pkg is not None:
                for sibling in _expand_skill_package(pkg):
                    if sibling == p or sibling in seen:
                        continue
                    candidates.append(
                        _Candidate(sibling, "CORE", _classify_kind(sibling, claude_dir))
                    )
                    seen.add(sibling)

    return candidates


def _expand_one_hop(
    seeds: List[_Candidate],
    claude_dir: Path,
    bin_dirs: List[Path],
) -> List[_Candidate]:
    """Add 1-hop neighbors as COMPANIONS candidates."""
    seen_paths: Set[Path] = {c.path for c in seeds}
    new: List[_Candidate] = []

    # Discover ~/bin scripts referenced by ANY seed file (strict-mode only
    # at this hop — bare-word lenient matches are pushed to CONTEXT later).
    seed_paths = [c.path for c in seeds]
    home_str = str(claude_dir.parent)
    refs = discover_referenced_scripts(
        config_roots=seed_paths,
        bin_dirs=bin_dirs,
        home=home_str,
        include_lenient=False,
    )
    for r in refs:
        if r.script_path not in seen_paths:
            new.append(_Candidate(r.script_path, "COMPANIONS", "bin"))
            seen_paths.add(r.script_path)

    # Skills that reference each other by `/<slug>`.
    skill_dir = claude_dir / "skills"
    if skill_dir.exists():
        skill_paths_by_slug: Dict[str, Path] = {}
        for sp in _walk_dir(skill_dir, (".md",)):
            skill_paths_by_slug[sp.stem.lower()] = sp
        for c in seeds:
            head = _safe_read_head(c.path)
            for m in _SLUG_REF_RE.finditer(head):
                slug = m.group(1).lower()
                target = skill_paths_by_slug.get(slug)
                if target and target not in seen_paths:
                    new.append(_Candidate(target, "COMPANIONS", "skill"))
                    seen_paths.add(target)

    # Hooks that mention a CORE rule / skill path → pull in the hook.
    hooks_root = claude_dir / "hooks"
    if hooks_root.exists():
        hook_files = _walk_dir(hooks_root, (".sh", ".py", ".js"))
        for h in hook_files:
            text = _safe_read_head(h)
            for c in seeds:
                if c.path.name in text:
                    if h not in seen_paths:
                        new.append(_Candidate(h, "COMPANIONS", "hook"))
                        seen_paths.add(h)
                    break

    return new


def _expand_two_hop(
    cores: List[_Candidate],
    companions: List[_Candidate],
    claude_dir: Path,
    bin_dirs: List[Path],
) -> List[_Candidate]:
    """Add 2-hop neighbors as CONTEXT candidates (lenient matches)."""
    seen_paths: Set[Path] = {c.path for c in cores + companions}
    new: List[_Candidate] = []

    seed_paths = [c.path for c in cores + companions]
    home_str = str(claude_dir.parent)
    refs = discover_referenced_scripts(
        config_roots=seed_paths,
        bin_dirs=bin_dirs,
        home=home_str,
        include_lenient=True,
    )
    for r in refs:
        if r.script_path not in seen_paths and r.match_mode == "lenient":
            new.append(_Candidate(r.script_path, "CONTEXT", "bin"))
            seen_paths.add(r.script_path)

    return new


def compose(
    capability_name: str,
    *,
    home: Optional[Path] = None,
    description: Optional[str] = None,
    intent: Optional[str] = None,
) -> Capability:
    """Compose a Capability bundle from a free-text capability name.

    Args:
        capability_name: e.g. "cascade-memory"
        home: Override $HOME — for tests with a fixture HOME.
        description: One-sentence what-it-does (defaults to a placeholder).
        intent: User's why (defaults to a placeholder).

    Returns:
        Capability with `assets` pre-tiered. Tier is encoded in
        AssetEntry.notes as a `tier=CORE|COMPANIONS|CONTEXT` prefix so the
        selection_matrix can group rendering. CORE assets are non-removable
        downstream.
    """
    home = home or Path.home()
    claude_dir = home / ".claude"
    bin_dirs = [Path(str(b).replace(str(Path.home()), str(home))) for b in DEFAULT_BIN_DIRS]

    # G12 — registry path takes precedence over discovery. When the user
    # has declared the capability explicitly at
    # ~/.claude/capabilities/<name>.yaml, use that authoritative list so
    # composing the same capability on two machines produces the same
    # set of assets (modulo the actual files existing).
    registration = load_registered(capability_name, home=home)
    if registration is not None:
        return _compose_from_registration(registration, home=home)

    cores = _anchor_pass(capability_name, claude_dir)

    if not cores:
        raise ValueError(
            f"No assets matched capability name {capability_name!r}. "
            "Try a more concrete name (e.g. 'cascade-memory' instead of 'memory'), "
            f"or register one at ~/.claude/capabilities/{capability_name}.yaml."
        )

    companions = _expand_one_hop(cores, claude_dir, bin_dirs)
    contexts: List[_Candidate] = []
    if _MAX_HOPS >= 2:
        contexts = _expand_two_hop(cores, companions, claude_dir, bin_dirs)

    all_candidates = cores + companions + contexts

    paths = [c.path for c in all_candidates]
    asset_dicts = emit_asset_entries(paths, home=home)

    # Decorate notes with tier so selection_matrix can group.
    tier_for: Dict[str, str] = {str(c.path.resolve()): c.tier for c in all_candidates}
    assets: List[AssetEntry] = []
    for d in asset_dicts:
        # Resolve the original path back from dest_path → home + path
        if d["dest_path"].startswith("~/"):
            full = (home / d["dest_path"][2:]).resolve()
        else:
            full = Path(d["dest_path"]).resolve()
        tier = tier_for.get(str(full), "CONTEXT")
        d["notes"] = f"tier={tier}"
        assets.append(AssetEntry(**d))

    return Capability(
        name=capability_name,
        description=description or f"Bundle for the {capability_name} capability.",
        intent=intent or "User-defined capability bundle generated by ab compose.",
        assets=assets,
        dependencies=[],
    )


def _compose_from_registration(
    reg: CapabilityRegistration,
    *,
    home: Path,
) -> Capability:
    """G12 — build a Capability from an explicit registry file.

    Skips the anchor + BFS discovery; the registration's `assets` list
    is authoritative. All assets are tagged tier=CORE because the user
    explicitly declared them.
    """
    paths = expand_asset_paths(reg, home=home)
    asset_dicts = emit_asset_entries(paths, home=home)
    assets: List[AssetEntry] = []
    for d in asset_dicts:
        d["notes"] = "tier=CORE"
        assets.append(AssetEntry(**d))

    return Capability(
        name=reg.name,
        description=reg.description,
        intent=reg.intent,
        assets=assets,
        dependencies=reg.dependencies,
        smoke_commands=reg.smoke_commands,
    )


def tier_of(asset: AssetEntry) -> Tier:
    """Extract the tier marker from AssetEntry.notes; default 'CONTEXT'."""
    if asset.notes and asset.notes.startswith("tier="):
        return asset.notes.split("=", 1)[1].split()[0]
    return "CONTEXT"
