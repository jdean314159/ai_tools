"""
engram_lite.inspection — re-exports from engram.inspection.

The canonical implementation lives in engram.inspection.
This module preserves backward compatibility for any code importing
directly from engram_lite.inspection.
"""
from engram.inspection import (  # noqa: F401
    EvidenceTrace,
    EvidenceItem,
    PromptBuildTrace,
    PromptSectionTrace,
    Section,
    TokenAccountingTrace,
)

__all__ = [
    "EvidenceTrace",
    "EvidenceItem",
    "PromptBuildTrace",
    "PromptSectionTrace",
    "Section",
    "TokenAccountingTrace",
]
