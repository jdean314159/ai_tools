"""Compatibility exports for the engram_lite public augmenter contracts.

During the current migration, engram_lite is acting as a compatibility facade
over the canonical augmenter contract types in full engram. Keep this module so
older imports such as `from engram_lite.contracts import AugmentRequest` continue
to work.
"""

from __future__ import annotations

from engram.memory.augment import (
    AugmentRequest,
    AugmentResult,
    ContextResult,
    PromptAugmenter,
)

__all__ = [
    "AugmentRequest",
    "AugmentResult",
    "ContextResult",
    "PromptAugmenter",
]
