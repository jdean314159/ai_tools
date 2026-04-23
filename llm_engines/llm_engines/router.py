"""
llm_engines/router.py

FailoverEngine: routes requests across multiple ChatModel engines in
priority order with circuit breaking and cloud data policy.

Ported from Engram's router.py and adapted to use contracts:
  - Engines are ChatModel Protocol (not LLMEngine ABC)
  - generate() accepts GenerationRequest / returns GenerationResponse
  - stream() and embed() delegate to the first healthy engine that
    implements the relevant Protocol

Design:
  primary -> local fallback -> optional cloud
  Circuit breaker per engine (N failures → cooldown)
  One short retry on transient errors before moving to next engine
  Cloud engines sanitise prompt if cloud_policy != "full_context"
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Iterator, Sequence

from llm_engines.contracts import (
    BackendUnavailableError,
    ChatMessage,
    ChatModel,
    EmbeddingModel,
    EmbeddingRequest,
    EmbeddingResponse,
    EngineCapabilities,
    GenerationError,
    GenerationRequest,
    GenerationResponse,
    ModelNotFoundError,
    StreamingModel,
    UsageStats,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FailoverPolicy:
    """Controls retry, fallback, and cloud data behaviour."""

    # Total attempts across all engines (not per-engine).
    max_attempts: int = 4

    # Reduce max_tokens before switching engines on OOM.
    reduce_output_on_oom: bool = True
    min_max_tokens: int = 256

    # One short retry on the same engine for transient network errors.
    transient_retry: bool = True
    transient_retry_backoff_s: float = 0.5

    # Circuit breaker: skip an engine after N consecutive failures.
    circuit_breaker_failures: int = 3
    circuit_breaker_cooldown_s: float = 30.0

    # Allow routing to engines flagged is_cloud=True.
    allow_cloud_failover: bool = False

    # Cloud data policy (applied when routing to a cloud engine):
    #   none              — disallow cloud usage
    #   query_only        — strip retrieved memory block
    #   query_plus_summary — replace memory block with compact summary
    #   full_context      — send full prompt unchanged
    cloud_policy: str = "query_plus_summary"


# ---------------------------------------------------------------------------
# Per-engine health tracker (circuit breaker state)
# ---------------------------------------------------------------------------

@dataclass
class _EngineHealth:
    failures: int = 0
    cooldown_until: float = 0.0

    def is_healthy(self) -> bool:
        return time.monotonic() >= self.cooldown_until

    def record_failure(self, policy: FailoverPolicy) -> None:
        self.failures += 1
        if self.failures >= policy.circuit_breaker_failures:
            self.cooldown_until = time.monotonic() + policy.circuit_breaker_cooldown_s
            self.failures = 0
            logger.warning("Engine circuit breaker tripped — cooldown %.0fs",
                           policy.circuit_breaker_cooldown_s)

    def record_success(self) -> None:
        self.failures = 0
        self.cooldown_until = 0.0


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

def _classify(e: Exception) -> str:
    msg = str(e).lower()
    if "context length" in msg or "maximum context" in msg or "too many tokens" in msg:
        return "context"
    if "out of memory" in msg or "cuda out of memory" in msg or "oom" in msg:
        return "oom"
    if ("timed out" in msg or "timeout" in msg
            or "connection" in msg or "unreachable" in msg):
        return "transient"
    if "not found" in msg or "no such" in msg:
        return "not_found"
    return "unknown"


# ---------------------------------------------------------------------------
# Cloud prompt sanitisation (minimal — no memory layer awareness here)
# ---------------------------------------------------------------------------

_MEMORY_BLOCK_MARKERS = [
    "--- retrieved context ---",
    "--- memory context ---",
    "[retrieved context]",
    "[memory]",
]


def _sanitise_for_cloud(request: GenerationRequest, policy: str) -> GenerationRequest:
    """
    Apply cloud data policy to a GenerationRequest.

    query_only / query_plus_summary: strip messages that look like
    retrieved memory blocks. full_context: pass through unchanged.
    """
    if policy == "full_context":
        return request

    filtered_messages = []
    for msg in request.messages:
        content = (msg.content or "").lower()
        is_memory_block = any(marker in content for marker in _MEMORY_BLOCK_MARKERS)
        if is_memory_block and policy in ("query_only", "query_plus_summary"):
            if policy == "query_plus_summary":
                # Replace with a short notice
                filtered_messages.append(ChatMessage(
                    role=msg.role,
                    content="[Retrieved memory context omitted for cloud privacy]"
                ))
            # query_only: drop entirely
        else:
            filtered_messages.append(msg)

    return request.model_copy(update={"messages": filtered_messages})


# ---------------------------------------------------------------------------
# FailoverEngine
# ---------------------------------------------------------------------------

class FailoverEngine:
    """
    ChatModel that routes across multiple engines in priority order.

    Usage:
        primary = OllamaEngine("qwen3:27b")
        fallback = OllamaEngine("qwen3:8b")
        engine = FailoverEngine([primary, fallback])
        response = engine.generate(request)

    The FailoverEngine itself implements ChatModel, EmbeddingModel (if any
    member does), and StreamingModel (if any member does). Capability
    reporting reflects the union of all member capabilities.
    """

    def __init__(
        self,
        engines: Sequence[ChatModel],
        policy: FailoverPolicy | None = None,
        name: str = "failover",
    ) -> None:
        if not engines:
            raise ValueError("FailoverEngine requires at least one engine")
        self.engines = list(engines)
        self.policy = policy or FailoverPolicy()
        self.name = name
        self._health: dict[int, _EngineHealth] = {
            i: _EngineHealth() for i in range(len(engines))
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_cloud(self, engine: ChatModel) -> bool:
        return bool(getattr(engine, "is_cloud", False))

    def _healthy_engines(self) -> list[tuple[int, ChatModel]]:
        """Return (index, engine) pairs that are healthy and eligible."""
        result = []
        for i, engine in enumerate(self.engines):
            if not self._health[i].is_healthy():
                continue
            if self._is_cloud(engine) and not self.policy.allow_cloud_failover:
                continue
            result.append((i, engine))
        return result

    def _apply_cloud_policy(
        self, engine: ChatModel, request: GenerationRequest
    ) -> GenerationRequest:
        if self._is_cloud(engine):
            return _sanitise_for_cloud(request, self.policy.cloud_policy)
        return request

    # ------------------------------------------------------------------
    # ChatModel Protocol
    # ------------------------------------------------------------------

    def get_capabilities(self) -> EngineCapabilities:
        """Union of capabilities across all member engines."""
        if not self.engines:
            return EngineCapabilities()
        caps_list = [e.get_capabilities() for e in self.engines]
        return EngineCapabilities(
            chat=any(c.chat for c in caps_list),
            streaming=any(c.streaming for c in caps_list),
            async_streaming=any(c.async_streaming for c in caps_list),
            tool_calling=any(c.tool_calling for c in caps_list),
            embeddings=any(c.embeddings for c in caps_list),
            structured_output=any(c.structured_output for c in caps_list),
            batch_generation=any(c.batch_generation for c in caps_list),
            vision=any(c.vision for c in caps_list),
            usage_reporting=any(c.usage_reporting for c in caps_list),
            logprobs=any(c.logprobs for c in caps_list),
        )

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """
        Generate with automatic failover.

        Tries each healthy engine in order. On OOM, reduces max_tokens and
        retries the SAME engine (up to max_attempts total). Does not trip the
        circuit breaker on OOM — the engine is healthy, the request was too
        large. On transient errors, retries the same engine once before moving
        on. All other errors move immediately to the next engine.
        """
        candidates = self._healthy_engines()
        if not candidates:
            raise GenerationError(
                f"All engines in circuit-breaker cooldown for '{self.name}'. "
                "Call reset_health() to clear, or wait for cooldown to expire. "
                f"Health: {self.health_report()}"
            )

        attempts = 0
        current_max_tokens = request.max_tokens
        last_error: Exception | None = None

        for idx, engine in candidates:
            model_label = getattr(engine, "model", str(idx))

            # Inner loop: allows OOM retries on the same engine with reduced tokens.
            while attempts < self.policy.max_attempts:
                effective_request = self._apply_cloud_policy(engine, request)
                if current_max_tokens != effective_request.max_tokens:
                    effective_request = effective_request.model_copy(
                        update={"max_tokens": current_max_tokens}
                    )

                try:
                    response = engine.generate(effective_request)
                    self._health[idx].record_success()
                    if len(self.engines) > 1:
                        response = response.model_copy(update={
                            "backend": f"{response.backend}[failover:{self.name}]"
                        })
                    return response

                except Exception as e:
                    attempts += 1
                    error_class = _classify(e)
                    last_error = e

                    if error_class == "transient" and self.policy.transient_retry:
                        logger.warning("Transient error on %s, retrying once: %s",
                                       model_label, e)
                        time.sleep(self.policy.transient_retry_backoff_s)
                        # One inline retry — if it fails, fall through to next engine
                        try:
                            response = engine.generate(effective_request)
                            self._health[idx].record_success()
                            return response
                        except Exception as e2:
                            attempts += 1
                            last_error = e2
                            self._health[idx].record_failure(self.policy)
                            logger.warning("Retry failed, moving to next engine: %s", e2)
                        break  # move to next engine

                    if error_class == "oom" and self.policy.reduce_output_on_oom:
                        reduced = max(
                            self.policy.min_max_tokens,
                            current_max_tokens // 2,
                        )
                        if reduced < current_max_tokens:
                            logger.warning("OOM on %s — reducing max_tokens %d→%d",
                                           model_label, current_max_tokens, reduced)
                            current_max_tokens = reduced
                            continue  # retry same engine with reduced tokens
                        # Already at minimum — give up on this engine
                        logger.warning("OOM on %s at minimum max_tokens, moving on",
                                       model_label)
                        break

                    # All other errors: trip circuit breaker and try next engine
                    self._health[idx].record_failure(self.policy)
                    logger.warning("Engine %s failed (%s), trying next: %s",
                                   model_label, error_class, e)
                    break  # exit inner while, advance to next engine

        raise GenerationError(
            f"All engines failed after {attempts} attempts. "
            f"Last error: {last_error}"
        ) from last_error

    # ------------------------------------------------------------------
    # EmbeddingModel delegation
    # ------------------------------------------------------------------

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Delegate to first healthy engine that supports embeddings."""
        for idx, engine in self._healthy_engines():
            if not isinstance(engine, EmbeddingModel):
                continue
            caps = engine.get_capabilities()
            if not caps.embeddings:
                continue
            try:
                result = engine.embed(request)
                self._health[idx].record_success()
                return result
            except Exception as e:
                self._health[idx].record_failure(self.policy)
                logger.warning("Embed failed on engine %d: %s", idx, e)
        raise GenerationError("No healthy engine supports embeddings")

    # ------------------------------------------------------------------
    # StreamingModel delegation
    # ------------------------------------------------------------------

    def stream(self, request: GenerationRequest) -> Iterator[str]:
        """Delegate to first healthy engine that supports streaming."""
        for idx, engine in self._healthy_engines():
            if not isinstance(engine, StreamingModel):
                continue
            caps = engine.get_capabilities()
            if not caps.streaming:
                continue
            effective_request = self._apply_cloud_policy(engine, request)
            try:
                yield from engine.stream(effective_request)
                self._health[idx].record_success()
                return
            except Exception as e:
                self._health[idx].record_failure(self.policy)
                logger.warning("Streaming failed on engine %d, falling back to generate(): %s",
                               idx, e)
                break
        # Fallback: use generate() and yield the full content at once
        response = self.generate(request)
        if response.message.content:
            yield response.message.content

    # ------------------------------------------------------------------
    # Introspection helpers (not part of any Protocol)
    # ------------------------------------------------------------------

    def health_report(self) -> dict[str, object]:
        """Return a dict of engine health states for monitoring."""
        return {
            getattr(self.engines[i], "model", str(i)): {
                "healthy": h.is_healthy(),
                "failures": h.failures,
                "cooldown_until": h.cooldown_until,
            }
            for i, h in self._health.items()
        }

    def reset_health(self) -> None:
        """Reset all circuit breakers. Useful after maintenance."""
        for h in self._health.values():
            h.record_success()
