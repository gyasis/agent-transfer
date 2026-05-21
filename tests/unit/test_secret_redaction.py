"""T019 — Unit test: merged secret regex (FR-010, SC-006).

Positive + negative cases for Bearer / sk- / sk-ant- / ghp_ / xox / ATBB /
AKIA / generic high-entropy fallback.
"""

from __future__ import annotations

import pytest

from agent_transfer.bridge.secrets import has_secrets, scan


# --- Positive cases — these MUST be detected --- #

POSITIVE_CASES = [
    ("bearer", "Authorization: Bearer abc123_def456_ghi789"),
    ("openai", "OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyzABCD"),
    ("anthropic", "ANTHROPIC_API_KEY=sk-ant-api03-deadbeef0123456789abcdef0123456789"),
    ("github", "token=ghp_abcdefghijklmnopqrstuvwxyzABCDEF1234"),
    ("github_oauth", "token=gho_abcdefghijklmnopqrstuvwxyzABCDEF1234"),
    ("slack_bot", "token=xoxb-12345-67890-abcdefghijklmn"),
    ("bitbucket", "BITBUCKET_APP_PASSWORD=ATBBabcdefghijklmnopqrstuvwxyz123"),
    ("aws", "aws_access_key_id=AKIAIOSFODNN7EXAMPLE"),
]


@pytest.mark.parametrize("name,text", POSITIVE_CASES)
def test_positive_detection(name, text):
    findings = scan(text)
    assert findings, f"{name} pattern was missed: {text!r}"


# --- Negative cases — must NOT trigger --- #

NEGATIVE_CASES = [
    "Just plain prose with no secrets at all.",
    "echo hello world",
    "The quick brown fox jumps over the lazy dog.",
    "version=1.2.3",
    "name=John",
    "abc",
    "",
]


@pytest.mark.parametrize("text", NEGATIVE_CASES)
def test_no_false_positives(text):
    assert not has_secrets(text), f"False positive on benign text: {text!r}"


# --- Generic high-entropy fallback --- #


def test_generic_fallback_catches_high_entropy_long_string():
    # 40-char string with high entropy — should fall through to generic.
    secret = "8gK4mZpQ9wRxNvBcLaToYuI6sJdEfHnVbWqXrPzC"
    assert has_secrets(secret)


def test_generic_fallback_skips_low_entropy_long_string():
    # 40 chars but low entropy (only 2 unique characters) — must NOT match.
    low_entropy = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert not has_secrets(low_entropy)


# --- Pattern naming --- #


def test_pattern_names_are_specific_when_targeted_match():
    findings = scan("Authorization: Bearer somelongtokenherewithatleast16chars")
    assert any(f.pattern == "bearer" for f in findings)


def test_findings_sorted_by_position():
    text = "first sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa then ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    findings = scan(text)
    assert findings == sorted(findings, key=lambda f: f.start)


# --- Path / identifier false-positive regression (2026-05-21 SIO bundle) --- #

PATH_FALSE_POSITIVES = [
    # Asset dest_paths inside the manifest — were tripping the SIO bundle
    "claude/skills/sio-velocity/SKILL.md",
    "claude/skills/sio-promote-flow/SKILL.md",
    "claude/skills/sio-briefing/SKILL.md",
    "~/.claude/skills/sio-rule-audit/SKILL.md",
    # MCP tool identifiers (long, mixed-case, but slash-free underscores)
    "mcp__playwright__browser_take_screenshot",
    "mcp__atlassian-remote__searchJiraIssuesUsingJql",
    # JSONL transcript / recipe paths in skill docs
    "claude/projects/-home-gyasisutton-dev/recipes/hh-zombie-stack",
    "/home/gyasisutton/.claude/projects/-home-gyasisutton-dev/memory",
]


@pytest.mark.parametrize("text", PATH_FALSE_POSITIVES)
def test_path_strings_not_flagged(text):
    """Filesystem paths and tool identifiers must NOT trigger the generic
    high-entropy detector. Real secret formats never contain `/`, so the
    detector's char class excludes it (see _GENERIC docstring).
    """
    assert not has_secrets(text), f"False positive on path-like string: {text!r}"


# --- Kebab/snake-case identifier false positives (2026-05-21 SIO bundle, round 2) --- #

IDENTIFIER_FALSE_POSITIVES = [
    # Recipe filenames found in skill documentation
    "hh-zombie-stack-diagnosis-and-cleanup",
    "hh-cdia-scoring-form-local-dev-walkthrough",
    # PRD IDs (library tier — Lxxx prefix + descriptor + date)
    "L010_sio_render_artifact_capture_2026-05-08",
    "L016_agentbridge_capability_transfer_2026-05-03",
    # Skill identifiers with timestamps
    "sio_backend_dead_loop_2026-04-15",
    "synthetic_amplification_pattern_audit",
]


@pytest.mark.parametrize("text", IDENTIFIER_FALSE_POSITIVES)
def test_word_segment_identifiers_not_flagged(text):
    """Long identifiers composed of English-word segments separated by `-`
    or `_` must NOT trigger the generic high-entropy detector. Real secrets
    are atomic random tokens — they don't contain multiple 4+ letter
    pure-ASCII segments. See _GENERIC scan loop docstring.
    """
    assert not has_secrets(text), f"False positive on word-segment identifier: {text!r}"


def test_single_word_high_entropy_still_caught():
    """The word-segment heuristic must NOT mask single-token high-entropy
    secrets. A 40-char random alphanumeric blob with NO `-`/`_` separators
    has no word segments and must still match.
    """
    # 40 chars, mixed case, no separators
    secret = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN"
    assert has_secrets(secret)


def test_two_short_letter_segments_still_caught():
    """The heuristic requires segments of length ≥4. A blob like
    `abc-def-ghi-jkl-mno-pqr-stu-vwx-yzaaaaaaaaaa` has only short
    segments (each <4) — heuristic should NOT skip it.
    """
    # Build a 32+ char string of 3-letter segments — len<4 so the
    # word-segment heuristic doesn't fire.
    candidate = "abc-def-ghi-jkl-mno-pqr-stu-vwx-yz1-234"  # 39 chars
    # Verify it has the length + entropy to enter the generic path
    findings = scan(candidate)
    # Either caught (good) or the entropy itself is below threshold;
    # what matters is the heuristic doesn't ITSELF mask it.
    # Worst case: entropy fails. Best case: caught.
    # Assert the test is exercising the right code path:
    from agent_transfer.bridge.secrets import _shannon_entropy
    assert len(candidate) >= 32
    if _shannon_entropy(candidate) >= 4.0:
        assert findings, "Short-segment string with sufficient entropy should still be flagged"
