"""Compatibility shim for the historical drills.base module.

The real drill implementation lives in :mod:`language_tutor.drills.drill_system`.
This module is kept importable so older code paths fail gracefully and static
analysis/packaging does not break on a design-stub artifact.
"""

from __future__ import annotations

import warnings

from .drill_system import DrillQuestion, DrillResult, DrillSystem

warnings.warn(
    "language_tutor.drills.base is deprecated; import from "
    "language_tutor.drills.drill_system instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["DrillQuestion", "DrillResult", "DrillSystem"]
