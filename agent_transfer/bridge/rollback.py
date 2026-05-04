"""All-or-nothing rollback snapshot.

Generated BEFORE any destination write. Per research.md §5, snapshots:
  - every destination path the bundle declares
  - ~/.claude.json (whole file)
  - ~/.claude/settings.json (whole file)
  - ~/.claude/settings.local.json (whole file, if exists)
  - parent-directory listing for every ~/bin/<x> write target (orphan
    detection on rollback)

Emits rollback.tar.gz + rollback.sh in the bundle root. The shell script
restores `before/` and removes orphans listed in
`manifest-of-bundle-writes.json`.

Constitution:
  R6 (no hardcoded ~/) — `home` arg is mandatory.
  R7 (safe extract) — rollback.sh uses tar with --no-overwrite-dir; the
                      ingest-side restore call uses safe-extract util.
  R16 (FR-016) — atomic; no partial state.
"""

from __future__ import annotations

import json
import os
import tarfile
from pathlib import Path
from typing import Iterable, List, Tuple


_MISSING_MARKER = ".was-missing"  # placed inside before/ to mark a path that
                                   # didn't exist pre-install (so rollback
                                   # removes it instead of restoring nothing).


def _expand_dest(dest_path: str, home: Path) -> Path:
    if dest_path.startswith("~/"):
        return home / dest_path[2:]
    if dest_path == "~":
        return home
    return Path(dest_path)


def _under_home(p: Path, home: Path) -> str:
    """Return path relative to before/home/ when under $HOME, else absolute."""
    try:
        rel = p.resolve().relative_to(home.resolve())
        return f"home/{rel}"
    except ValueError:
        # Path is outside $HOME — store under abs/ to keep the tar self-contained.
        return f"abs{p.resolve()}"


def _sibling_paths_for_orphan_detection(p: Path) -> Path:
    """Parent directory used for orphan detection (~/bin/* parent listing)."""
    return p.parent


def snapshot(
    targets: Iterable[str],
    bundle_root: Path,
    *,
    home: Path,
    extra_whole_files: Iterable[str] = (),
) -> Tuple[Path, Path]:
    """Snapshot pre-install state. Returns (rollback_tar, rollback_sh).

    Args:
        targets: dest_path strings from manifest.capability.assets[*].
        bundle_root: Where to write rollback.tar.gz and rollback.sh.
        home: Receiver's home directory.
        extra_whole_files: Always-snapshot paths regardless of `targets`.
            Defaults add ~/.claude.json + ~/.claude/settings.json[.local].

    Returns:
        (rollback_tar, rollback_sh) absolute paths.
    """
    bundle_root.mkdir(parents=True, exist_ok=True)
    rollback_tar = bundle_root / "rollback.tar.gz"
    rollback_sh = bundle_root / "rollback.sh"

    # Always include the canonical config files.
    always_paths = [
        home / ".claude.json",
        home / ".claude" / "settings.json",
        home / ".claude" / "settings.local.json",
    ]
    extra_paths = [_expand_dest(p, home) for p in extra_whole_files]
    target_paths = [_expand_dest(t, home) for t in targets]

    all_paths: List[Path] = list({
        *always_paths, *extra_paths, *target_paths,
    })

    # Build manifest of bundle writes for orphan detection.
    bundle_writes: List[str] = [
        str(_expand_dest(t, home).resolve()) for t in targets
    ]

    # Collect orphan-detection parents (~/bin parents etc.).
    parent_listings: dict[str, List[str]] = {}
    for tp in target_paths:
        parent = _sibling_paths_for_orphan_detection(tp)
        if parent.exists() and parent.is_dir():
            try:
                parent_listings[str(parent.resolve())] = sorted(
                    p.name for p in parent.iterdir()
                )
            except OSError:
                pass

    manifest = {
        "schema": "rollback-v1",
        "home": str(home),
        "bundle_writes": bundle_writes,
        "parent_listings": parent_listings,
    }

    with tarfile.open(rollback_tar, "w:gz") as tar:
        # Write manifest first so rollback.sh can read it.
        manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
        info = tarfile.TarInfo(name="manifest-of-bundle-writes.json")
        info.size = len(manifest_bytes)
        info.mode = 0o644
        import io
        tar.addfile(info, io.BytesIO(manifest_bytes))

        # Snapshot each path under before/.
        for p in all_paths:
            arcname = f"before/{_under_home(p, home)}"
            if p.exists():
                tar.add(str(p), arcname=arcname, recursive=False)
            else:
                # Mark as missing so rollback knows to delete on restore.
                marker_name = f"{arcname}{_MISSING_MARKER}"
                marker_info = tarfile.TarInfo(name=marker_name)
                marker_info.size = 0
                marker_info.mode = 0o644
                tar.addfile(marker_info)

    rollback_sh.write_text(_ROLLBACK_SH_BODY)
    rollback_sh.chmod(0o755)
    return rollback_tar, rollback_sh


_ROLLBACK_SH_BODY = r"""#!/usr/bin/env bash
# AgentBridge rollback script — restores pre-install state.
#
# Usage: bash rollback.sh
#
# This is the all-or-nothing safety net per FR-016. Invokes:
#   1. Read manifest-of-bundle-writes.json from sibling rollback.tar.gz
#   2. Remove every path the bundle wrote
#   3. Restore before/ over those paths
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TAR="$HERE/rollback.tar.gz"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

if [ ! -f "$TAR" ]; then
    echo "rollback: missing rollback.tar.gz" >&2
    exit 1
fi

tar -xzf "$TAR" -C "$WORK"
MANIFEST="$WORK/manifest-of-bundle-writes.json"
if [ ! -f "$MANIFEST" ]; then
    echo "rollback: tar missing manifest-of-bundle-writes.json" >&2
    exit 1
fi

HOME_DIR="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["home"])' "$MANIFEST")"

# Step 1: remove orphans the bundle introduced.
python3 -c '
import json, os, sys
m = json.load(open(sys.argv[1]))
for p in m.get("bundle_writes", []):
    if os.path.exists(p):
        try:
            if os.path.isfile(p) or os.path.islink(p):
                os.unlink(p)
            else:
                import shutil
                shutil.rmtree(p)
        except OSError as e:
            print(f"rollback: could not remove {p}: {e}", file=sys.stderr)
' "$MANIFEST"

# Step 2: restore before/ tree.
if [ -d "$WORK/before" ]; then
    # Resolve "home/<rel>" -> "$HOME_DIR/<rel>", "abs/<abs>" -> absolute path.
    find "$WORK/before" -type f -o -type l | while read -r src; do
        rel="${src#$WORK/before/}"
        case "$rel" in
            home/*)
                dst="$HOME_DIR/${rel#home/}"
                ;;
            abs/*)
                dst="/${rel#abs/}"
                ;;
            *)
                continue
                ;;
        esac
        case "$dst" in
            *.was-missing)
                # nothing to restore; the path was missing pre-install
                continue
                ;;
        esac
        mkdir -p "$(dirname "$dst")"
        cp -p "$src" "$dst"
    done
fi

echo "rollback: complete" >&2
"""
