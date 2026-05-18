"""`agent-transfer doctor inspect` — post-init health validator.

Runs the cross-platform check suite plus inspect-only checks
(redacted-token scan, MCP sources extracted). Returns a structured
report and a non-zero exit code if any check is `fail`.
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
    check_mcp_sources_extracted,
    check_redacted_tokens,
    darwin_specific_checks,
    runtime_checks,
)


@dataclass
class InspectReport:
    generated_at: str
    platform: str
    home: str
    checks: list[CheckResult] = field(default_factory=list)
    pass_count: int = 0
    warn_count: int = 0
    fail_count: int = 0
    skip_count: int = 0

    @property
    def exit_code(self) -> int:
        return 1 if self.fail_count else 0

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "platform": self.platform,
            "home": self.home,
            "pass_count": self.pass_count,
            "warn_count": self.warn_count,
            "fail_count": self.fail_count,
            "skip_count": self.skip_count,
            "checks": [asdict(c) for c in self.checks],
        }

    def to_markdown(self) -> str:
        symbol = {"pass": "✅", "warn": "⚠️", "fail": "❌", "skip": "—"}
        lines: list[str] = []
        lines.append(f"# agent-transfer doctor inspect — {self.platform}\n")
        lines.append(f"Generated at: {self.generated_at}")
        lines.append(f"Home: `{self.home}`\n")
        lines.append(
            f"Summary: {self.pass_count} pass · {self.warn_count} warn · "
            f"{self.fail_count} fail · {self.skip_count} skip\n"
        )
        lines.append("| | ID | Check | Detail |")
        lines.append("|---|---|---|---|")
        for c in self.checks:
            sym = symbol.get(c.status, "?")
            detail = c.detail.replace("|", "\\|") if c.detail else ""
            lines.append(f"| {sym} | `{c.id}` | {c.title} | {detail} |")
        # Findings + remediation
        problems = [c for c in self.checks if c.status in ("warn", "fail")]
        if problems:
            lines.append("\n## Findings\n")
            for c in problems:
                sym = symbol.get(c.status, "?")
                lines.append(f"### {sym} {c.title} (`{c.id}`)\n")
                if c.detail:
                    lines.append(f"- **Detail:** {c.detail}")
                if c.fix_hint:
                    lines.append(f"- **Fix:** {c.fix_hint}")
                if c.fix_command_darwin and self.platform == "darwin":
                    lines.append(f"- **macOS:** `{c.fix_command_darwin}`")
                if c.fix_command_linux and self.platform == "linux":
                    lines.append(f"- **Linux:** `{c.fix_command_linux}`")
                lines.append("")
        return "\n".join(lines)


def run_inspect(home: Optional[Path] = None) -> InspectReport:
    home = home or Path.home()
    plat = "darwin" if sys.platform == "darwin" else (
        "linux" if sys.platform.startswith("linux") else sys.platform
    )
    report = InspectReport(
        generated_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
        platform=plat,
        home=str(home),
    )

    checks: list[CheckResult] = []
    checks.extend(runtime_checks(home))
    if plat == "darwin":
        checks.extend(darwin_specific_checks())
    # Inspect-only checks (don't belong in pre-init playbook since they
    # need the bundle already extracted / config already written).
    checks.append(check_redacted_tokens(home))
    checks.append(check_mcp_sources_extracted(home))

    report.checks = checks
    for c in checks:
        if c.status == "pass":
            report.pass_count += 1
        elif c.status == "warn":
            report.warn_count += 1
        elif c.status == "fail":
            report.fail_count += 1
        else:
            report.skip_count += 1
    return report
