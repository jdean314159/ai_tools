"""
contracts/engine.py

Canonical engine contracts for the AI Toolkit.
All LLM engine implementations must conform to these Protocols.

ADR: ADR-001 (Engine Capability Model), ADR-002 (Engine Response Schema)
Status: Pending ADR acceptance
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Iterator, Literal, Protocol, runtime_checkable

from llm_harness_core import LLMMessage as InteropMessage
from llm_harness_core import OperationResult, OperationWarning, ToolInvocation
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

class LLMEngineError(Exception):
    """Base class for all engine errors."""


class BackendUnavailableError(LLMEngineError):
    """Backend process or service is unreachable (e.g. Ollama not running)."""


class ModelNotFoundError(LLMEngineError):
    """Requested model is not loaded or does not exist on this backend."""


class ContextLengthExceededError(LLMEngineError):
    """Request exceeds the model's maximum context length."""


class RateLimitError(LLMEngineError):
    """Cloud API rate limit hit. Caller should back off and retry."""


class GenerationError(LLMEngineError):
    """Error during token generation (OOM, CUDA error, etc.)."""


class EngineConfigError(LLMEngineError):
    """Engine was constructed with invalid or incompatible configuration."""


# ---------------------------------------------------------------------------
# Prompt compression strategy
# ---------------------------------------------------------------------------

class CompressionStrategy(Enum):
    """How an engine handles prompts that exceed the context window."""
    TRUNCATE_START = "truncate_start"   # Drop oldest content
    TRUNCATE_END   = "truncate_end"     # Drop newest content
    COMPRESS       = "compress"          # Summarise via model (recursive call)
    ERROR          = "error"             # Raise ContextLengthExceededError


# ---------------------------------------------------------------------------
# Logprob types (needed by Engram surprise filter / RTRL neural layer)
# ---------------------------------------------------------------------------

@dataclass
class TokenLogprob:
    """Log probability for a single generated token."""
    token: str
    logprob: float
    bytes: list[int] | None = None


@dataclass
class LogprobResult:
    """Full logprob data for a generation — primary input to the surprise filter."""
    text: str
    token_logprobs: list[TokenLogprob] = field(default_factory=list)

    @property
    def perplexity(self) -> float:
        """Sequence perplexity. High perplexity → surprising content."""
        if not self.token_logprobs:
            return 1.0
        avg_nll = -sum(t.logprob for t in self.token_logprobs) / len(self.token_logprobs)
        return math.exp(avg_nll)

    @property
    def mean_logprob(self) -> float:
        if not self.token_logprobs:
            return 0.0
        return sum(t.logprob for t in self.token_logprobs) / len(self.token_logprobs)

    @property
    def token_count(self) -> int:
        return len(self.token_logprobs)


# ---------------------------------------------------------------------------
# Capability model
# ---------------------------------------------------------------------------

class EngineCapabilities(BaseModel):
    """What this engine can do. Engines report capabilities; callers check before using."""
    chat: bool = True
    streaming: bool = False
    async_streaming: bool = False
    tool_calling: bool = False
    embeddings: bool = False
    structured_output: bool = False
    batch_generation: bool = False
    vision: bool = False
    usage_reporting: bool = True
    logprobs: bool = False
    speculative_decoding: bool = False
    kv_cache_compression: bool = False
    kv_cache_compression_modes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Inference optimization schema
# ---------------------------------------------------------------------------


class InferenceOptimizationRequest(BaseModel):
    """Optional inference-time optimization hints for an engine call."""

    speculative_decoding: bool = False
    draft_model: str | None = None
    speculative_tokens: int | None = None
    kv_cache_compression: str | None = None
    kv_cache_bits: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActiveInferenceOptimization(BaseModel):
    """Optimization reported as active for a specific generation response."""

    kind: Literal["speculative_decoding", "kv_cache_compression", "other"]
    backend: str | None = None
    model: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

