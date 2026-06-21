"""
llm_engines/strategies/propose_then_verify.py

ProposeThenVerifyEngine: draft model generates N candidates, verifier selects best.

This is NOT token-level speculative decoding (which requires shared logits and
runs inside the inference engine — vLLM supports that natively via
--speculative-model). This operates at the response level.

When to use:
  - You have a fast, cheap draft model and a slower, better verifier
  - Quality matters more than throughput
  - The draft model is small enough that N parallel calls are cheap
  - Cloud APIs where you want to avoid expensive large-model retries

When NOT to use:
  - You want raw speed on local inference (more total compute, not less)
  - Both models are similarly sized
  - Use vLLM's --speculative-model flag instead for true token-level speedup

Speedup profile:
  Total cost ≈ (N × draft_cost) + verify_cost
  vs. baseline ≈ large_model_cost

  Worthwhile when: draft_cost × N < large_model_cost AND quality improves.
  Typical ratio: 7B draft × 3 candidates vs. 32B verifier → ~2x cheaper, better quality.
"""
from __future__ import annotations

import concurrent.futures
import logging
import time
from typing import Any

from llm_engines.contracts import (
    ChatMessage,
    ChatModel,
    EngineCapabilities,
    GenerationError,
    GenerationRequest,
    GenerationResponse,
    UsageStats,
)

logger = logging.getLogger(__name__)

_SELECT_SYSTEM = (
    "You are an expert evaluator. You will be shown several candidate responses "
    "to a question. Select the single best response — most accurate, clear, and "
    "complete. Output ONLY the selected response verbatim, with no preamble, "
    "commentary, or explanation."
)

_SELECT_PROMPT_TEMPLATE = """\
Original question:
{query}

Candidate responses:
{candidates}

Select and reproduce the best response verbatim:"""


