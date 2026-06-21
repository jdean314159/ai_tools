"""
llm_engines/token_counter.py

Token counting utility used by OllamaEngine, FailoverEngine, and
the prompt compression helper.

Uses tiktoken (cl100k_base, GPT-4/Claude-compatible) when available,
falls back to len//4 approximation.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_ENCODER: Any = None
try:
    import tiktoken as _tiktoken
    _ENCODER = _tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        """Count tokens using cl100k_base. ~±10% accuracy for most models."""
        return len(_ENCODER.encode(text))

except Exception as exc:
    logger.debug("tiktoken unavailable (%s) — using len//4 token approximation", exc)
    def count_tokens(text: str) -> int:
        """Fallback: ~4 chars per token. Rough but dependency-free."""
        return max(1, len(text) // 4)


def compress_prompt(
    text: str,
    target_tokens: int,
    strategy: str = "truncate_end",
) -> str:
    """
    Truncate text to approximately target_tokens.

    Args:
        text:          Input text.
        target_tokens: Target token budget.
        strategy:      "truncate_start" | "truncate_end"

    Note: Model-based compression (summarisation) is intentionally not
    implemented here to avoid circular engine dependencies. Use
    FailoverEngine.compress_with_model() if you need that.
    """
    current = count_tokens(text)
    if current <= target_tokens:
        return text
    ratio = target_tokens / max(current, 1)
    keep_chars = int(len(text) * ratio)
    if strategy == "truncate_start":
        return text[-keep_chars:]
    return text[:keep_chars]
