"""Unit tests for `_open_bundle` wrapper-directory auto-detection.

Origin: 2026-05-21 — `ab ingest <bundle.tar.gz>` failed with "Bundle missing
manifest.json" against a tarball produced by `ab compose`, because the
compose-side archive wraps everything in a single `bundle-<capability>/`
directory at the root, while `_open_bundle` looked for `manifest.json`
directly at the extraction root. These tests pin the auto-detect behavior
so the round-trip works without manual unpacking.
"""

from __future__ import annotations

import tarfile
from pathlib import Path

from agent_transfer.bridge.ingest import _open_bundle


def _make_tarball(tar_path: Path, files: dict[str, str]) -> None:
    """Build a .tar.gz from a {member_path: text_content} mapping."""
    staging = tar_path.parent / f".{tar_path.stem}_staging"
    staging.mkdir(exist_ok=True)
    try:
        with tarfile.open(tar_path, "w:gz") as tar:
            for name, content in files.items():
                src = staging / name.replace("/", "__")
                src.write_text(content)
                tar.add(src, arcname=name)
    finally:
        for child in staging.iterdir():
            child.unlink()
        staging.rmdir()


def test_open_bundle_dir_returns_dir(tmp_path: Path) -> None:
    """Passing a directory directly returns it unchanged (no extraction)."""
    d = tmp_path / "some-bundle"
    d.mkdir()
    (d / "manifest.json").write_text("{}")
    assert _open_bundle(d) == d


def test_open_bundle_unwraps_single_wrapper_dir(tmp_path: Path) -> None:
    """ab compose convention: tarball contents live under `bundle-<cap>/`."""
    tar = tmp_path / "bundle-foo-20260521.tar.gz"
    _make_tarball(
        tar,
        {
            "bundle-foo/manifest.json": "{}",
            "bundle-foo/BRIEFING.md": "# briefing\n",
        },
    )
    result = _open_bundle(tar)
    assert (result / "manifest.json").exists(), (
        f"Expected manifest.json under returned dir, got {result}"
    )
    assert result.name == "bundle-foo"


def test_open_bundle_no_wrapper_returns_extraction_root(tmp_path: Path) -> None:
    """Backward-compat: a tarball with manifest at the root still works."""
    tar = tmp_path / "flat-bundle.tar.gz"
    _make_tarball(
        tar,
        {
            "manifest.json": "{}",
            "BRIEFING.md": "# briefing\n",
        },
    )
    result = _open_bundle(tar)
    assert (result / "manifest.json").exists()
    assert result.name.endswith("-extracted")


def test_open_bundle_multiple_subdirs_does_not_auto_pick(tmp_path: Path) -> None:
    """If the tarball has multiple subdirs at root, don't try to auto-pick.

    The downstream manifest lookup will then raise a clear error, which is
    the correct behavior — ambiguity must not be silently resolved.
    """
    tar = tmp_path / "ambiguous.tar.gz"
    _make_tarball(
        tar,
        {
            "bundle-foo/manifest.json": "{}",
            "extra-dir/something.md": "stray\n",
        },
    )
    result = _open_bundle(tar)
    assert not (result / "manifest.json").exists()
    assert result.name.endswith("-extracted")


def test_open_bundle_subdir_without_manifest_no_unwrap(tmp_path: Path) -> None:
    """A single subdir lacking manifest.json does NOT trigger unwrap."""
    tar = tmp_path / "no-manifest-anywhere.tar.gz"
    _make_tarball(
        tar,
        {
            "just-some-dir/random.md": "hi\n",
        },
    )
    result = _open_bundle(tar)
    assert not (result / "manifest.json").exists()
    assert result.name.endswith("-extracted")
