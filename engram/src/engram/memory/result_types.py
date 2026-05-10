"""result_types — shared data containers for Engram memory runtime.

Extracted from project_memory.py so they can be imported without pulling
in the full ProjectMemory machinery.

Author: Jeffrey Dean
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TokenBudget:
    """Token allocation across memory layers.

    Defaults from README specifications. Adjust per project as needed.
    """
    working: int = 1000
    episodic: int = 800
    semantic: int = 400
    cold: int = 400
    procedural: int = 200   # Layer 6 — skill procedures

    @property
    def total(self) -> int:
        return self.working + self.episodic + self.semantic + self.cold + self.procedural


@dataclass
class SynthesisHookConfig:
    """Configuration for the session-end synthesis approval hook.

    When enabled, ProjectMemory.end_session() fires an approval prompt
    when enough episodes have accumulated since the last synthesis run.
    The caller provides an approval_callback that returns True (run now)
    or False (defer). Default callback uses stdin/stdout.

    Args:
        enabled: Off by default — opt-in per project.
        episode_threshold: Min new episodes per session to trigger prompt.
        approval_callback: Callable(prompt_str) -> bool. None = stdout input().
        window_size: Episode window passed to synthesize_now().
        days_back: Lookback window for synthesis episode fetch.
        min_support: Min supporting episodes per rule.
        min_confidence: Min confidence threshold for rule emission.
    """
    enabled: bool = False
    episode_threshold: int = 20
    approval_callback: Optional[Any] = None  # Callable[[str], bool] | None
    window_size: int = 50
    days_back: int = 30
    min_support: int = 3
    min_confidence: float = 0.60
