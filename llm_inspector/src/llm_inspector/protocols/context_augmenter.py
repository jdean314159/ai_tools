from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from llm_harness_core import LLMMessage

from llm_inspector.core import Trace, Turn


@dataclass(frozen=True)
class AugmentRequest:
    """Normalized request object so we can evolve args without breaking signatures."""

    turn: Turn
    query: Optional[str] = None
    session_id: str = "default"

    def to_interop_message(self) -> LLMMessage:
        return self.turn.to_interop_message()


@runtime_checkable
class ContextAugmenter(Protocol):
    """A general context augmentation interface (memory, retrieval, tools, etc.)."""

    @property
    def name(self) -> str: ...

    def augment(self, req: AugmentRequest) -> Trace: ...