FinishReason = Literal[
    "stop",            # Natural completion
    "length",          # Hit max_tokens limit
    "tool_call",       # Model wants to call a tool
    "content_filter",  # Blocked by safety filter
    "error",           # Error occurred during generation
    "unknown",         # Reason not reported by backend
]


class UsageStats(BaseModel):
    """Token usage and timing for a single generation."""
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: float | None = None  # float: sub-ms precision for fast local inference


class ToolCall(BaseModel):
    """Structured tool invocation returned by the model."""
    call_id: str               # Unique ID for this call
    name: str                  # Tool name
    arguments: dict[str, Any]  # Parsed tool arguments

    def to_interop(self) -> ToolInvocation:
        return ToolInvocation(
            call_id=self.call_id,
            name=self.name,
            arguments=dict(self.arguments),
        )

    @classmethod
    def from_interop(cls, value: ToolInvocation) -> "ToolCall":
        return cls(
            call_id=value.call_id,
            name=value.name,
            arguments=dict(value.arguments),
        )


class ChatMessage(BaseModel):
    """Single message in a conversation."""
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    name: str | None = None            # Identifier for tool messages
    tool_call_id: str | None = None    # Links tool result to its originating call
    tool_calls: list[ToolCall] = Field(default_factory=list)

    def to_interop(self) -> InteropMessage:
        return InteropMessage(
            role=self.role,
            content=self.content,
            name=self.name,
            tool_call_id=self.tool_call_id,
            tool_calls=tuple(call.to_interop() for call in self.tool_calls),
        )

    @classmethod
    def from_interop(cls, value: InteropMessage) -> "ChatMessage":
        return cls(
            role=value.role,
            content=value.content,
            name=value.name,
            tool_call_id=value.tool_call_id,
            tool_calls=[ToolCall.from_interop(call) for call in value.tool_calls],
        )


class GenerationRequest(BaseModel):
    """Request to generate text from a conversation."""
    messages: list[ChatMessage]
    max_tokens: int = 512
    temperature: float = 0.7
    stop: list[str] = Field(default_factory=list)
    json_schema: dict[str, Any] | None = None  # For structured output
    metadata: dict[str, Any] = Field(default_factory=dict)
    optimizations: InferenceOptimizationRequest | None = None


class GenerationResponse(BaseModel):
    """Response from a single generation call. Always returned; never plain str."""
    message: ChatMessage
    finish_reason: FinishReason = "unknown"
    usage: UsageStats = Field(default_factory=UsageStats)
    model_name: str
    backend: str
    active_optimizations: list[ActiveInferenceOptimization] = Field(default_factory=list)
    raw_provider_payload: dict[str, Any] | None = None  # Preserved for debugging

    def to_interop_result(self) -> OperationResult[InteropMessage]:
        warnings: list[OperationWarning] = []
        if self.finish_reason == "length":
            warnings.append(
                OperationWarning(
                    code="generation_truncated",
                    message="Generation stopped because the max token limit was reached.",
                )
            )
        elif self.finish_reason == "content_filter":
            warnings.append(
                OperationWarning(
                    code="content_filtered",
                    message="The provider reported that output was filtered.",
                )
            )

        diagnostics = {
            "backend": self.backend,
            "model_name": self.model_name,
            "finish_reason": self.finish_reason,
            "usage": self.usage.model_dump(exclude_none=True),
            "active_optimizations": [opt.model_dump(exclude_none=True) for opt in self.active_optimizations],
        }
        if self.raw_provider_payload is not None:
            diagnostics["raw_provider_payload"] = self.raw_provider_payload

        return OperationResult.success(
            self.message.to_interop(),
            warnings=tuple(warnings),
            diagnostics=diagnostics,
        )


# ---------------------------------------------------------------------------
# Embedding schema
# ---------------------------------------------------------------------------

class EmbeddingRequest(BaseModel):
    """Request to generate embedding vectors."""
    texts: list[str]
    model: str | None = None  # Use backend default if not specified


