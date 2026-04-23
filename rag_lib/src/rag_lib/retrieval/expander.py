"""
rag_lib.retrieval.expander

Query expansion via local LLM. Generates synonym, specific, and related
variants of a query to improve recall for vague or imprecise queries.

D19: Off by default (adds 1-3s LLM latency per query).
     Results cached via LRU cache (configurable size).
     Enable via expander.enabled: true in config.

Usage (when enabled in pipeline):
    expander = QueryExpander(
        host="http://localhost:11434",
        model="qwen3:8b",
        cache_size=256,
    )
    expanded = expander.expand("how does clustering work in the dissertation")
    # Returns: [original_query, variant1, variant2, variant3]
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)


class QueryExpander:
    """Expand a query into 3 semantically related variants via local LLM.

    Args:
        host:       Ollama server URL.
        model:      Local LLM model for expansion (small/fast preferred).
        cache_size: LRU cache entries. Repeated identical queries skip the LLM.
        timeout:    Request timeout in seconds.
    """

    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "qwen3:8b",
        cache_size: int = 256,
        timeout: int = 30,
    ) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._timeout = timeout
        # Use a module-level cache keyed by (model, query)
        self._cache: dict[str, list[str]] = {}
        self._cache_size = cache_size

    def expand(self, query: str) -> list[str]:
        """Return [original_query, variant1, variant2, variant3].

        Falls back to [original_query] on any failure so retrieval is
        never blocked by expander errors.
        """
        cache_key = f"{self._model}::{query}"
        if cache_key in self._cache:
            logger.debug("Query expansion cache hit for: %s", query[:60])
            return self._cache[cache_key]

        variants = self._generate_variants(query)
        result = [query] + variants

        # Evict oldest if cache is full
        if len(self._cache) >= self._cache_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        self._cache[cache_key] = result

        return result

    def _generate_variants(self, query: str) -> list[str]:
        """Call Ollama to generate 3 query variants. Returns [] on failure."""
        prompt = (
            f"Generate exactly 3 alternative search queries for the following query. "
            f"Each variant should find relevant information using different wording:\n"
            f"1. A synonym variant (same meaning, different words)\n"
            f"2. A specific variant (more concrete or detailed)\n"
            f"3. A related concept variant (broader or narrower context)\n\n"
            f"Original query: {query}\n\n"
            f"Respond with ONLY a JSON array of exactly 3 strings. "
            f"No explanation, no markdown, just the JSON array.\n"
            f'Example: ["variant one", "variant two", "variant three"]'
        )

        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 200},
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self._host}/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                text = result.get("response", "").strip()

            # Parse JSON array from response
            # Handle cases where model wraps in markdown
            if "```" in text:
                start = text.find("[")
                end = text.rfind("]") + 1
                if start >= 0 and end > start:
                    text = text[start:end]

            variants = json.loads(text)
            if isinstance(variants, list) and len(variants) >= 1:
                # Take up to 3, ensure strings
                return [str(v) for v in variants[:3] if v]

        except (urllib.error.URLError, json.JSONDecodeError, Exception) as exc:
            logger.debug("Query expansion failed for '%s': %s", query[:60], exc)

        return []

    @property
    def cache_size(self) -> int:
        return len(self._cache)

    def clear_cache(self) -> None:
        self._cache.clear()