class ProposeThenVerifyEngine:
    """
    A ChatModel wrapper that uses a draft/verify two-stage generation strategy.

    Args:
        draft:      Fast ChatModel for generating candidate responses.
        verifier:   Better ChatModel for selecting the best candidate.
        n_drafts:   Number of candidates to generate. 3 is a good default;
                    diminishing returns above 5.
        temperature: Draft generation temperature. Higher = more diverse
                     candidates; lower = more similar (wastes the diversity).
                     Default 0.8.
        parallel:   Generate drafts in parallel threads. Almost always True.
                    Set False for debugging or when thread safety is a concern.
    """

    def __init__(
        self,
        draft: ChatModel,
        verifier: ChatModel,
        n_drafts: int = 3,
        temperature: float = 0.8,
        parallel: bool = True,
    ) -> None:
        if n_drafts < 1:
            raise ValueError("n_drafts must be >= 1")
        self.draft = draft
        self.verifier = verifier
        self.n_drafts = n_drafts
        self.temperature = temperature
        self.parallel = parallel

    # ------------------------------------------------------------------
    # ChatModel Protocol
    # ------------------------------------------------------------------

    def get_capabilities(self) -> EngineCapabilities:
        # Expose the verifier's capabilities as the engine's capabilities.
        return self.verifier.get_capabilities()

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """
        1. Generate n_drafts candidates from the draft model (optionally parallel).
        2. Ask the verifier to select the best candidate.
        3. Return a GenerationResponse with the selected content and combined usage.
        """
        if not request.messages:
            raise GenerationError("messages list cannot be empty")

        t0 = time.perf_counter()

        # Stage 1: Generate candidates
        draft_request = request.model_copy(update={"temperature": self.temperature})
        candidates = self._generate_candidates(draft_request)

        if not candidates:
            raise GenerationError("All draft candidates failed — cannot proceed to verify stage")

        # Stage 2: If only one candidate (n_drafts=1 or all but one failed), skip selection
        if len(candidates) == 1:
            selected_content = candidates[0].message.content or ""
            verify_usage = UsageStats()
        else:
            selected_content, verify_usage = self._select_best(request, candidates)

        total_latency = (time.perf_counter() - t0) * 1000

        # Aggregate usage across all draft calls + verify call
        total_input = sum(
            (r.usage.input_tokens or 0) for r in candidates
        ) + (verify_usage.input_tokens or 0)
        total_output = sum(
            (r.usage.output_tokens or 0) for r in candidates
        ) + (verify_usage.output_tokens or 0)

        return GenerationResponse(
            message=ChatMessage(role="assistant", content=selected_content),
            finish_reason="stop",
            usage=UsageStats(
                input_tokens=total_input,
                output_tokens=total_output,
                total_tokens=total_input + total_output,
                latency_ms=round(total_latency, 3),
            ),
            model_name=(
                f"propose_then_verify("
                f"draft={getattr(self.draft, 'model', 'draft')}×{self.n_drafts},"
                f"verify={getattr(self.verifier, 'model', 'verify')})"
            ),
            backend="propose_then_verify",
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _generate_candidates(self, request: GenerationRequest) -> list[GenerationResponse]:
        """Generate n_drafts candidates, in parallel if enabled."""
        if self.parallel and self.n_drafts > 1:
            return self._generate_parallel(request)
        return self._generate_serial(request)

    def _generate_serial(self, request: GenerationRequest) -> list[GenerationResponse]:
        results = []
        for i in range(self.n_drafts):
            try:
                resp = self.draft.generate(request)
                results.append(resp)
                logger.debug("Draft %d/%d: %d tokens", i + 1, self.n_drafts,
                             resp.usage.output_tokens or 0)
            except Exception as e:
                logger.warning("Draft %d/%d failed: %s", i + 1, self.n_drafts, e)
        return results

    def _generate_parallel(self, request: GenerationRequest) -> list[GenerationResponse]:
        results: list[GenerationResponse] = []
        errors: list[Exception] = []

        def _call(_: int) -> GenerationResponse:
            return self.draft.generate(request)

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.n_drafts) as pool:
            futures = {pool.submit(_call, i): i for i in range(self.n_drafts)}
            for future in concurrent.futures.as_completed(futures):
                idx = futures[future]
                try:
                    results.append(future.result())
                    logger.debug("Draft %d complete", idx + 1)
                except Exception as e:
                    logger.warning("Draft %d failed: %s", idx + 1, e)
                    errors.append(e)

        if not results:
            raise GenerationError(
                f"All {self.n_drafts} draft candidates failed. "
                f"Errors: {[str(e) for e in errors]}"
            )
        return results

    def _select_best(
        self,
        original_request: GenerationRequest,
        candidates: list[GenerationResponse],
    ) -> tuple[str, UsageStats]:
        """Ask the verifier to select the best candidate."""
        # Extract the original user query for context
        user_query = next(
            (m.content for m in reversed(original_request.messages) if m.role == "user"),
            "(no user message)",
        )

        # Format candidates for the verifier
        formatted = "\n\n".join(
            f"[Candidate {i + 1}]\n{r.message.content or '(empty)'}"
            for i, r in enumerate(candidates)
        )

        select_prompt = _SELECT_PROMPT_TEMPLATE.format(
            query=user_query,
            candidates=formatted,
        )

        verify_request = GenerationRequest(
            messages=[
                ChatMessage(role="system", content=_SELECT_SYSTEM),
                ChatMessage(role="user", content=select_prompt),
            ],
            max_tokens=original_request.max_tokens,
            temperature=0.0,  # deterministic selection
        )

        try:
            verify_resp = self.verifier.generate(verify_request)
            content = verify_resp.message.content or ""
            logger.debug(
                "Verifier selected from %d candidates (%d verify tokens)",
                len(candidates),
                verify_resp.usage.output_tokens or 0,
            )
            return content, verify_resp.usage
        except Exception as e:
            # Verifier failed — fall back to the first candidate
            logger.warning("Verifier selection failed (%s) — using first candidate", e)
            return candidates[0].message.content or "", UsageStats()
