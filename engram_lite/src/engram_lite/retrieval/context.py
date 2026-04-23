from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ContextResult:
    working: list[Any] = field(default_factory=list)
    episodic: list[Any] = field(default_factory=list)
    semantic: list[Any] = field(default_factory=list)
    cold: list[Any] = field(default_factory=list)

    working_tokens: int = 0
    episodic_tokens: int = 0
    semantic_tokens: int = 0
    cold_tokens: int = 0

    def memory_tokens(self) -> int:
        return (
            int(self.working_tokens)
            + int(self.episodic_tokens)
            + int(self.semantic_tokens)
            + int(self.cold_tokens)
        )
