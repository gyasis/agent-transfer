"""K — discovery's bin_dirs are protected from symlink-escape.

Pre-fix: B (audit-2 follow-up) hardened the registry path. The discovery
path (compose.py / script_discovery.py) walks ~/bin and ~/.local/bin
unguarded — an attacker-planted symlink ~/bin/sio → /etc/shadow would
be picked up by `discover_referenced_scripts` and shipped.

Post-fix: bin-dir entries that are symlinks pointing OUTSIDE $HOME are
skipped silently. In-HOME symlinks (legitimate tool-manager farms) keep
working.
"""

from __future__ import annotations

import os
from pathlib import Path

from agent_transfer.utils.script_discovery import discover_referenced_scripts


def test_k_symlink_escaping_home_is_skipped(tmp_path):
    home = tmp_path / "home"
    bin_dir = home / "bin"
    bin_dir.mkdir(parents=True)
    config_dir = home / ".claude"
    config_dir.mkdir()

    # Plant an OUTSIDE-HOME target.
    outside = tmp_path / "outside" / "evil"
    outside.parent.mkdir()
    outside.write_text("#!/bin/sh\necho pwned\n")
    outside.chmod(0o755)

    # Symlink inside ~/bin pointing OUT of HOME.
    (bin_dir / "evil").symlink_to(outside)

    # Reference it from a config file under .claude.
    cfg = config_dir / "rules.md"
    cfg.write_text("Run ~/bin/evil to do the thing.\n")

    refs = discover_referenced_scripts(
        config_roots=[cfg],
        bin_dirs=[bin_dir],
        home=str(home),
        include_lenient=True,
    )
    refs_basenames = {r.script_path.name for r in refs}
    assert "evil" not in refs_basenames, (
        "K regression: out-of-HOME symlink in ~/bin was discovered and "
        "would be bundled. The destination's /etc/shadow (or any other "
        "outside-HOME path) must NOT ride along."
    )


def test_k_in_home_symlink_still_works(tmp_path):
    """Legitimate in-HOME symlink farm — must keep working."""
    home = tmp_path / "home"
    bin_dir = home / "bin"
    bin_dir.mkdir(parents=True)
    real_dir = home / ".local" / "share" / "tool"
    real_dir.mkdir(parents=True)
    real = real_dir / "good-cmd"
    real.write_text("#!/bin/sh\n")
    real.chmod(0o755)

    (bin_dir / "good-cmd").symlink_to(real)

    config_dir = home / ".claude"
    config_dir.mkdir()
    cfg = config_dir / "rules.md"
    cfg.write_text("Use ~/bin/good-cmd.\n")

    refs = discover_referenced_scripts(
        config_roots=[cfg],
        bin_dirs=[bin_dir],
        home=str(home),
        include_lenient=True,
    )
    basenames = {r.script_path.name for r in refs}
    assert "good-cmd" in basenames, (
        "in-HOME symlink legitimately should still be discovered"
    )


def test_k_real_file_in_bin_still_works(tmp_path):
    """Plain file (not a symlink) — baseline check, must still work."""
    home = tmp_path / "home"
    bin_dir = home / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "real-cmd").write_text("#!/bin/sh\n")
    (bin_dir / "real-cmd").chmod(0o755)

    config_dir = home / ".claude"
    config_dir.mkdir()
    cfg = config_dir / "rules.md"
    cfg.write_text("Use ~/bin/real-cmd.\n")

    refs = discover_referenced_scripts(
        config_roots=[cfg],
        bin_dirs=[bin_dir],
        home=str(home),
        include_lenient=True,
    )
    basenames = {r.script_path.name for r in refs}
    assert "real-cmd" in basenames
