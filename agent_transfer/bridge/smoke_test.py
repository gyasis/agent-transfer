"""Post-install smoke test — receiving Claude self-interrogation.

Validates that every declared asset is present at its declared path with
declared mode, runs `session-search foo` on empty corpus, and checks
"who are you" against the source manifest. Implementation lands in T034
(Wave 3).
"""

from __future__ import annotations

from agent_transfer.bridge.models import ManifestModel


def run(manifest: ManifestModel) -> None:
    """Run smoke test, flag drift. Implemented in T034 (Wave 3)."""
    raise NotImplementedError("run() lands in T034 (Wave 3)")
