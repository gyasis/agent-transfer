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
    registry_path_for,
)
from agent_transfer.bridge.models import AssetEntry, Capability, RegistrationRef
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

# v1.1 — frontmatter delimiter at the start of a markdown file. Used by
# _extract_behavior_md to skip YAML frontmatter (skills + rules) before
# pulling the first paragraph as a behavior summary.
_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
_BEHAVIOR_MD_MAX_CHARS = 200

# v1.1 — frontmatter `description:` field extractor. Used by the
# vacuous-description-refusal logic to suggest a real description when
# the user omits --description. Matches `description: <one-line text>`
# OR `description: >`/`|` block scalar (first non-blank line only).
_FRONTMATTER_DESC_RE = re.compile(
    r"^description\s*:\s*(.+?)\s*$", re.MULTILINE,
)

# v1.1 — exit code emitted when compose cannot determine a non-vacuous
# description AND the user did not pass --description "(unset)" to opt
# out. Bundles without a real description are useless to non-Claude
# receivers because they have no other signal for what the capability
# does. PRD §5 Q3.
EXIT_VACUOUS_DESCRIPTION = 7

# v1.1 — sentinel that the user can pass to --description to explicitly
# accept a placeholder. Useful in CI / smoke tests where the bundle is
# discarded immediately.
DESCRIPTION_UNSET_SENTINEL = "(unset)"


# v1.1 — map _Candidate.asset_kind (internal, free-form) to the AssetKind
# Literal that AssetEntry now requires. Keep the internal taxonomy looser
# than the schema so the composer can still describe things like CLAUDE.md
# fragments without losing information; the manifest just records the
# best-fit cross-harness category. claude_md_section → "capability" because
# a CLAUDE.md fragment is a capability-level glue artifact, not file-level.
_KIND_MAP = {
    "skill": "skill",
    "rule": "rule",
    "hook": "hook",
    "bin": "bin",
    "claude_md_section": "capability",
}


def _normalize_kind(internal_kind: str) -> str:
    return _KIND_MAP.get(internal_kind, "skill")


