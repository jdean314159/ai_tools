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
        return LLMMessage(role="user", content=self.user_text, metadata={"session_id": self.session_id})


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

    def new_session(self, session_id: str) -> None:
        ...

    def add_turn(self, role: str, text: str, session_id: str) -> None:
        ...

    def augment(self, request: AugmentRequest) -> AugmentResult:
        ...