class EmbeddingResponse(BaseModel):
    """Embedding vectors from a single embed call."""
    vectors: list[list[float]]
    dimensions: int
    model_name: str
    backend: str


# ---------------------------------------------------------------------------
# Engine Protocols
#
# Engines implement only the Protocols matching their actual capabilities.
# The type checker enforces this; no "universal engine" assumption.
# ---------------------------------------------------------------------------

@runtime_checkable
class ChatModel(Protocol):
    """Engine that can generate chat responses."""

    def get_capabilities(self) -> EngineCapabilities:
        """Report what this engine supports."""
        ...

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Generate a response from a conversation. Never returns plain str."""
        ...


@runtime_checkable
class ToolCallingModel(Protocol):
    """Engine that can decide to invoke tools during generation."""

    def generate_with_tools(
        self,
        request: GenerationRequest,
        available_tools: list["ToolSpec"],  # noqa: F821  (defined in contracts.tools)
    ) -> GenerationResponse:
        """Generate a response that may include ToolCall entries."""
        ...


@runtime_checkable
class EmbeddingModel(Protocol):
    """Engine that can produce embedding vectors."""

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Generate embedding vectors for a list of texts."""
        ...


@runtime_checkable
class StreamingModel(Protocol):
    """Engine that can stream responses token by token (synchronous)."""

    def stream(self, request: GenerationRequest) -> Iterator[str]:
        """Yield tokens as they are generated."""
        ...


@runtime_checkable
class AsyncStreamingModel(Protocol):
    """Engine that supports async streaming (required for FastAPI / asyncio contexts)."""

    async def stream_async(self, request: GenerationRequest) -> AsyncIterator[str]:
        """Async-yield tokens as they are generated."""
        ...


@runtime_checkable
class LogprobModel(Protocol):
    """Engine that can return per-token log probabilities (for surprise filter)."""

    def generate_with_logprobs(
        self,
        request: GenerationRequest,
        top_logprobs: int = 0,
    ) -> LogprobResult:
        """Generate text and return token-level log probabilities.
        
        top_logprobs=0: only the chosen token's logprob (cheapest).
        top_logprobs=N: N most-likely alternatives per position.
        Not available on AnthropicEngine (API does not expose logprobs).
        """
        ...


@runtime_checkable
class BatchChatModel(Protocol):
    """Engine that can process multiple requests in a single call."""

    def generate_batch(
        self,
        requests: list[GenerationRequest],
    ) -> list[GenerationResponse]:
        """Process a batch of requests. Returns responses in the same order."""
        ...


# ---------------------------------------------------------------------------
# Concrete engine declarations (capability composition)
#
# These classes document which protocols each backend implements.
# They contain no logic here; implementations live in llm_engines/backends/.
# ---------------------------------------------------------------------------

class OllamaEngine(ChatModel, ToolCallingModel, EmbeddingModel, StreamingModel, Protocol):
    """Ollama: chat, tool calling, embeddings, sync streaming."""
    pass


class AnthropicEngine(ChatModel, ToolCallingModel, AsyncStreamingModel, Protocol):
    """Anthropic: chat, tool calling, async streaming. No native embeddings."""
    pass


class OpenAIEngine(ChatModel, ToolCallingModel, EmbeddingModel, AsyncStreamingModel, Protocol):
    """OpenAI: chat, tool calling, embeddings, async streaming."""
    pass


class vLLMEngine(ChatModel, EmbeddingModel, AsyncStreamingModel, BatchChatModel, Protocol):
    """vLLM: chat, embeddings, async streaming, batch."""
    pass


class LlamaCppEngine(ChatModel, EmbeddingModel, StreamingModel, Protocol):
    """llama.cpp: chat, embeddings, sync streaming. No tool calling."""
    pass


class MockEngine(ChatModel, Protocol):
    """Mock engine for testing. Supports basic chat only."""
    pass
