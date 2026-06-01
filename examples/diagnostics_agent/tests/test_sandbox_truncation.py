from __future__ import annotations

from diagnostics_agent import SandboxConfig
from diagnostics_agent.sandbox import _truncate_text


def test_tail_truncation_keeps_newest_lines() -> None:
    text = "".join(f"line-{index:03d}\n" for index in range(20))

    truncated, was_truncated = _truncate_text(text, 50, keep="tail")

    assert was_truncated is True
    assert len(truncated.encode("utf-8")) <= 50
    assert "line-019" in truncated
    assert "line-000" not in truncated


def test_head_truncation_keeps_oldest_lines() -> None:
    text = "".join(f"line-{index:03d}\n" for index in range(20))

    truncated, was_truncated = _truncate_text(text, 50, keep="head")

    assert was_truncated is True
    assert len(truncated.encode("utf-8")) <= 50
    assert "line-000" in truncated
    assert "line-019" not in truncated


def test_tail_truncation_drops_partial_leading_line() -> None:
    text = "partial-json-object\nwhole-json-object-1\nwhole-json-object-2\n"

    truncated, was_truncated = _truncate_text(text, 42, keep="tail")

    assert was_truncated is True
    assert truncated == "whole-json-object-1\nwhole-json-object-2\n"


def test_under_cap_is_untouched_for_both_policies() -> None:
    text = "line-1\nline-2\n"

    for keep in ("head", "tail"):
        truncated, was_truncated = _truncate_text(text, 128, keep=keep)

        assert was_truncated is False
        assert truncated == text


def test_zero_byte_cap_drops_output() -> None:
    truncated, was_truncated = _truncate_text("line-1\n", 0, keep="tail")

    assert was_truncated is True
    assert truncated == ""


def test_sandbox_config_defaults_to_tail_and_sixteen_mib() -> None:
    config = SandboxConfig()

    assert config.truncate_keep == "tail"
    assert config.max_output_bytes == 16_777_216
