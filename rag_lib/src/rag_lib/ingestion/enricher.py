"""
rag_lib.ingestion.enricher

Contextual chunk enrichment: prepend a document-aware description to each
chunk's embed_text before vectorisation.

Motivation: A chunk like "the users in our role groups, their flow data was
sampled at regular intervals" is ambiguous without document context. Prepending
"This passage is from the Results chapter of a dissertation on NetFlow-based
user behavioral profiling, describing the data sampling methodology." places
the embedding precisely in the correct vector-space region.

The description is prepended to chunk.text → stored as chunk.embed_text.
  - embed_text goes to the embedder (improved vector placement)
  - text is unchanged (BM25 indexes this; no vocabulary noise from descriptions)
  - context_text is unchanged (LLM sees original content)

D14: Enrichment result cached by chunk_id — re-ingest of unchanged chunks
     skips the LLM call entirely.

Providers:
  - ollama:    local Qwen3:8b (default). No API cost. ~1-2s per chunk.
  - anthropic: Claude Haiku. High quality. ~$0.001 per chunk at 161 chunks ≈ $0.16.
  - openai:    GPT-4o-mini. Comparable to Haiku.

Config (rag_lib.yaml):
    enricher:
      enabled: false
      provider: ollama
      model: qwen3:8b
      host: http://localhost:11434      # Ollama only
      api_key_env: ANTHROPIC_API_KEY   # cloud providers
      timeout: 30
      keep_alive: 60
      max_context_chars: 1000
      batch_size: 1                    # Ollama: 1; cloud APIs: 8+
      cache: true
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
Document title: {title}
Document type: {doc_type}
Position: chunk {n} of {total}
Document introduction (first {intro_chars} characters):
{intro}

Write ONE sentence (20-40 words) describing what the following passage is \
about and where it fits within this document. Be specific to the actual \
content — avoid generic phrases like "this passage discusses".

Passage:
{chunk_text}

Description:"""


