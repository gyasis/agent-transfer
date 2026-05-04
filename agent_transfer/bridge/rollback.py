"""All-or-nothing rollback snapshot — generated before any destination write.

Snapshots the union of (every dest path the bundle will touch) +
(~/.claude.json) + (~/.claude/settings.json). Emits rollback.tar.gz +
rollback.sh. Implementation lands in T030 (Wave 4).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Tuple


def snapshot(targets: Iterable[Path], bundle_root: Path) -> Tuple[Path, Path]:
    """Return (rollback_tar, rollback_sh). Implemented in T030 (Wave 4)."""
    raise NotImplementedError("snapshot() lands in T030 (Wave 4)")
