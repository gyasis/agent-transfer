"""
Bundle local MCP server source repos into the export tarball.

Many MCP servers are not installed from a registry — they live as local repos
(e.g., ~/dev/gemini-mcp/, ~/dev/tableau-mcp/) that the config invokes via
absolute paths. Without bundling that source, the destination machine can't
run the server.

This module:
  1. Reads classification results from mcp_classifier
  2. For each server with capture_strategy == "bundle-source", finds its source dir
  3. Tars each source repo into `mcp-sources/<name>.tar.gz`, skipping dependency
     dirs (.venv, node_modules, __pycache__, .git)
  4. Records bundled / skipped / oversized in a manifest

Sister-module to script_discovery — same shape, but at repo level.
"""

from __future__ import annotations

import os
import tarfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


# Same dirs we skipped in script_discovery — never bundle build/cache artifacts.
TAR_EXCLUDE_DIR_PARTS = frozenset({
    ".venv", "venv", "node_modules", "__pycache__", ".git",
    ".pytest_cache", ".ruff_cache", ".mypy_cache", "dist", "build",
    ".tox", ".eggs", "*.egg-info",
})

TAR_EXCLUDE_FILE_SUFFIXES = frozenset({".pyc", ".pyo", ".log"})

# Source bundles larger than this are flagged but still bundled (with warning).
# Repos this big usually have something checked in that shouldn't be (db dumps,
# model weights). User reviews the warning and decides.
SOFT_SIZE_WARN = 50 * 1024 * 1024   # 50 MiB

# Source bundles larger than this are SKIPPED with manifest-only entry.
# At this size, the partner is better off cloning fresh from a git remote.
HARD_SIZE_LIMIT = 500 * 1024 * 1024  # 500 MiB


@dataclass
class BundledSource:
    name: str                          # MCP server name
    server_class: str                  # local-uv | local-python | local-node
    source_dir: str                    # absolute path on source machine
    bundle_relpath: str                # path inside tarball (mcp-sources/<name>.tar.gz)
    bundle_size_bytes: int             # size of the .tar.gz
    file_count: int                    # files included
    warnings: list[str] = field(default_factory=list)
    git_remote: str | None = None      # if source dir is a git repo
    # v0.2.0 — runtime version captured from the source dir at bundle time.
    # Used by `agent-transfer init` to validate the destination has a
    # compatible interpreter BEFORE running install_steps. See
    # _detect_runtime_version().
    python_version: str | None = None
    node_engines: str | None = None


@dataclass
class SkippedSource:
    name: str
    server_class: str
    source_dir: str
    reason: str
    estimated_size_bytes: int = 0


def _extract_source_dir(server_name: str, classification: dict[str, Any]) -> Path | None:
    """Find the source directory for a local-* class server.

    For local-uv:    `--directory <path>` in args
    For local-python: dirname of the .py script in args
    For local-node:   dirname of the .js script in args
    """
    cls = classification.get("server_class")
    args = classification.get("args") or []

    if cls == "local-uv":
        try:
            idx = args.index("--directory")
            return Path(args[idx + 1]).expanduser().resolve()
        except (ValueError, IndexError):
            return None

    if cls in {"local-python", "local-node"}:
        # First arg that looks like a path-with-suffix
        for a in args:
            if not isinstance(a, str):
                continue
            if a.endswith((".py", ".js", ".mjs")) or "/" in a:
                p = Path(a).expanduser().resolve()
                if p.is_file():
                    return p.parent
                if p.is_dir():
                    return p
        return None

    return None