class ContextualEnricher:
    """Generate and prepend document-context descriptions to chunk embed_text.

    Args:
        provider:       'ollama' | 'anthropic' | 'openai'
        model:          Model identifier for the chosen provider.
        host:           Ollama server URL (Ollama only).
        api_key_env:    Environment variable name holding the API key (cloud).
        timeout:        Request timeout in seconds.
        keep_alive:     Ollama keep_alive seconds (short — only needed at ingest).
        max_context_chars: Characters of document intro to include in prompt.
        batch_size:     Parallel calls (Ollama: 1; cloud: 8+).
        cache:          If True, skip enrichment for chunks with unchanged chunk_id.
        max_embed_tokens: Hard ceiling on embed_text word count after enrichment.
    """

    def __init__(
        self,
        provider: str = "ollama",
        model: str = "qwen3:8b",
        host: str = "http://localhost:11434",
        api_key_env: str = "ANTHROPIC_API_KEY",
        timeout: int = 30,
        keep_alive: int = 60,
        max_context_chars: int = 1000,
        batch_size: int = 1,
        cache: bool = True,
        max_embed_tokens: int = 1800,
    ) -> None:
        self._provider = provider.lower()
        self._model = model
        self._host = host.rstrip("/")
        self._api_key_env = api_key_env
        self._timeout = timeout
        self._keep_alive = keep_alive
        self._max_context_chars = max_context_chars
        self._batch_size = batch_size
        self._cache = cache
        self._max_embed_tokens = max_embed_tokens
        self._cache_store: dict[str, str] = {}  # chunk_id → description

        # Validate provider
        if self._provider not in ("ollama", "anthropic", "openai"):
            raise ValueError(
                f"Unknown enricher provider '{provider}'. "
                "Use: ollama | anthropic | openai"
            )

        # Validate cloud API key availability
        if self._provider in ("anthropic", "openai"):
            if not os.environ.get(api_key_env):
                raise ValueError(
                    f"Enricher provider '{provider}' requires {api_key_env} "
                    f"to be set in the environment."
                )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enrich(
        self,
        chunks: list[Any],          # list[TextChunk]
        doc_title: str = "",
        doc_type: str = "unknown",
        doc_intro: str = "",
        file_hash: str = "",
    ) -> list[Any]:
        """Enrich a list of TextChunks by setting embed_text on each.

        Args:
            chunks:     TextChunks from the chunker. Modified in-place.
            doc_title:  Document filename or title for the prompt.
            doc_type:   Document type (thesis, paper, policy, etc.)
            doc_intro:  First N characters of the document (provides context).
            file_hash:  Used for cache key construction.

        Returns:
            The same chunks list with embed_text set on each chunk.
        """
        if not chunks:
            return chunks

        total = len(chunks)
        intro = doc_intro[:self._max_context_chars]
        skipped = 0
        enriched = 0
        errors = 0

        for chunk in chunks:
            cid = chunk.chunk_id(file_hash) if file_hash else chunk.source_id

            # Cache hit: skip LLM call
            if self._cache and cid in self._cache_store:
                description = self._cache_store[cid]
                chunk.embed_text = self._build_embed_text(description, chunk.text)
                skipped += 1
                continue

            # Generate description
            prompt = _PROMPT_TEMPLATE.format(
                title=doc_title or chunk.source_id.rsplit(":", 1)[0],
                doc_type=doc_type,
                n=chunk.chunk_index + 1,
                total=total,
                intro_chars=self._max_context_chars,
                intro=intro or "[not available]",
                chunk_text=chunk.text[:800],  # cap chunk in prompt
            )

            description = self._generate(prompt)

            if description:
                embed = self._build_embed_text(description, chunk.text)
                # Enforce max_embed_tokens — truncate description if needed
                if len(embed.split()) > self._max_embed_tokens:
                    # Fall back to just the chunk text
                    logger.warning(
                        "Enriched embed_text exceeds max_embed_tokens for chunk %s; "
                        "using plain text.",
                        chunk.source_id,
                    )
                    chunk.embed_text = chunk.text
                else:
                    chunk.embed_text = embed
                    if self._cache:
                        self._cache_store[cid] = description
                enriched += 1
            else:
                # Generation failed — embed_text stays as text (set by __post_init__)
                chunk.embed_text = chunk.text
                errors += 1

        logger.info(
            "Enrichment complete: %d enriched, %d cache hits, %d errors (total %d)",
            enriched, skipped, errors, total,
        )
        return chunks

    def clear_cache(self) -> None:
        self._cache_store.clear()

    @property
    def cache_size(self) -> int:
        return len(self._cache_store)

    # ------------------------------------------------------------------
    # Prompt dispatch
    # ------------------------------------------------------------------

    def _generate(self, prompt: str) -> str:
        """Call the configured provider and return the description string."""
        try:
            if self._provider == "ollama":
                return self._generate_ollama(prompt)
            elif self._provider == "anthropic":
                return self._generate_anthropic(prompt)
            elif self._provider == "openai":
                return self._generate_openai(prompt)
        except Exception as exc:
            logger.debug("Enricher generation failed: %s", exc)
        return ""

    def _generate_ollama(self, prompt: str) -> str:
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": self._keep_alive,
            "options": {
                "temperature": 0.1,
                "num_predict": 80,      # description is 20-40 words; cap tokens
                "stop": ["\n\n", "Passage:", "Document:"],
            },
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self._host}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return self._clean(result.get("response", ""))

    def _generate_anthropic(self, prompt: str) -> str:
        api_key = os.environ.get(self._api_key_env, "")
        payload = {
            "model": self._model,
            "max_tokens": 80,
            "temperature": 0.1,
            "messages": [{"role": "user", "content": prompt}],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=data,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        content = result.get("content", [])
        if content and content[0].get("type") == "text":
            return self._clean(content[0]["text"])
        return ""

    def _generate_openai(self, prompt: str) -> str:
        api_key = os.environ.get(self._api_key_env, "")
        payload = {
            "model": self._model,
            "max_tokens": 80,
            "temperature": 0.1,
            "messages": [{"role": "user", "content": prompt}],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        choices = result.get("choices", [])
        if choices:
            return self._clean(choices[0]["message"]["content"])
        return ""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_embed_text(self, description: str, chunk_text: str) -> str:
        """Combine description and chunk text into the embed_text string."""
        description = description.strip().rstrip(".")
        return f"{description}. {chunk_text}"

    @staticmethod
    def _clean(text: str) -> str:
        """Strip whitespace, markdown fences, and leading labels."""
        text = text.strip()
        # Remove markdown code fences if model wraps output
        if text.startswith("```"):
            text = text.split("```")[1].strip()
        # Remove common leading labels models add
        for prefix in ("Description:", "Context:", "Summary:", "Answer:"):
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        # Take first sentence only if model over-generates
        # (stop tokens should prevent this but be safe)
        if "\n" in text:
            text = text.split("\n")[0].strip()
        return text
