"""Tests for llm_inspector.renderers.origins.

Verifies:
  1. All seven canonical origins are in ORIGIN_META.
  2. console_prefix() returns correct bracket tags.
  3. label() returns non-empty strings.
  4. sort_key() respects ORIGIN_ORDER.
  5. sorted_origins() preserves canonical order.
  6. Unknown origin gets a sensible fallback (no KeyError).
  7. memory_origins() excludes system and user.
  8. ui_color() returns a hex colour string.
"""

from __future__ import annotations

import pytest


CANONICAL = ["system", "working", "episodic", "semantic", "cold", "synthesis", "user"]

EXPECTED_PREFIXES = {
    "system": "[SYS]",
    "working": "[WRK]",
    "episodic": "[EPI]",
    "semantic": "[SEM]",
    "cold": "[CLD]",
    "synthesis": "[RUL]",
    "user": "[USR]",
}


@pytest.fixture
def origins_mod():
    from llm_inspector.renderers import origins

    return origins


def test_all_canonical_origins_in_meta(origins_mod):
    """Every canonical origin has an entry in ORIGIN_META."""
    for o in CANONICAL:
        assert o in origins_mod.ORIGIN_META, f"Missing from ORIGIN_META: {o!r}"


def test_console_prefixes_correct(origins_mod):
    """console_prefix() returns the expected bracket tag for each origin."""
    for origin, expected in EXPECTED_PREFIXES.items():
        result = origins_mod.console_prefix(origin)
        assert result == expected, f"console_prefix({origin!r}) = {result!r}, expected {expected!r}"


def test_label_returns_nonempty_string(origins_mod):
    """label() returns a non-empty string for every canonical origin."""
    for o in CANONICAL:
        lbl = origins_mod.label(o)
        assert isinstance(lbl, str) and lbl.strip(), (
            f"label({o!r}) returned empty or non-string: {lbl!r}"
        )


def test_sort_key_system_before_user(origins_mod):
    """system has a lower sort key than user."""
    assert origins_mod.sort_key("system") < origins_mod.sort_key("user")


def test_sort_key_synthesis_before_user(origins_mod):
    """synthesis (procedural rules) sorts before user."""
    assert origins_mod.sort_key("synthesis") < origins_mod.sort_key("user")


def test_sort_key_working_before_cold(origins_mod):
    """working memory sorts before cold storage."""
    assert origins_mod.sort_key("working") < origins_mod.sort_key("cold")


def test_sorted_origins_canonical_order(origins_mod):
    """sorted_origins() returns canonical origins in ORIGIN_ORDER sequence."""
    shuffled = ["user", "cold", "system", "episodic", "working", "semantic", "synthesis"]
    result = origins_mod.sorted_origins(shuffled)
    assert result == CANONICAL


def test_unknown_origin_fallback_no_error(origins_mod):
    """get_meta() on an unknown origin returns a fallback, not a KeyError."""
    meta = origins_mod.get_meta("custom_origin_xyz")
    assert meta is not None
    assert isinstance(meta.label, str)
    assert isinstance(meta.console_prefix, str)


def test_unknown_origin_prefix_uses_first_three_chars(origins_mod):
    """Unknown origin prefix is derived from the origin name."""
    prefix = origins_mod.console_prefix("zephyr")
    assert prefix.startswith("[")
    assert prefix.endswith("]")
    assert "ZEP" in prefix


def test_memory_origins_excludes_structural(origins_mod):
    """memory_origins() must not include 'system' or 'user'."""
    mem = origins_mod.memory_origins()
    assert "system" not in mem, "'system' must not be a memory origin"
    assert "user" not in mem, "'user' must not be a memory origin"


def test_memory_origins_includes_synthesis(origins_mod):
    """memory_origins() includes 'synthesis' (procedural rules are memory)."""
    assert "synthesis" in origins_mod.memory_origins()


def test_ui_color_returns_hex_string(origins_mod):
    """ui_color() returns a CSS hex string for all canonical origins."""
    import re

    hex_re = re.compile(r"^#[0-9a-fA-F]{6}$")
    for o in CANONICAL:
        color = origins_mod.ui_color(o)
        assert hex_re.match(color), f"ui_color({o!r}) = {color!r} is not a valid hex colour"


def test_description_returns_nonempty_string(origins_mod):
    """description() returns a non-empty string for all canonical origins."""
    for o in CANONICAL:
        desc = origins_mod.description(o)
        assert isinstance(desc, str) and desc.strip(), (
            f"description({o!r}) returned empty: {desc!r}"
        )