def _detect_runtime_version(
    source_dir: Path, server_class: str
) -> tuple[str | None, str | None]:
    """v0.2.0 — read python/node version requirements from a source dir.

    Returns (python_version, node_engines) as strings, both optional.
    Precedence for python:
        1. `.python-version` file (uv / pyenv standard)
        2. `pyproject.toml` [project.requires-python]
        3. `pyproject.toml` [tool.poetry.dependencies.python]
    Precedence for node:
        1. `package.json` engines.node
        2. `.nvmrc` file

    Best-effort and read-only. Failures return None for that runtime.
    `agent-transfer init` consumes these to validate the target before
    running install_steps; mismatches abort with a clear hint instead
    of silently failing on `uv sync` / `npm install`.
    """
    py_ver: str | None = None
    node_ver: str | None = None

    if server_class in ("local-uv", "local-python"):
        py_file = source_dir / ".python-version"
        if py_file.is_file():
            try:
                txt = py_file.read_text(encoding="utf-8").strip().splitlines()
                if txt:
                    py_ver = txt[0].strip()
            except OSError:
                pass
        if py_ver is None:
            ppy = source_dir / "pyproject.toml"
            if ppy.is_file():
                try:
                    import tomllib  # py3.11+
                except ImportError:
                    tomllib = None  # type: ignore[assignment]
                if tomllib is not None:
                    try:
                        with open(ppy, "rb") as f:
                            data = tomllib.load(f)
                        proj = data.get("project") or {}
                        rp = proj.get("requires-python")
                        if isinstance(rp, str):
                            py_ver = rp.strip()
                        if py_ver is None:
                            tool = (data.get("tool") or {}).get("poetry") or {}
                            deps = tool.get("dependencies") or {}
                            poetry_py = deps.get("python")
                            if isinstance(poetry_py, str):
                                py_ver = poetry_py.strip()
                    except Exception:
                        pass

    if server_class == "local-node":
        pkg = source_dir / "package.json"
        if pkg.is_file():
            try:
                import json as _json
                with open(pkg) as f:
                    data = _json.load(f)
                engines = data.get("engines") or {}
                ne = engines.get("node")
                if isinstance(ne, str):
                    node_ver = ne.strip()
            except Exception:
                pass
        if node_ver is None:
            nvmrc = source_dir / ".nvmrc"
            if nvmrc.is_file():
                try:
                    txt = nvmrc.read_text(encoding="utf-8").strip().splitlines()
                    if txt:
                        node_ver = txt[0].strip()
                except OSError:
                    pass

    return py_ver, node_ver


def _redact_git_url(url: str) -> str:
    """Strip embedded credentials from a git remote URL.

    Bitbucket / GitHub HTTPS URLs sometimes include `https://user:token@host/...`.
    Shipping these in a manifest leaks the token. We redact to `https://<REDACTED>@host/...`.
    SSH URLs (git@host:path) are returned unchanged — no embedded secret.
    """
    import re
    # https://USER:TOKEN@host/...  → https://<REDACTED>@host/...
    return re.sub(
        r"(https?://)([^@/\s]+:[^@/\s]+)@",
        r"\1<REDACTED>@",
        url,
    )


def _git_remote_for(source_dir: Path) -> str | None:
    """Best-effort git remote URL detection, with embedded-secret redaction."""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "-C", str(source_dir), "config", "--get", "remote.origin.url"],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            return _redact_git_url(url) if url else None
    except Exception:
        pass
    return None


