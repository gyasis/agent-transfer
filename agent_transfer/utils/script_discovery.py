"""
Discover and bundle user scripts referenced by Claude Code config.

Many skills, rules, and recipes shell out to user-installed scripts in
`~/bin/` or `~/.local/bin/` (e.g., `session-search`, `prd`, `bb`,
`circleci_monitor.py`). Without these scripts on the destination machine,
the corresponding skills/rules silently break.

This module:
  1. Greps the Claude Code config tree for path references like `~/bin/X`,
     `/home/<user>/bin/X`, `/home/<user>/.local/bin/X`.
  2. Resolves each reference to an actual file.
  3. Returns a manifest of what to bundle into `bin-scripts/<name>` in the
     export tarball, with which config files referenced each script.

Usage:
    from agent_transfer.utils.script_discovery import discover_referenced_scripts
    refs = discover_referenced_scripts()
    for r in refs:
        print(r.script_path, r.referenced_by)
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable


# Default directories where user scripts live and are searched for.
DEFAULT_BIN_DIRS = (
    Path.home() / "bin",
    Path.home() / ".local" / "bin",
)

# Default config roots to grep for references.
DEFAULT_CONFIG_ROOTS = (
    Path.home() / ".claude" / "skills",
    Path.home() / ".claude" / "rules",
    Path.home() / ".claude" / "agents",
    Path.home() / ".claude" / "recipes",
    Path.home() / ".claude" / "commands",
    Path.home() / ".claude" / "CLAUDE.md",
)

# File extensions to scan inside config roots.
SCANNABLE_EXTS = {".md", ".sh", ".py", ".json", ".yaml", ".yml", ".txt"}

# Default size cap (bytes). Scripts larger than this are likely platform binaries
# (snowsql, dbtf, claude itself) that should be installed by the importer via
# their own package manager, not bundled in a Claude Code config tarball.
DEFAULT_MAX_BUNDLE_SIZE = 1_048_576  # 1 MiB

# Always exclude these basenames in lenient mode — runtime managers, language
# binaries, and the harness itself. They produce huge tarballs and don't belong
# in a Claude Code transfer payload (importer manages them via their OS).
ALWAYS_EXCLUDE_BASENAMES = frozenset({
    "claude",          # Claude Code CLI itself
    "agent-transfer",  # this tool itself
    "python", "python3", "pip", "pip3", "uv", "uvx",
    "node", "npm", "npx", "bun", "bunx", "yarn", "pnpm",
    "docker", "podman", "git", "bash", "sh", "zsh",
})

# Common English words / generic basenames that produce too many false positives
# in lenient mode. If a script has one of these basenames, require strict-path
# evidence to bundle it.
GENERIC_BASENAMES = frozenset({
    "agent", "agents", "code", "run", "do", "start", "stop", "test", "build",
    "make", "init", "config", "setup", "install", "update", "upgrade", "tools",
    "specify", "validate", "check", "watch", "list", "show",
})


@dataclass
class ScriptReference:
    script_path: Path                  # absolute path to the resolved script
    basename: str                      # filename only (e.g., "session-search")
    bin_dir: Path                      # which bin dir it lives in
    size_bytes: int
    is_executable: bool
    referenced_by: list[str] = field(default_factory=list)  # config files mentioning it
    reference_count: int = 0
    match_mode: str = "strict"         # "strict" (explicit path) or "lenient" (bare command)
    # AgentBridge MVP (003) — risk tag for the bundle inventory (FR-008).
    # Default yellow; computed by tag_script() per heuristics in research.md.
    risk_tag: str = "yellow"


# Tokens that indicate a script writes state on the destination machine.
# Presence of any of these tokens promotes risk_tag to "red".
_RED_TOKENS = (
    "rm ", "rm\t", "mv ", " > ", " >> ",        # filesystem mutation
    "git push", "git commit",                    # vcs writes
    "chmod ", "chown ", "install ", "make install",
    "curl -X POST", "curl -X PUT", "curl -X DELETE", "curl --request POST",
    "wget ", "pip install", "uv pip install",   # network writes / install
    "kill ", "pkill ",                           # process control
    "sed -i", "perl -pi",                        # in-place edits
    "docker run", "docker build", "docker rm",
    "psql -c", "snowsql -q", "duckdb",           # db state
)

# Tokens for clearly read-only scripts. Promotes yellow→green when present
# AND no _RED_TOKENS are also present.
_GREEN_TOKENS = ("grep", "rg ", "ripgrep", "find ", "ls ", "cat ", "head ", "tail ", "echo ")


def tag_script(script_path: Path) -> str:
    """Return Green/Yellow/Red for one script. Heuristic per FR-008.

    - Reads first 64 KiB (scripts are tiny). Errors → conservative "red".
    - Any RED token present → red.
    - Else, only GREEN tokens (no env, no auth) → green.
    - Otherwise → yellow.
    """
    try:
        with open(script_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read(65536)
    except OSError:
        return "red"
    for tok in _RED_TOKENS:
        if tok in text:
            return "red"
    has_green = any(tok in text for tok in _GREEN_TOKENS)
    has_auth = "AUTH" in text.upper() or "TOKEN" in text.upper() or "API_KEY" in text.upper()
    if has_green and not has_auth:
        return "green"
    return "yellow"


def _build_reference_pattern(home: str) -> re.Pattern[str]:
    """Build a regex matching `~/bin/<name>`, `/home/<user>/bin/<name>`, etc."""
    home_escaped = re.escape(home)
    # Names: alphanumeric + dash + underscore + dot (covers .py / .sh suffixes)
    return re.compile(
        rf"(?:~|{home_escaped})/(?:bin|\.local/bin)/([a-zA-Z0-9_.\-]+)"
    )


SKIP_DIR_PARTS = frozenset({
    ".venv", "venv", "node_modules", "__pycache__", ".git",
    ".pytest_cache", ".ruff_cache", ".mypy_cache", "dist", "build",
})


def _iter_scannable_files(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        if not root.exists():
            continue
        if root.is_file():
            yield root
            continue
        for p in root.rglob("*"):
            if not (p.is_file() and p.suffix in SCANNABLE_EXTS):
                continue
            # Skip files inside dependency / build / cache directories
            if any(part in SKIP_DIR_PARTS for part in p.parts):
                continue
            yield p


def discover_referenced_scripts(
    config_roots: Iterable[Path] = DEFAULT_CONFIG_ROOTS,
    bin_dirs: Iterable[Path] = DEFAULT_BIN_DIRS,
    home: str | None = None,
    include_lenient: bool = True,
) -> list[ScriptReference]:
    """Scan config_roots for references to scripts in bin_dirs. Return matches.

    Two-pass discovery:
      STRICT  — explicit path references (~/bin/X, /home/$USER/bin/X). High confidence.
      LENIENT — bare command references (\\bX\\b) where X is the basename of an
                executable in a bin_dir. Higher recall, may include false positives
                from prose mentions; users review before bundling.

    Only scripts that exist in one of the bin_dirs are returned. Unreferenced
    bin scripts are NOT bundled (avoid over-capture of unrelated tools).
    """
    home = home or os.path.expanduser("~")
    pattern = _build_reference_pattern(home)
    bin_dirs = [Path(b) for b in bin_dirs]

    # Pre-read each scannable file once for both passes
    file_contents: dict[Path, str] = {}
    for cfg_file in _iter_scannable_files(config_roots):
        try:
            file_contents[cfg_file] = cfg_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

    # ---- PASS 1: strict (explicit path references) ----
    strict_refs: dict[str, set[str]] = {}
    for cfg_file, text in file_contents.items():
        for match in pattern.finditer(text):
            strict_refs.setdefault(match.group(1), set()).add(str(cfg_file))

    # ---- PASS 2: lenient (bare command references) ----
    # Enumerate basenames present in any bin_dir, then word-boundary grep.
    bin_basenames: dict[str, Path] = {}  # basename -> resolved bin path
    for bd in bin_dirs:
        if not bd.exists():
            continue
        for child in bd.iterdir():
            if child.is_file() and child.name not in bin_basenames:
                bin_basenames[child.name] = bd

    lenient_refs: dict[str, set[str]] = {}
    if include_lenient:
        # Compile one regex per basename, escape, word-boundary anchors
        for basename in bin_basenames:
            # Skip noise: too short, pure numeric, always-excluded, or generic words
            if len(basename) < 2 or basename.isdigit():
                continue
            if basename in ALWAYS_EXCLUDE_BASENAMES:
                continue
            if basename in GENERIC_BASENAMES:
                # Generic words need strict-path evidence — drop from lenient pass.
                continue
            patt = re.compile(rf"\b{re.escape(basename)}\b")
            for cfg_file, text in file_contents.items():
                if patt.search(text):
                    lenient_refs.setdefault(basename, set()).add(str(cfg_file))

    # ---- Merge: strict wins over lenient on match_mode tag ----
    all_basenames = set(strict_refs) | set(lenient_refs)
    results: list[ScriptReference] = []
    for basename in sorted(all_basenames):
        resolved: Path | None = None
        bin_dir: Path | None = None
        for bd in bin_dirs:
            candidate = bd / basename
            if candidate.is_file():
                resolved = candidate
                bin_dir = bd
                break
        if resolved is None:
            continue
        try:
            stat = resolved.stat()
            size = stat.st_size
            executable = bool(stat.st_mode & 0o111)
        except OSError:
            size = 0
            executable = False

        # Combine refs from both passes; tag mode based on whether strict found it
        merged = strict_refs.get(basename, set()) | lenient_refs.get(basename, set())
        mode = "strict" if basename in strict_refs else "lenient"

        results.append(
            ScriptReference(
                script_path=resolved,
                basename=basename,
                bin_dir=bin_dir,  # type: ignore[arg-type]
                size_bytes=size,
                is_executable=executable,
                referenced_by=sorted(merged),
                reference_count=len(merged),
                match_mode=mode,
                risk_tag=tag_script(resolved),
            )
        )
    return results


def discover_unresolved_references(
    config_roots: Iterable[Path] = DEFAULT_CONFIG_ROOTS,
    bin_dirs: Iterable[Path] = DEFAULT_BIN_DIRS,
    home: str | None = None,
) -> dict[str, list[str]]:
    """Return basenames referenced by config but NOT found in any bin_dir.

    These are the warnings to surface to the user — either the reference is
    stale (script was renamed/removed) or the script is somewhere else and
    we should expand bin_dirs.
    """
    home = home or os.path.expanduser("~")
    pattern = _build_reference_pattern(home)
    bin_dirs = [Path(b) for b in bin_dirs]

    refs_by_basename: dict[str, set[str]] = {}
    for cfg_file in _iter_scannable_files(config_roots):
        try:
            text = cfg_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in pattern.finditer(text):
            refs_by_basename.setdefault(match.group(1), set()).add(str(cfg_file))

    unresolved: dict[str, list[str]] = {}
    for basename, ref_files in refs_by_basename.items():
        if not any((bd / basename).is_file() for bd in bin_dirs):
            unresolved[basename] = sorted(ref_files)
    return unresolved


def bundle_scripts_to(
    scripts: list[ScriptReference],
    dest_dir: Path,
    max_size: int = DEFAULT_MAX_BUNDLE_SIZE,
) -> dict[str, object]:
    """Copy resolved scripts into dest_dir, preserving mode bits.

    Scripts larger than `max_size` are NOT copied — they're recorded in the
    manifest under `oversized` with their install hint left to the importer
    (these are usually platform binaries like snowsql/dbtf installed via OS
    package managers).

    Returns a manifest dict suitable for inclusion in the tarball alongside
    the bin-scripts/ directory.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    bundled: list[dict[str, object]] = []
    oversized: list[dict[str, object]] = []
    for s in scripts:
        entry = asdict(s)
        entry["script_path"] = str(s.script_path)
        entry["bin_dir"] = str(s.bin_dir)
        entry["original_relative_to_home"] = os.path.relpath(
            s.script_path, os.path.expanduser("~")
        )
        if s.size_bytes > max_size:
            entry["skipped_reason"] = (
                f"size {s.size_bytes} > max_size {max_size}; likely platform "
                "binary — importer should install via their package manager"
            )
            oversized.append(entry)
            continue
        target = dest_dir / s.basename
        shutil.copy2(s.script_path, target)
        if s.is_executable:
            os.chmod(target, target.stat().st_mode | 0o111)
        bundled.append(entry)
    return {
        "version": "0.2",
        "bundled_count": len(bundled),
        "oversized_count": len(oversized),
        "max_size_bytes": max_size,
        "scripts": bundled,
        "oversized": oversized,
    }


