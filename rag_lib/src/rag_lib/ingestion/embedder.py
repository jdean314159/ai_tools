"""
rag_lib.ingestion.embedder

Ollama embedding via raw urllib — no llm_engines import required.
Mirrors OllamaEngine._post_json() exactly for consistency.

D3: No llm_engines dependency in rag_lib core.
D7: validate_tokens enforces that text (not context_text) is being embedded.
D15: keep_alive passed in every request to prevent model-switch latency.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from ..errors import EmbedderError

logger = logging.getLogger(__name__)


class OllamaEmbedder:
    """Embed texts via Ollama /api/embed endpoint.

    Args:
        host:             Ollama server URL (default: http://localhost:11434)
        model:            Embedding model tag
        timeout:          Request timeout in seconds
        batch_size:       Max texts per request
        keep_alive:       Seconds to keep model loaded after last request.
                          Set to 600 (10 min) during ingestion to prevent
                          model-switch latency when processing large directories.
        max_embed_tokens: Hard ceiling on input token count. EmbedderError is
                          raised if any text exceeds this. Guards against the
                          context_text / text confusion (D7).
        doc_prefix:       Instruction prefix for document embeddings.
                          nomic-embed-text requires "search_document:" for
                          asymmetric retrieval (query vs passage). Without this,
                          query and document embeddings land in different vector
                          space regions and cosine similarity is near zero.
        query_prefix:     Instruction prefix for query embeddings.
    """

    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "nomic-embed-text-v2-moe",
        timeout: int = 120,
        batch_size: int = 32,
        keep_alive: int = 600,
        max_embed_tokens: int = 1800,
        doc_prefix: str = "search_document: ",
        query_prefix: str = "search_query: ",
    ) -> None:
        self._host = host.rstrip("/")
        self.model = model
        self._timeout = timeout
        self._batch_size = batch_size
        self._keep_alive = keep_alive
        self._max_embed_tokens = max_embed_tokens
        self._doc_prefix = doc_prefix
        self._query_prefix = query_prefix

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed(
        self,
        texts: list[str],
        *,
        validate_tokens: bool = True,
    ) -> list[list[float]]:
        """Embed a list of texts. Returns one vector per text.

        Args:
            texts:           Texts to embed. Must be chunk.text, NOT chunk.context_text.
            validate_tokens: If True, raises EmbedderError for texts exceeding
                             max_embed_tokens. Disable only for testing.
        """
        if not texts:
            return []

        if validate_tokens:
            for i, t in enumerate(texts):
                word_count = len(t.split())
                if word_count > self._max_embed_tokens:
                    raise EmbedderError(
                        f"Text at index {i} exceeds max_embed_tokens "
                        f"({word_count} words > {self._max_embed_tokens}). "
                        "Ensure chunk.text (not chunk.context_text) is passed to the embedder. "
                        "Reduce chunker.max_embed_tokens or the chunk strategy's size parameters."
                    )

        # Apply document prefix for asymmetric retrieval alignment.
        # nomic-embed-text requires "search_document:" for passages and
        # "search_query:" for queries. Without these, query and document
        # embeddings land in different vector space regions, producing
        # near-zero cosine similarity even for relevant content.
        prefixed = [f"{self._doc_prefix}{t}" for t in texts]

        vectors: list[list[float]] = []
        for i in range(0, len(prefixed), self._batch_size):
            batch = prefixed[i : i + self._batch_size]
            batch_vectors = self._embed_batch(batch)
            vectors.extend(batch_vectors)

        return vectors

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string with query instruction prefix."""
        prefixed = f"{self._query_prefix}{text}"
        result = self._embed_batch([prefixed])
        return result[0] if result else []

    def dimensions(self) -> int:
        """Return the embedding dimension by embedding a probe string."""
        probe = self.embed_query("probe")
        return len(probe)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _embed_batch(
        self,
        texts: list[str],
        validate: bool = True,
    ) -> list[list[float]]:
        payload: dict[str, Any] = {
            "model": self.model,
            "input": texts,
            "keep_alive": self._keep_alive,
        }
        try:
            result = self._post_json("/api/embed", payload)
        except EmbedderError:
            raise
        except Exception as exc:
            raise EmbedderError(
                f"Unexpected error calling Ollama embed: {exc}"
            ) from exc

        vectors = result.get("embeddings", [])
        if len(vectors) != len(texts):
            raise EmbedderError(
                f"Ollama returned {len(vectors)} vectors for {len(texts)} texts. "
                "This may indicate a model loading failure."
            )
        return vectors

    def _post_json(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST JSON to Ollama endpoint. Mirrors OllamaEngine._post_json()."""
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self._host}{endpoint}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                pass
            raise EmbedderError(
                f"Ollama HTTP {exc.code} on {endpoint}: {body}. "
                f"Ensure model '{self.model}' is pulled: ollama pull {self.model}"
            ) from exc
        except urllib.error.URLError as exc:
            raise EmbedderError(
                f"Cannot reach Ollama at {self._host}: {exc.reason}. "
                "Is Ollama running? Start with: ollama serve"
            ) from exc
