"""
engram.inspection — re-exports from engram_lite.

The canonical inspection dataclasses live in engram_lite.inspection.
This module exists so that existing code using `from engram.inspection import ...`
continues to work without changes.

If you are writing new code, import directly from engram_lite:
    from engram_lite.inspection import PromptBuildTrace, EvidenceTrace, ...
"""
from engram_lite.inspection import (  # noqa: F401
    EvidenceTrace,
    PromptBuildTrace,
    PromptSectionTrace,
    TokenAccountingTrace,
)

__all__ = [
    "EvidenceTrace",
    "PromptBuildTrace",
    "PromptSectionTrace",
    "TokenAccountingTrace",
]
