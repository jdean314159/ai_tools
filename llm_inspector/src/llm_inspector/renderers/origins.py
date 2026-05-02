"""llm_inspector.renderers.origins — shared origin metadata.

Centralises display labels, ordering, and descriptions for all known
prompt-section origins. Both console/diff renderers and the Streamlit
UI import from here so the vocabulary stays consistent.

Adding a new origin:
  1. Add an entry to ORIGIN_META below.
  2. Add it to ORIGIN_ORDER at the appropriate position.
  Everything else adapts automatically.

Author: Jeffrey Dean
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class OriginMeta:
    """Display metadata for one prompt-section origin."""
    label: str              # Short display label
    description: str        # One-line explanation for beginner/teaching mode
    ui_color: str           # Streamlit / CSS colour for badges and charts
    console_prefix: str     # ASCII prefix for plain-text console output
    is_memory: bool = True  # False for structural sections (system, user)


# ---------------------------------------------------------------------------
# Registry — one entry per known origin string
# ---------------------------------------------------------------------------
ORIGIN_META: Dict[str, OriginMeta] = {
    "system": OriginMeta(
        label="System",
        description="Instructions injected before the conversation to shape model behaviour.",
        ui_color="#6c757d",       # muted grey
        console_prefix="[SYS]",
        is_memory=False,
    ),
    "working": OriginMeta(
        label="Working memory",
        description="The recent conversation turns held in fast, short-term memory.",
        ui_color="#0d6efd",       # blue
        console_prefix="[WRK]",
    ),
    "episodic": OriginMeta(
        label="Episodic memory",
        description="Relevant past episodes retrieved by semantic similarity to the query.",
        ui_color="#198754",       # green
        console_prefix="[EPI]",
    ),
    "semantic": OriginMeta(
        label="Semantic memory",
        description="Structured facts and preferences extracted from past conversations.",
        ui_color="#0dcaf0",       # cyan
        console_prefix="[SEM]",
    ),
    "cold": OriginMeta(
        label="Cold storage",
        description="Older archived episodes retrieved by keyword matching as a fallback.",
        ui_color="#6f42c1",       # purple
        console_prefix="[CLD]",
    ),
    "synthesis": OriginMeta(
        label="Procedural rules",
        description=(
            "Generalizable rules extracted from past sessions — 'when X, do Y' patterns "
            "that apply across many conversations."
        ),
        ui_color="#fd7e14",       # orange — visually distinct from all memory tiers
        console_prefix="[RUL]",
    ),
    "user": OriginMeta(
        label="User",
        description="The current user message.",
        ui_color="#adb5bd",       # light grey
        console_prefix="[USR]",
        is_memory=False,
    ),
}

# Display order for sections (unknown origins go at the end, before user)
ORIGIN_ORDER: List[str] = [
    "system",
    "working",
    "episodic",
    "semantic",
    "cold",
    "synthesis",
    "user",
]


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_meta(origin: str) -> OriginMeta:
    """Return OriginMeta for a known origin, or a sensible default."""
    if origin in ORIGIN_META:
        return ORIGIN_META[origin]
    # Unknown origin — generate a neutral fallback
    label = origin.replace("_", " ").title()
    return OriginMeta(
        label=label,
        description=f"Custom section: {label}.",
        ui_color="#adb5bd",
        console_prefix=f"[{origin[:3].upper()}]",
    )


def console_prefix(origin: str) -> str:
    """Return the console prefix for an origin (e.g. '[EPI]')."""
    return get_meta(origin).console_prefix


def ui_color(origin: str) -> str:
    """Return the CSS/hex colour for an origin."""
    return get_meta(origin).ui_color


def label(origin: str) -> str:
    """Return the human-readable display label for an origin."""
    return get_meta(origin).label


def description(origin: str) -> str:
    """Return the beginner-mode description for an origin."""
    return get_meta(origin).description


def sort_key(origin: str) -> int:
    """Integer sort key respecting ORIGIN_ORDER; unknowns sort after cold."""
    try:
        return ORIGIN_ORDER.index(origin)
    except ValueError:
        return ORIGIN_ORDER.index("user") - 1  # before user, after synthesis


def sorted_origins(origins) -> List[str]:
    """Sort an iterable of origin strings by canonical display order."""
    return sorted(origins, key=sort_key)


def memory_origins() -> List[str]:
    """Return all origins marked is_memory=True, in display order."""
    return [o for o in ORIGIN_ORDER if ORIGIN_META.get(o, OriginMeta("","","","", False)).is_memory]