def _print_report(scripts: list[ScriptReference], unresolved: dict[str, list[str]]) -> None:
    strict = [s for s in scripts if s.match_mode == "strict"]
    lenient = [s for s in scripts if s.match_mode == "lenient"]
    print(
        f"=== Referenced scripts: {len(scripts)} total "
        f"({len(strict)} strict, {len(lenient)} lenient), "
        f"{len(unresolved)} unresolved ==="
    )
    for s in scripts:
        tag = "✓" if s.match_mode == "strict" else "~"
        print(
            f"  {tag} {s.basename:28s}  {s.size_bytes:6d}B  "
            f"refs={s.reference_count}  ({s.bin_dir})"
        )
        for r in s.referenced_by[:3]:
            print(f"    ↳ {r}")
        if len(s.referenced_by) > 3:
            print(f"    ↳ ... +{len(s.referenced_by) - 3} more")
    if unresolved:
        print()
        print("=== UNRESOLVED references (script mentioned but not found in bin dirs) ===")
        for basename, refs in sorted(unresolved.items()):
            print(f"  {basename}  ← {len(refs)} reference(s)")
            for r in refs[:2]:
                print(f"    ↳ {r}")


if __name__ == "__main__":
    refs = discover_referenced_scripts()
    unresolved = discover_unresolved_references()
    # Filter unresolved to exclude already-resolved basenames
    resolved_names = {s.basename for s in refs}
    unresolved = {k: v for k, v in unresolved.items() if k not in resolved_names}
    _print_report(refs, unresolved)