def _tar_filter(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo | None:
    """Exclude dependency / build / cache artifacts from the tarball."""
    name = tarinfo.name
    parts = Path(name).parts
    if any(part in TAR_EXCLUDE_DIR_PARTS for part in parts):
        return None
    if any(name.endswith(suf) for suf in TAR_EXCLUDE_FILE_SUFFIXES):
        return None
    if any(part.endswith(".egg-info") for part in parts):
        return None
    return tarinfo


def _estimate_dir_size(d: Path, exclude_parts: frozenset[str]) -> int:
    total = 0
    try:
        for p in d.rglob("*"):
            if not p.is_file():
                continue
            if any(part in exclude_parts for part in p.relative_to(d).parts):
                continue
            try:
                total += p.stat().st_size
            except OSError:
                pass
    except OSError:
        pass
    return total


def bundle_mcp_sources(
    classifications: dict[str, dict[str, Any]],
    dest_dir: Path,
    soft_warn_bytes: int = SOFT_SIZE_WARN,
    hard_limit_bytes: int = HARD_SIZE_LIMIT,
) -> dict[str, Any]:
    """Tar each local MCP server's source repo into dest_dir/<name>.tar.gz.

    Args:
        classifications: dict from `_classification.servers` (name -> entry)
        dest_dir: where to write the .tar.gz files (typically temp_path/mcp-sources)
        soft_warn_bytes: warn if source exceeds this (still bundle)
        hard_limit_bytes: skip if source exceeds this (record git_remote instead)

    Returns:
        Manifest dict listing bundled, skipped, and unresolved source dirs.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    bundled: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for name, cls_entry in classifications.items():
        if cls_entry.get("capture_strategy") != "bundle-source":
            continue
        source_dir = _extract_source_dir(name, cls_entry)
        if source_dir is None or not source_dir.is_dir():
            unresolved.append({
                "name": name,
                "server_class": cls_entry.get("server_class"),
                "reason": f"could not locate source dir from args={cls_entry.get('args')}",
            })
            continue

        est_size = _estimate_dir_size(source_dir, TAR_EXCLUDE_DIR_PARTS)
        git_remote = _git_remote_for(source_dir)

        if est_size > hard_limit_bytes:
            skipped.append(asdict(SkippedSource(
                name=name,
                server_class=cls_entry.get("server_class", "?"),
                source_dir=str(source_dir),
                reason=(
                    f"estimated size {est_size} > hard_limit {hard_limit_bytes}; "
                    "use git remote on import"
                ),
                estimated_size_bytes=est_size,
            )))
            continue

        bundle_path = dest_dir / f"{name}.tar.gz"
        warnings: list[str] = []
        if est_size > soft_warn_bytes:
            warnings.append(
                f"source dir is large ({est_size} bytes after exclusions) — "
                "review what's being bundled"
            )

        # Tar the source directory
        file_count = 0
        try:
            with tarfile.open(bundle_path, "w:gz") as tar:
                # Walk and add files individually so we can count + filter cleanly
                for p in source_dir.rglob("*"):
                    rel = p.relative_to(source_dir)
                    # Pre-filter at walk time for speed (matches _tar_filter)
                    if any(part in TAR_EXCLUDE_DIR_PARTS for part in rel.parts):
                        continue
                    if any(part.endswith(".egg-info") for part in rel.parts):
                        continue
                    if p.is_file():
                        if any(p.name.endswith(suf) for suf in TAR_EXCLUDE_FILE_SUFFIXES):
                            continue
                        # arcname = "<name>/<rel>" so extraction lands cleanly
                        arcname = f"{name}/{rel}"
                        tar.add(p, arcname=arcname, recursive=False)
                        file_count += 1
                    elif p.is_dir():
                        # tarfile auto-creates parent dirs from file entries; skip
                        pass
        except Exception as exc:
            unresolved.append({
                "name": name,
                "server_class": cls_entry.get("server_class"),
                "source_dir": str(source_dir),
                "reason": f"tar failed: {exc!r}",
            })
            if bundle_path.exists():
                try:
                    bundle_path.unlink()
                except OSError:
                    pass
            continue

        py_ver, node_ver = _detect_runtime_version(
            source_dir, cls_entry.get("server_class", "?")
        )

        bundled.append(asdict(BundledSource(
            name=name,
            server_class=cls_entry.get("server_class", "?"),
            source_dir=str(source_dir),
            bundle_relpath=f"mcp-sources/{name}.tar.gz",
            bundle_size_bytes=bundle_path.stat().st_size,
            file_count=file_count,
            warnings=warnings,
            git_remote=git_remote,
            python_version=py_ver,
            node_engines=node_ver,
        )))

    total_bytes = sum(b["bundle_size_bytes"] for b in bundled)
    return {
        "version": "0.1",
        "bundled_count": len(bundled),
        "skipped_count": len(skipped),
        "unresolved_count": len(unresolved),
        "total_bundle_bytes": total_bytes,
        "soft_warn_bytes": soft_warn_bytes,
        "hard_limit_bytes": hard_limit_bytes,
        "bundled": bundled,
        "skipped": skipped,
        "unresolved": unresolved,
    }
