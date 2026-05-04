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


def _anchor_pass(
    capability_name: str,
    claude_dir: Path,
) -> List[_Candidate]:
    """Return CORE-tier candidates whose name/body matches the capability."""
    synonyms = _split_synonyms(capability_name)
    candidates: List[_Candidate] = []

    md_files: List[Path] = []
    md_files += _walk_dir(claude_dir / "skills", (".md",))
    md_files += _walk_dir(claude_dir / "rules", (".md",))
    md_files += _walk_dir(claude_dir / "hooks", (".md",))

    for p in md_files:
        norm_name = _norm_name(p.stem)
        norm_body = _norm_name(_safe_read_head(p))
        hit = any(s in norm_name for s in synonyms) or any(
            f" {s} " in f" {norm_body} " for s in synonyms
        )
        if hit:
            candidates.append(_Candidate(p, "CORE", _classify_kind(p, claude_dir)))

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

    cores = _anchor_pass(capability_name, claude_dir)

    if not cores:
        raise ValueError(
            f"No assets matched capability name {capability_name!r}. "
            "Try a more concrete name (e.g. 'cascade-memory' instead of 'memory'), "
            "or list synonyms in the description."
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


def tier_of(asset: AssetEntry) -> Tier:
    """Extract the tier marker from AssetEntry.notes; default 'CONTEXT'."""
    if asset.notes and asset.notes.startswith("tier="):
        return asset.notes.split("=", 1)[1].split()[0]
    return "CONTEXT"
