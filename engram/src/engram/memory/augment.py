from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

from llm_harness_core import LLMMessage, OperationResult


# ---------------------------------------------------------------------------
# Generic context container (used by the augmenter protocol)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ContextResult:
    """Generic multi-layer context container for the augmenter protocol.

    Fields are plain lists of Any so any memory backend can populate them
    without depending on engram's internal Message/Episode types.

    This is the *public interface* type.  engram's internal ContextResult
    (in project_memory.py) is a richer production type with typed fields
    and procedural/neural layers.
    """
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


# ---------------------------------------------------------------------------
# Augmenter protocol
# ---------------------------------------------------------------------------

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
            role="user",
            content=self.user_text,
            metadata={"session_id": self.session_id},
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


@runtime_checkable
class PromptAugmenter(Protocol):
    augmenter_id: str

    def new_session(self, session_id: str) -> None: ...
    def add_turn(self, role: str, text: str, session_id: str) -> None: ...
    def augment(self, request: AugmentRequest) -> AugmentResult: ...


__all__ = [
    "ContextResult",
    "AugmentRequest",
    "AugmentResult",
    "PromptAugmenter",
]
