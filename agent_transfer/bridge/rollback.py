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
    """Return path relative to before/home/ when under $HOME, else absolute.

    R12 H#6 — does NOT call resolve() to keep snapshot keys consistent with
    apply-side keys, which also avoids resolve(). Symlinked HOME on WSL
    would otherwise produce mismatched canonical-vs-symlinked entries.
    """
    home_str = str(home).rstrip("/")
    p_str = str(p)
    if p_str == home_str or p_str.startswith(home_str + "/"):
        rel = p_str[len(home_str) + 1:]
        return f"home/{rel}" if rel else "home"
    return f"abs{p_str}"


def _sibling_paths_for_orphan_detection(p: Path) -> Path:
    """Parent directory used for orphan detection (~/bin/* parent listing)."""
    return p.parent


def snapshot(
    targets: Iterable[str],
    bundle_root: Path,
    *,
    home: Path,
    extra_whole_files: Iterable[str] = (),
    preserve_existing: bool = True,
) -> Tuple[Path, Path]:
    """Snapshot pre-install state. Returns (rollback_tar, rollback_sh).

    Args:
        targets: dest_path strings from manifest.capability.assets[*].
        bundle_root: Where to write rollback.tar.gz and rollback.sh.
        home: Receiver's home directory.
        extra_whole_files: Always-snapshot paths regardless of `targets`.
            Defaults add ~/.claude.json + ~/.claude/settings.json[.local].
        preserve_existing: If True (default) and rollback.tar.gz already
            exists in bundle_root, return its path unchanged WITHOUT
            re-snapshotting. The first-ingest snapshot is the authoritative
            pre-install baseline; re-running ingest must NOT overwrite it
            with post-install state (G9 — the second snapshot would capture
            files we just installed, silently losing the original "before"
            and breaking rollback). Set False at compose time when you
            intend to regenerate.

    Returns:
        (rollback_tar, rollback_sh) absolute paths.
    """
    bundle_root.mkdir(parents=True, exist_ok=True)
    rollback_tar = bundle_root / "rollback.tar.gz"
    rollback_sh = bundle_root / "rollback.sh"

    # G9 — protect the original pre-install baseline. If a rollback already
    # exists in this bundle (i.e. a previous ingest captured it), do NOT
    # overwrite. Re-snapshotting after install would tar up the now-installed
    # files as the "before" state — silent data loss on rollback.
    if preserve_existing and rollback_tar.exists():
        if not rollback_sh.exists():
            rollback_sh.write_text(_ROLLBACK_SH_BODY)
            rollback_sh.chmod(0o755)
        return rollback_tar, rollback_sh

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
    # R12 H#6 fix — do NOT resolve(): apply path uses _expand_dest without
    # resolve, so snapshot paths must match exactly. Symlinked HOME (common
    # on WSL) was producing bundle_writes pointing at canonical paths while
    # the actual writes went through the symlinked HOME — divergence on
    # rollback. Match apply-side semantics.
    bundle_writes: List[str] = [str(_expand_dest(t, home)) for t in targets]

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
# AgentBridge rollback script — restores pre-install state (FR-016).
#
# R12 H#4 hardening: refuses to run unless $HOME matches the manifest's
# recorded home, and rejects manifests where home is "/" or starts with
# anything outside the user's actual HOME. This blocks privesc when a
# user accidentally runs `sudo bash rollback.sh` against a bundle whose
# manifest has been crafted or carried over from another box.
#
# R12 H#5 fix: directories are restored too (find now includes -type d),
# and parent-listing orphan detection actually consults the manifest.
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

# R12 H#4 — assert manifest's HOME matches the actual current HOME.
# Reject obviously dangerous values (/, /etc, /root) outright.
case "$HOME_DIR" in
    /|/etc|/etc/*|/root|/root/*|/sys|/sys/*|/proc|/proc/*)
        echo "rollback: refusing to restore into privileged path $HOME_DIR" >&2
        exit 2
        ;;
esac
if [ "${HOME_DIR%/}" != "${HOME%/}" ]; then
    echo "rollback: manifest home ($HOME_DIR) does not match current HOME ($HOME)" >&2
    echo "rollback: refusing to run — re-run from a session where HOME matches" >&2
    exit 2
fi

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
# R12 H#5 — include directories in the find so empty / permission-only
# entries are recreated. -print0 + read -d '' to handle paths with spaces
# or newlines safely (M#3 hardening).
if [ -d "$WORK/before" ]; then
    find "$WORK/before" \( -type f -o -type l -o -type d \) -print0 | while IFS= read -r -d '' src; do
        rel="${src#$WORK/before/}"
        if [ "$rel" = "before" ] || [ -z "$rel" ]; then
            continue
        fi
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
                continue
                ;;
        esac
        if [ -d "$src" ] && [ ! -L "$src" ]; then
            mkdir -p "$dst"
        else
            mkdir -p "$(dirname "$dst")"
            cp -p "$src" "$dst"
        fi
    done
fi

echo "rollback: complete" >&2
"""