def _extract_frontmatter_description(path: Path) -> Optional[str]:
    """v1.1 — return the YAML `description:` field of a skill/rule, or None.

    Skills frequently carry a one-line description in their frontmatter
    (per the Claude Code skill convention). Used as the SECOND-priority
    fallback when compose() needs a non-vacuous Capability.description.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not fm_match:
        return None
    fm_body = fm_match.group(1)
    desc_match = _FRONTMATTER_DESC_RE.search(fm_body)
    if not desc_match:
        return None
    desc = desc_match.group(1).strip()
    # Strip surrounding quotes if present
    if (desc.startswith('"') and desc.endswith('"')) or (
        desc.startswith("'") and desc.endswith("'")
    ):
        desc = desc[1:-1]
    desc = desc.strip()
    return desc or None


def _resolve_description(
    user_description: Optional[str],
    cores: "List[_Candidate]",
    capability_name: str,
) -> str:
    """v1.1 — produce a non-vacuous description or raise SystemExit(7).

    Priority chain:
      1. user_description (unless it's None) → return as-is
      2. user_description == DESCRIPTION_UNSET_SENTINEL → return placeholder
         (explicit opt-out for CI/tests)
      3. frontmatter `description:` of the first CORE skill
      4. first paragraph (via _extract_behavior_md) of the first CORE skill
      5. SystemExit(EXIT_VACUOUS_DESCRIPTION) with a clear remediation hint

    Why exit instead of returning a placeholder by default: bundles
    without real descriptions are functionally useless to non-Claude
    receivers, who have no other signal for what the capability does.
    Hard refusal at compose time is the only forcing function that gets
    a meaningful description into every shipped bundle.
    """
    import sys as _sys

    if user_description is None:
        pass
    elif user_description == DESCRIPTION_UNSET_SENTINEL:
        return f"(unset — bundle for the {capability_name} capability)"
    else:
        return user_description

    # Try frontmatter (skills/rules only — bins/hooks have no frontmatter).
    for c in cores:
        if c.asset_kind in ("skill", "rule"):
            fm = _extract_frontmatter_description(c.path)
            if fm:
                return fm
    # Then try first-paragraph (skills/rules) or leading comment-block
    # (bins/hooks). For CLI-anchored capabilities like `session-search`,
    # this is the primary source — the bin's header comments often DO
    # describe the tool.
    for c in cores:
        hint = _extract_behavior_md(c.path, _normalize_kind(c.asset_kind))
        if hint:
            return hint

    # Nothing usable — refuse.
    print(
        f"ERROR: compose: cannot determine a description for capability "
        f"{capability_name!r}. None of its CORE assets carry a frontmatter "
        f"`description:` field or a usable first paragraph.\n"
        f"\n"
        f"Fix:\n"
        f"  • Pass --description '<one-sentence what-this-does>'\n"
        f"  • Or add a `description:` field to the frontmatter of the\n"
        f"    primary CORE skill\n"
        f"  • Or pass --description '{DESCRIPTION_UNSET_SENTINEL}' to bypass\n"
        f"    (for CI / smoke tests where the bundle is discarded)\n",
        file=_sys.stderr,
    )
    raise SystemExit(EXIT_VACUOUS_DESCRIPTION)


def _extract_behavior_md(path: Path, kind: str) -> Optional[str]:
    """v1.1 — return a short behavioral hint for the asset, or None.

    Per user-approved defaults (PRD Q2):
      • skill / rule: first non-frontmatter paragraph (~200 chars).
      • hook / bin: leading `#`-comment block after any shebang.
      • other kinds (capability): None — CLAUDE.md fragments wear their
        markers and don't have a tidy summary.

    Never executes --help; this is a static read so it stays safe + fast
    and works inside `compose` even when the script imports fail.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if not text:
        return None

    if kind in ("skill", "rule"):
        stripped = _FRONTMATTER_RE.sub("", text, count=1).lstrip()
        # First paragraph = up to first blank line.
        para = stripped.split("\n\n", 1)[0].strip()
        # Drop leading markdown heading hashes for readability.
        para = re.sub(r"^#+\s*", "", para)
        if not para:
            return None
        if len(para) > _BEHAVIOR_MD_MAX_CHARS:
            para = para[: _BEHAVIOR_MD_MAX_CHARS - 1].rstrip() + "…"
        return para

    if kind in ("hook", "bin"):
        lines = text.splitlines()
        out: List[str] = []
        started = False
        for ln in lines:
            stripped = ln.strip()
            # Skip shebang.
            if not started and stripped.startswith("#!"):
                continue
            # Skip blank lines before comment block starts.
            if not started and not stripped:
                continue
            if stripped.startswith("#"):
                started = True
                cleaned = stripped.lstrip("#").strip()
                if cleaned:
                    out.append(cleaned)
                continue
            if started:
                break
            # First non-comment, non-shebang line and no comment started → no hint.
            break
        if not out:
            return None
        text_out = " ".join(out)
        if len(text_out) > _BEHAVIOR_MD_MAX_CHARS:
            text_out = text_out[: _BEHAVIOR_MD_MAX_CHARS - 1].rstrip() + "…"
        return text_out

    return None


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


# A (F1) — exclusion list for skill-package expansion.
# Without these, `pkg_dir.rglob("*")` would happily pull `.git/` (multi-MiB
# pack files), `.venv/` (hundreds of MiB), `node_modules/` (worse), `.env`
# (secrets!), `__pycache__/` (stale bytecode), `.DS_Store`, etc. into the
# bundle. Skill maintainers shouldn't have to manually .gitignore-style
# every accidentally-committed cache; the bundler skips them by default.
_SKILL_PKG_EXCLUDED_DIRS = frozenset({
    ".git",
    ".venv", "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    "dist", "build",
    ".idea", ".vscode",
})
_SKILL_PKG_EXCLUDED_NAMES = frozenset({
    ".env", ".env.local",  # secrets — .env.example is fine
    ".DS_Store",
    "Thumbs.db",
})
_SKILL_PKG_EXCLUDED_SUFFIXES = frozenset({
    ".pyc", ".pyo",
    ".log",
    ".swp", ".swo",
})
_SKILL_PKG_MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MiB per file


def _is_skill_package_excluded(p: Path, pkg_dir: Path) -> bool:
    """Return True if `p` (a file under `pkg_dir`) should be skipped.

    Excludes by:
      • any ancestor directory name in _SKILL_PKG_EXCLUDED_DIRS
      • exact filename in _SKILL_PKG_EXCLUDED_NAMES
      • file extension in _SKILL_PKG_EXCLUDED_SUFFIXES
      • size > _SKILL_PKG_MAX_FILE_BYTES
    """
    try:
        rel = p.relative_to(pkg_dir)
    except ValueError:
        return True
    if any(part in _SKILL_PKG_EXCLUDED_DIRS for part in rel.parts):
        return True
    if p.name in _SKILL_PKG_EXCLUDED_NAMES:
        return True
    if p.suffix in _SKILL_PKG_EXCLUDED_SUFFIXES:
        return True
    try:
        if p.stat().st_size > _SKILL_PKG_MAX_FILE_BYTES:
            return True
    except OSError:
        return True
    return False


def _expand_skill_package(pkg_dir: Path) -> List[Path]:
    """Return every file inside a skill-package directory, with exclusions.

    G2 — pre-fix `_walk_dir` filtered to .md only, silently dropping
    scripts/, requirements.txt, .css/.html/.js companions inside skill
    packages (e.g. planning-enhanced/, kami/, data-analyzer/). Now we
    pull the whole package tree EXCEPT `.git/`, `.venv/`, `node_modules/`,
    `__pycache__/`, `.env`, files >5 MiB — those are accidental-include
    risks more than legitimate capability assets (A — F1).
    """
    if not pkg_dir.is_dir():
        return []
    return [
        p for p in pkg_dir.rglob("*")
        if p.is_file() and not _is_skill_package_excluded(p, pkg_dir)
    ]


def _anchor_pass(
    capability_name: str,
    claude_dir: Path,
    *,
    anchor_mode: str = "name",
    bin_dirs: Optional[List[Path]] = None,
) -> List[_Candidate]:
    """Return CORE-tier candidates whose name/body matches the capability.

    anchor_mode:
        "name" (default) — match capability synonyms only against the file
            stem. Correct for a capability anchored on a concrete artifact
            (CLI tool, named skill). Prevents the ".body match" explosion
            where any skill that *uses* X gets falsely tagged CORE.
        "body" — match only against the first ~2 KiB of file body. Useful
            for capabilities expressed as concepts where many files
            implement the concept but no file is named for it.
        "both" — legacy behavior: name OR body match. Pre-spec-006
            default. Retained for backward compatibility; use sparingly,
            it produces large CORE sets for common verbs.
    """
    if anchor_mode not in ("name", "body", "both"):
        raise ValueError(
            f"anchor_mode must be 'name', 'body', or 'both'; got {anchor_mode!r}"
        )
    # In name mode, use ONLY the full normalized capability as the synonym
    # — anchor identity must be strict. _split_synonyms produces
    # {'session search', 'session', 'search'} for "session-search", which
    # then matches "session-recall", "specstory-search", etc. as false
    # CORE anchors. Body/both modes keep the looser synonym set so concept
    # bundles ("memory", "session") still discover related artifacts.
    if anchor_mode == "name":
        synonyms = {_norm_name(capability_name)}
    else:
        synonyms = _split_synonyms(capability_name)
    candidates: List[_Candidate] = []
    seen: Set[Path] = set()

    md_files: List[Path] = []
    md_files += _walk_dir(claude_dir / "skills", (".md",))
    md_files += _walk_dir(claude_dir / "rules", (".md",))
    md_files += _walk_dir(claude_dir / "hooks", (".md",))

    for p in md_files:
        norm_name = _norm_name(p.stem)
        # G4 — word-boundary match. _norm_name collapses non-alnum to
        # single spaces; wrapping with leading/trailing spaces gives
        # token equality without regex. Substring match without bounds
        # produced false positives (capability "sio" matched "session",
        # "decision", "mission" — anything containing s-i-o in sequence).
        name_hit = any(f" {s} " in f" {norm_name} " for s in synonyms)
        body_hit = False
        # Read body only when needed — anchor_mode="name" is the hot path
        # for narrow-capability bundles and skipping the read here makes
        # it noticeably faster on large ~/.claude/ trees.
        if anchor_mode in ("body", "both"):
            norm_body = _norm_name(_safe_read_head(p))
            body_hit = any(f" {s} " in f" {norm_body} " for s in synonyms)
        if anchor_mode == "name":
            hit = name_hit
        elif anchor_mode == "body":
            hit = body_hit
        else:  # "both"
            hit = name_hit or body_hit
        # (continued — selection happens after this block)
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

    # ALSO scan ~/bin and ~/.local/bin for executables whose stem matches
    # the capability name. Critical for capabilities anchored on a CLI
    # tool (e.g. "session-search" lives at ~/bin/session-search, NOT in
    # ~/.claude/). Without this, anchor_mode="name" would return zero
    # cores for any bin-anchored capability and raise ValueError.
    if anchor_mode in ("name", "both") and bin_dirs:
        for bd in bin_dirs:
            if not bd.exists():
                continue
            for entry in bd.iterdir():
                if not entry.is_file():
                    continue
                stem_norm = _norm_name(entry.stem or entry.name)
                if any(f" {s} " in f" {stem_norm} " for s in synonyms):
                    if entry not in seen:
                        candidates.append(_Candidate(entry, "CORE", "bin"))
                        seen.add(entry)

    return candidates


def _expand_one_hop(
    seeds: List[_Candidate],
    claude_dir: Path,
    bin_dirs: List[Path],
    capability_name: str = "",
) -> List[_Candidate]:
    """Add 1-hop neighbors as COMPANIONS candidates.

    capability_name (added 2026-05-24): the free-text capability name. Used to
    do directory-name matching against hook dirs — when ~/.claude/hooks/<dir>/
    has <dir> containing the capability stem, all files in that hook dir get
    pulled in as COMPANIONS even if their body text doesn't name-drop a CORE
    seed. Mirrors `_is_skill_package_anchor` for skill packages. Without this,
    `ab compose --capability memory` silently skips ~/.claude/hooks/unified-memory/
    because the bash bodies don't mention memory.md.
    """
    seen_paths: Set[Path] = {c.path for c in seeds}
    new: List[_Candidate] = []
    cap_stem = capability_name.lower().replace("-", "_") if capability_name else ""

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
        # Skill-package SKILL.md indexed by package dir name too.
        for sub in skill_dir.iterdir():
            if sub.is_dir():
                skill_md = sub / "SKILL.md"
                if skill_md.exists():
                    skill_paths_by_slug.setdefault(sub.name.lower(), skill_md)
        for c in seeds:
            head = _safe_read_head(c.path)
            for m in _SLUG_REF_RE.finditer(head):
                slug = m.group(1).lower()
                target = skill_paths_by_slug.get(slug)
                if target and target not in seen_paths:
                    new.append(_Candidate(target, "COMPANIONS", "skill"))
                    seen_paths.add(target)
                    # G (B G2 adjacent) — symmetric package expansion.
                    # Anchor pass expands skill packages; 1-hop slug
                    # references must too, otherwise a companion skill's
                    # scripts/ subdir gets silently dropped.
                    pkg = _is_skill_package_anchor(target, claude_dir)
                    if pkg is not None:
                        for sibling in _expand_skill_package(pkg):
                            if sibling == target or sibling in seen_paths:
                                continue
                            new.append(_Candidate(
                                sibling, "COMPANIONS",
                                _classify_kind(sibling, claude_dir),
                            ))
                            seen_paths.add(sibling)

    # Hooks: pull in either by (a) directory-name match against capability
    # stem OR (b) body text mentions a CORE rule / skill path.
    # Path (a) added 2026-05-24 — hook scripts rarely name-drop the rule files
    # they support, so the body-text-only signal silently skips critical hooks
    # like unified-memory/pre-compact.sh when bundling --capability memory.
    hooks_root = claude_dir / "hooks"
    if hooks_root.exists():
        hook_files = _walk_dir(hooks_root, (".sh", ".py", ".js", ".md"))
        for h in hook_files:
            # Path (a): directory-name match
            if cap_stem:
                try:
                    rel = h.relative_to(hooks_root)
                    if len(rel.parts) > 1:
                        top_dir = rel.parts[0].lower().replace("-", "_")
                        if cap_stem in top_dir or top_dir in cap_stem:
                            if h not in seen_paths:
                                new.append(_Candidate(h, "COMPANIONS", "hook"))
                                seen_paths.add(h)
                            continue
                except ValueError:
                    pass

            # Path (b): body-text match against CORE seeds (.md hooks skip
            # this — body match is meaningless for READMEs).
            if h.suffix == ".md":
                continue
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
    anchor_mode: str = "name",
    behavior_overrides: Optional[Dict[str, str]] = None,
) -> Capability:
    """Compose a Capability bundle from a free-text capability name.

    Args:
        capability_name: e.g. "cascade-memory"
        home: Override $HOME — for tests with a fixture HOME.
        description: One-sentence what-it-does (defaults to a placeholder).
        intent: User's why (defaults to a placeholder).
        anchor_mode: How to match the capability name against discovered
            files in the anchor pass. "name" (default) — file-stem match
            only; correct for capabilities anchored on a concrete artifact
            (CLI tool, named skill). "body" — body-text match only. "both"
            — legacy OR-match (pre-spec-006); produces large CORE sets and
            pulls in upstream consumers as false anchors. See
            _anchor_pass docstring for guidance.

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

    cores = _anchor_pass(
        capability_name, claude_dir,
        anchor_mode=anchor_mode, bin_dirs=bin_dirs,
    )

    # Smart fallback: when anchor_mode="name" finds nothing (capability is
    # conceptual, no concrete artifact stem-matches), automatically widen
    # to "both" so users on legacy capabilities (e.g. "cascade-memory" with
    # no matching file stem) keep working. The fallback emits a stderr
    # WARN so the user knows scope might be wider than expected and can
    # opt-in to a registry file at ~/.claude/capabilities/<name>.yaml for
    # deterministic results.
    if not cores and anchor_mode == "name":
        import sys as _sys
        print(
            f"WARN: anchor-mode=name found no concrete artifact for "
            f"{capability_name!r}; falling back to anchor-mode=both. "
            f"For deterministic scoping, register at "
            f"~/.claude/capabilities/{capability_name}.yaml or pass "
            f"--anchor-mode both explicitly.",
            file=_sys.stderr,
        )
        cores = _anchor_pass(
            capability_name, claude_dir,
            anchor_mode="both", bin_dirs=bin_dirs,
        )

    if not cores:
        raise ValueError(
            f"No assets matched capability name {capability_name!r}. "
            "Try a more concrete name (e.g. 'cascade-memory' instead of 'memory'), "
            f"or register one at ~/.claude/capabilities/{capability_name}.yaml."
        )

    companions = _expand_one_hop(cores, claude_dir, bin_dirs, capability_name)
    contexts: List[_Candidate] = []
    if _MAX_HOPS >= 2:
        contexts = _expand_two_hop(cores, companions, claude_dir, bin_dirs)

    all_candidates = cores + companions + contexts

    paths = [c.path for c in all_candidates]

    # v1.1 — thread the composer's own classification + behavior summary
    # into emit_asset_entries. _normalize_kind maps the internal taxonomy
    # ("claude_md_section" → "capability") to the AssetKind Literal that
    # AssetEntry now requires. behavior_for is sparse — extract only for
    # CORE candidates (cheap, and the COMPANIONS/CONTEXT tiers are noisier
    # signals where the hint is more often than not unhelpful).
    kind_for: Dict[str, str] = {}
    behavior_for: Dict[str, str] = {}
    for c in all_candidates:
        abs_str = str(c.path if c.path.is_absolute() else c.path.absolute())
        mapped_kind = _normalize_kind(c.asset_kind)
        kind_for[abs_str] = mapped_kind
        if c.tier == "CORE":
            hint = _extract_behavior_md(c.path, mapped_kind)
            if hint:
                behavior_for[abs_str] = hint

    # v1.1 — apply user --behavior overrides. Keys are dest_path (the form
    # the user sees in BRIEFING.md), so we resolve them back to absolute
    # paths via the candidate list before merging into behavior_for. Unknown
    # dest_paths are still recorded as a soft-warn rather than a hard error
    # — the user may pre-write overrides for assets that didn't get picked
    # up in this run.
    if behavior_overrides:
        dest_to_abs: Dict[str, str] = {}
        for c in all_candidates:
            abs_str = str(c.path if c.path.is_absolute() else c.path.absolute())
            if abs_str.startswith(str(home) + "/"):
                dest_to_abs[f"~/{abs_str[len(str(home))+1:]}"] = abs_str
            else:
                dest_to_abs[abs_str] = abs_str
        import sys as _sys
        for dest, txt in behavior_overrides.items():
            abs_path = dest_to_abs.get(dest)
            if abs_path is None:
                print(
                    f"WARN: --behavior dest_path {dest!r} not found in this "
                    f"bundle's asset list; override ignored.",
                    file=_sys.stderr,
                )
                continue
            behavior_for[abs_path] = txt

    asset_dicts = emit_asset_entries(
        paths, home=home, kind_for=kind_for, behavior_for=behavior_for,
    )

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

    resolved_description = _resolve_description(description, cores, capability_name)

    return Capability(
        name=capability_name,
        description=resolved_description,
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
    explicitly declared them. C — provenance (path + sha256 of the
    registry YAML at compose time) is stamped onto the Capability so
    the receiver can tell registry-composed bundles from discovery-
    composed ones.
    """
    import hashlib as _hashlib

    paths = expand_asset_paths(reg, home=home)
    asset_dicts = emit_asset_entries(paths, home=home)
    assets: List[AssetEntry] = []
    for d in asset_dicts:
        d["notes"] = "tier=CORE"
        assets.append(AssetEntry(**d))

    # C — record provenance. Use the home-relative form of the registry
    # path so the manifest doesn't leak the source machine's absolute
    # path layout.
    reg_path = registry_path_for(reg.name, home=home)
    yaml_bytes = reg_path.read_bytes()
    yaml_sha = _hashlib.sha256(yaml_bytes).hexdigest()
    reg_path_str = str(reg_path)
    home_str = str(home)
    if reg_path_str.startswith(home_str + "/"):
        reg_path_display = "~" + reg_path_str[len(home_str):]
    else:
        reg_path_display = reg_path_str

    return Capability(
        name=reg.name,
        description=reg.description,
        intent=reg.intent,
        assets=assets,
        dependencies=reg.dependencies,
        smoke_commands=reg.smoke_commands,
        registered_via=RegistrationRef(
            registry_path=reg_path_display,
            yaml_sha256=yaml_sha,
        ),
    )


def tier_of(asset: AssetEntry) -> Tier:
    """Extract the tier marker from AssetEntry.notes; default 'CONTEXT'."""
    if asset.notes and asset.notes.startswith("tier="):
        return asset.notes.split("=", 1)[1].split()[0]
    return "CONTEXT"
