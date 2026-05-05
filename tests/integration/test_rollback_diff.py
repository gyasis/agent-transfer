"""T023 — Integration test: rollback file-tree diff (SC-002).

Verifies that bash rollback.sh restores the destination to byte-identical
pre-ingest state with zero leftover artifacts.

Skipped until T030 (Wave 4) lands the rollback generator.
"""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.skip(
    reason="Awaits T030 (rollback generator, Wave 4). Will be unskipped in T037."
)


def test_rollback_restores_byte_identical_state():
    """SC-002 — file-tree diff before vs after install→rollback shows zero
    leftover artifacts.

    Implementation outline (lands once T030 ships):

    1. snapshot pre-install file tree (paths + sha256 + mode bits)
    2. ab ingest <bundle>           # writes to sandbox HOME
    3. bash rollback.sh             # restore
    4. snapshot post-rollback file tree
    5. assert pre == post-rollback
    """
    raise NotImplementedError("T023 lands when T030 lands")
