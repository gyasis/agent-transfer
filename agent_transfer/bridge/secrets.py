"""Merged secret regex scanner — runs pre-seal AND post-seal on every bundle.

Constitution: R8 (no secret transfer). Spec FR-010, SC-006.

Detects:
- Bearer tokens                       (HTTP auth headers)
- OpenAI-style                        (sk-...)
- GitHub personal access tokens       (ghp_..., gho_..., ghs_..., ghu_..., ghr_...)
- Slack tokens                        (xoxb-..., xoxp-..., xoxa-..., xoxr-...)
- Bitbucket app passwords             (ATBB...)
- Generic high-entropy fallback       (long alphanumerics with required entropy)

The two real Bitbucket app-password leaks the existing classifier caught
during the parent-PRD work are covered by both the targeted ATBB pattern
and the generic high-entropy fallback.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable, List, Pattern

# Targeted patterns — high precision, low false-positive rate.
_TARGETED: List[tuple[str, Pattern[str]]] = [
    ("bearer", re.compile(r"\bBearer\s+([A-Za-z0-9._\-]{16,})", re.IGNORECASE)),
    ("openai_sk", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("github_pat", re.compile(r"\bgh[posur]_[A-Za-z0-9]{30,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("bitbucket_app_password", re.compile(r"\bATBB[A-Za-z0-9]{20,}\b")),
    # Anthropic API keys
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{30,}\b")),
    # AWS access key
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
]

# Generic fallback — long alphanumeric strings with high Shannon entropy.
# Conservative threshold to limit false positives. Used when targeted patterns
# don't fire but content is suspicious (e.g., env var values).
#
# Note: `/` is intentionally excluded from the character class. Real-world
# secret formats (Bearer, sk-, ghp_, xox*, ATBB, AKIA, sk-ant-) never use
# forward slash inside token bodies — they are all word-class characters.
# Including `/` previously caused false positives on filesystem paths in
# documentation (`claude/skills/sio-velocity/SKILL`, MCP tool identifiers
# like `mcp__playwright__browser_take_screenshot`, etc.) — see 2026-05-21
# SIO-bundle regression. Standard-alphabet base64 secrets that happen to
# contain `/` will now match as multiple sub-segments; in practice the
# 32-char minimum already misses short base64 anyway, and any production
# secret long enough to matter will still have ≥32 contiguous slash-free
# chars somewhere.
_GENERIC = re.compile(r"\b[A-Za-z0-9_\-+=]{32,}\b")
_ENTROPY_THRESHOLD = 4.0  # bits per character — typical password material is 4.5+


@dataclass(frozen=True)
class SecretFinding:
    """One match. `start`/`end` are byte offsets in the input string."""

    pattern: str
    match: str
    start: int
    end: int


def _shannon_entropy(s: str) -> float:
    """Bits per character. Returns 0.0 for empty input."""
    if not s:
        return 0.0
    freq: dict[str, int] = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def scan(text: str) -> List[SecretFinding]:
    """Scan input text and return all findings.

    Targeted patterns run first; generic high-entropy fallback runs after
    and only emits matches that the targeted patterns missed. The generic
    pass requires both length >= 32 AND Shannon entropy >= 4.0 bits/char.
    """
    findings: List[SecretFinding] = []
    covered: List[tuple[int, int]] = []

    for name, pat in _TARGETED:
        for m in pat.finditer(text):
            findings.append(
                SecretFinding(pattern=name, match=m.group(0), start=m.start(), end=m.end())
            )
            covered.append((m.start(), m.end()))

    for m in _GENERIC.finditer(text):
        if any(m.start() < e and m.end() > s for s, e in covered):
            continue
        candidate = m.group(0)
        if _shannon_entropy(candidate) < _ENTROPY_THRESHOLD:
            continue
        # Skip MCP-style tool identifiers (`mcp__playwright__browser_take_screenshot`,
        # `mcp__atlassian-remote__searchJiraIssuesUsingJql`, etc.). The double-
        # underscore convention is distinctive — no real-world secret format
        # (Bearer / sk- / sk-ant- / ghp_ / xox* / ATBB / AKIA) ever uses `__`
        # inside the token body. Skipping these prevents false positives in
        # skill / agent documentation that references MCP tools.
        if "__" in candidate:
            continue
        # Skip kebab/snake-case identifiers composed of English-word segments
        # (recipe filenames like `hh-zombie-stack-diagnosis-and-cleanup`, PRD
        # IDs like `L010_sio_render_artifact_capture_2026-05-08`, etc.). Real
        # secrets are atomic random tokens — they don't contain multiple 4+
        # letter pure-ASCII segments separated by `-` or `_`. This heuristic
        # requires AT LEAST 2 such segments before skipping, so single-word
        # high-entropy tokens like `abcdefghijklmnopqrstuvwxyz123456` still
        # match (no separators) and short letter segments (like `abc-def-...`)
        # don't trigger it either.
        _segments = re.split(r"[-_]+", candidate)
        _word_segments = [s for s in _segments if s.isalpha() and len(s) >= 4]
        if len(_word_segments) >= 2:
            continue
        findings.append(
            SecretFinding(pattern="generic_high_entropy", match=candidate, start=m.start(), end=m.end())
        )

    findings.sort(key=lambda f: f.start)
    return findings


def scan_files(paths: Iterable[str]) -> dict[str, List[SecretFinding]]:
    """Convenience — scan a list of file paths and return path -> findings."""
    out: dict[str, List[SecretFinding]] = {}
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        hits = scan(text)
        if hits:
            out[path] = hits
    return out


def has_secrets(text: str) -> bool:
    """Cheap boolean — true iff scan() would return at least one finding."""
    return bool(scan(text))
