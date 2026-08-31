from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

from llm_harness_core import LLMMessage, OperationResult


@dataclass(frozen=True)
class AugmentRequest:
    session_id: str
    user_text: str
    query: Optional[str] = None
    max_prompt_tokens: Optional[int] = None
    reserve_output_tokens: int = 512
    options: dict[str, Any] = field(default_factory=dict)

    def to_interop_message(self) -> LLMMessage:
        return LLMMessage(
            role="user", content=self.user_text, metadata={"session_id": self.session_id}
        )


@dataclass(frozen=True)
class AugmentResult:
    prompt: str
    trace: Any = None
    prompt_tokens: Optional[int] = None
    memory_tokens: Optional[int] = None
    compressed: bool = False
    raw_context: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_interop_result(self) -> OperationResult[str]:
        diagnostics = {
            "prompt_tokens": self.prompt_tokens,
            "memory_tokens": self.memory_tokens,
            "compressed": self.compressed,
            "metadata": dict(self.metadata),
        }
        return OperationResult.success(self.prompt, diagnostics=diagnostics)


@dataclass(frozen=True)
class MemoryObservation:
    """A turn or episode presented to extension layers for learning."""

    role: str
    text: str
    session_id: str
    embedding: tuple[float, ...] | None = None
    surprise: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecallQuery:
    """A recall or prompt query presented to extension layers."""

    query: str
    session_id: str | None = None
    embedding: tuple[float, ...] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecallContribution:
    """Spread-relative advisory contributions to core recall ranking.

    Each affinity value is dimensionless. The recall seam multiplies it by the
    original candidate score spread before applying it to a candidate.
    """

    affinity: dict[str, float] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PromptHint:
    """An optional advisory contribution to prompt assembly."""

    text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class MemoryLayer(Protocol):
    """Optional memory extension invoked at stable ProjectMemory seams."""

    name: str

    def observe(self, observation: MemoryObservation) -> None: ...

    def contribute_to_recall(self, query: RecallQuery) -> RecallContribution | None: ...

    def contribute_to_prompt(self, query: RecallQuery) -> PromptHint | None: ...

    def warmup(self, history: list[MemoryObservation]) -> None: ...

    def persist(self) -> None: ...

    def close(self) -> None: ...


@runtime_checkable
class PromptAugmenter(Protocol):
    augmenter_id: str

    def new_session(self, session_id: str) -> None: ...

    def add_turn(self, role: str, text: str, session_id: str) -> None: ...

    def augment(self, request: AugmentRequest) -> AugmentResult: ...
