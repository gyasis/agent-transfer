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
