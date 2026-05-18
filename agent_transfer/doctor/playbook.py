"""`agent-transfer doctor playbook` — pre-init bootstrap generator.

Inspects the host's runtime + filesystem state, then emits a structured
playbook another agent can ingest to bring the host up to the level
`agent-transfer init` requires. Markdown for humans + JSON sidecar for
agents. Read-only on the host — never installs.

The playbook lists ONLY the actionable items (warn/fail). Passing
checks are summarized in a header but not echoed as actions.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from agent_transfer.doctor.checks import (
    CheckResult,
    darwin_specific_checks,
    runtime_checks,
)


@dataclass
class PlaybookStep:
    """One actionable item for the bootstrapping agent."""

    id: str               # mirrors CheckResult.id
    title: str
    severity: str         # "warn" | "error"
    detail: str
    fix_hint: str
    command: Optional[str] = None  # platform-resolved single command
    raw_check: dict = field(default_factory=dict)


@dataclass
class Playbook:
    generated_at: str
    platform: str
    home: str
    steps: list[PlaybookStep] = field(default_factory=list)
    pass_count: int = 0     # informational
    skip_count: int = 0

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "platform": self.platform,
            "home": self.home,
            "pass_count": self.pass_count,
            "skip_count": self.skip_count,
            "step_count": len(self.steps),
            "steps": [asdict(s) for s in self.steps],
        }

    def to_markdown(self) -> str:
        lines: list[str] = []
        lines.append(f"# agent-transfer doctor playbook — {self.platform}\n")
        lines.append(f"Generated at: {self.generated_at}")
        lines.append(f"Target home: `{self.home}`\n")
        lines.append(
            "## Purpose\n\n"
            "This playbook lists the actionable steps another Claude instance "
            "(or a human) should take to bring this host to a state where "
            "`agent-transfer init` will succeed against a bundle. Each step "
            "is paired with a verified one-line fix command for this platform.\n"
        )
        lines.append(f"## Summary\n\n- Passing checks: {self.pass_count}")
        lines.append(f"- Skipped (not applicable): {self.skip_count}")
        lines.append(f"- Action items below: {len(self.steps)}\n")

        if not self.steps:
            lines.append(
                "**No action items.** This host is ready for `agent-transfer init`.\n"
            )
            return "\n".join(lines)

        lines.append("## Action Items\n")
        for i, step in enumerate(self.steps, 1):
            sym = "❌" if step.severity == "error" else "⚠️"
            lines.append(f"### {i}. {sym} {step.title} (`{step.id}`)\n")
            lines.append(f"- **Severity:** {step.severity}")
            lines.append(f"- **Detail:** {step.detail}")
            lines.append(f"- **Fix:** {step.fix_hint}")
            if step.command:
                lines.append(f"\n```bash\n{step.command}\n```\n")
            else:
                lines.append("")

        lines.append("## Verification\n")
        lines.append(
            "After running the steps above, re-run `agent-transfer doctor "
            "playbook` and confirm action items are zero before proceeding "
            "to `agent-transfer init`.\n"
        )
        return "\n".join(lines)


def _platform_command(check: CheckResult, plat: str) -> Optional[str]:
    if plat == "darwin":
        return check.fix_command_darwin
    if plat == "linux":
        return check.fix_command_linux
    return None


def _check_to_step(check: CheckResult, plat: str) -> Optional[PlaybookStep]:
    if check.status not in ("warn", "fail"):
        return None
    severity = "error" if check.status == "fail" else "warn"
    return PlaybookStep(
        id=check.id,
        title=check.title,
        severity=severity,
        detail=check.detail,
        fix_hint=check.fix_hint or "Resolve the condition above before init.",
        command=_platform_command(check, plat),
        raw_check=asdict(check),
    )


def run_playbook(home: Optional[Path] = None) -> Playbook:
    home = home or Path.home()
    plat = "darwin" if sys.platform == "darwin" else (
        "linux" if sys.platform.startswith("linux") else sys.platform
    )
    pb = Playbook(
        generated_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
        platform=plat,
        home=str(home),
    )

    checks: list[CheckResult] = []
    checks.extend(runtime_checks(home))
    if plat == "darwin":
        checks.extend(darwin_specific_checks())

    for c in checks:
        if c.status == "pass":
            pb.pass_count += 1
        elif c.status == "skip":
            pb.skip_count += 1
        else:
            step = _check_to_step(c, plat)
            if step is not None:
                pb.steps.append(step)
    return pb
