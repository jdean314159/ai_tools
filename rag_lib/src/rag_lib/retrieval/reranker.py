"""
rag_lib.retrieval.reranker

Cross-encoder reranking for Stage 2 retrieval quality improvement.

D5: Two-stage retrieval — Stage 1 (hybrid BM25+dense) → Stage 2 (reranker).
D10: Reranker off by default; downloads from HuggingFace on first use.
     Enable via reranker.enabled: true in config.
     Pre-download with: python scripts/setup_models.py --reranker

Why cross-encoder vs bi-encoder:
    Bi-encoder (dense search): fast, approximate — encodes query and document
    independently. Good for Stage 1 candidate retrieval at scale.

    Cross-encoder: slower, precise — encodes query+document as a pair.
    Sees the full interaction between query terms and document content.
    Produces a single relevance score that's significantly more accurate
    for final ranking. Runs comfortably on RTX 3090.
"""

from __future__ import annotations

import logging
from typing import Any

from ..errors import RerankerError
from ..storage.base import StoredChunk

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class CrossEncoderReranker:
    """Rerank retrieved chunks using a cross-encoder model.

    Lazy-loads sentence_transformers on first call — import cost is not paid
    at startup, and the reranker can be disabled without the dependency
    being installed.

    Args:
        model:   HuggingFace model name. Default is ms-marco-MiniLM-L-6-v2,
                 which runs on CPU and GPU and is optimised for passage ranking.
        device:  'auto' selects CUDA if available, else CPU.
                 'cpu' forces CPU (slower but always works).
                 'cuda' forces CUDA (raises if not available).
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        device: str = "auto",
    ) -> None:
        self._model_name = model
        self._device = device
        self._model: Any = None  # lazy-loaded

    def rerank(
        self,
        query: str,
        chunks: list[StoredChunk],
        k: int = 5,
    ) -> list[StoredChunk]:
        """Score query+chunk pairs and return top-k chunks by cross-encoder score.

        Args:
            query:  The user query.
            chunks: Candidate chunks from Stage 1 retrieval (BM25+dense).
            k:      Number of chunks to return.

        Returns:
            Up to k chunks sorted by cross-encoder relevance score (descending).
            The StoredChunk.score field is updated to the cross-encoder score.

        Raises:
            RerankerError: If the model cannot be loaded.
        """
        if not chunks:
            return []

        model = self._get_model()
        pairs = [[query, chunk.context_text] for chunk in chunks]

        try:
            scores = model.predict(pairs)
        except Exception as exc:
            raise RerankerError(f"CrossEncoder prediction failed: {exc}") from exc

        # Pair chunks with scores, sort descending, return top k
        scored = sorted(
            zip(chunks, scores),
            key=lambda x: float(x[1]),
            reverse=True,
        )

        result: list[StoredChunk] = []
        for chunk, score in scored[:k]:
            # Update score to reflect cross-encoder relevance
            # Use a new StoredChunk with updated score (dataclass is not frozen)
            from dataclasses import replace

            try:
                result.append(replace(chunk, score=round(float(score), 4)))
            except TypeError:
                # replace() may not work if chunk has unexpected fields
                chunk.score = round(float(score), 4)
                result.append(chunk)

        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_model(self) -> Any:
        """Lazy-load CrossEncoder. Raises RerankerError with actionable message."""
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RerankerError(
                "sentence-transformers required for reranking: "
                "pip install rag-lib[rerank]\n"
                "Then pre-download the model: "
                "python scripts/setup_models.py --reranker"
            ) from exc

        device = self._resolve_device()

        try:
            logger.info(
                "Loading CrossEncoder '%s' on %s (first use)...",
                self._model_name,
                device,
            )
            self._model = CrossEncoder(self._model_name, device=device)
            logger.info("CrossEncoder loaded.")
        except Exception as exc:
            cache = "~/.cache/huggingface/hub/"
            model_dir = f"models--{self._model_name.replace('/', '--')}"
            raise RerankerError(
                f"Cannot load CrossEncoder '{self._model_name}': {exc}\n"
                "If this is an air-gapped machine, pre-download the model:\n"
                f"  python scripts/setup_models.py --reranker\n"
                f"Or manually copy the model to: {cache}{model_dir}/"
            ) from exc

        return self._model

    def _resolve_device(self) -> str:
        if self._device == "cpu":
            return "cpu"
        if self._device == "cuda":
            return "cuda"
        # auto
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"
