"""
rag_lib.ingestion.chunker

Document-type-aware chunking. Implements all four strategies and dispatches
based on doc_type metadata set at load time.

D1: No LlamaIndex dependency. All strategies implemented natively.
D4: Strategy selected by doc_type; all four implemented from Phase 1.
D7: TextChunk.text (embedded) vs context_text (sent to LLM) are distinct.
D17: NLTK punkt tokenizer for sentence splitting; regex fallback if absent.
D18: Semantic chunking cost bounded by semantic_max_sentences.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from ..errors import ChunkerError

logger = logging.getLogger(__name__)


@dataclass
class TextChunk:
    """A single chunk ready for embedding and storage.

    Three distinct text roles (D7 + contextual enrichment):
        text         — original chunk content. Used for BM25 index and as
                       context_text fallback. Never modified after chunking.
        context_text — expanded context sent to the LLM (window/parent section).
        embed_text   — text actually passed to the embedding model. Defaults to
                       text; replaced with contextually enriched version when the
                       enricher is enabled. Contains a one-sentence document
                       description prepended to text to improve vector placement.

    Invariant: embed_text must not exceed max_embed_tokens.
    BM25 always indexes text (not embed_text) to avoid description vocabulary noise.
    """
    text: str
    context_text: str
    source_id: str          # "{file_path}:{chunk_index}"
    doc_type: str
    chunk_index: int
    metadata: dict[str, Any] = field(default_factory=dict)
    embed_text: str = ""    # set by enricher; falls back to text if empty

    def __post_init__(self) -> None:
        # Default embed_text to text if not explicitly set
        if not self.embed_text:
            self.embed_text = self.text

    def chunk_id(self, file_hash: str) -> str:
        """Deterministic ID for deduplication (D14)."""
        key = f"{self.source_id}:{file_hash}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Sentence splitting (D17)
# ---------------------------------------------------------------------------

def _sentences(text: str) -> list[str]:
    """Split text into sentences using NLTK punkt, with regex fallback."""
    try:
        from nltk.tokenize import sent_tokenize
        return [s.strip() for s in sent_tokenize(text) if s.strip()]
    except Exception:
        logger.warning(
            "NLTK punkt unavailable; using regex sentence splitter. "
            "Run: python -m nltk.downloader punkt_tab"
        )
        parts = re.split(r'(?<=[.!?])\s+', text.strip())
        return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# Strategy implementations
# ---------------------------------------------------------------------------

def _sentence_window(
    text: str,
    source_path: str,
    doc_type: str,
    *,
    window_size: int = 3,
    start_index: int = 0,
) -> list[TextChunk]:
    """Sentence-window chunking.

    Each chunk embeds one sentence (precise retrieval).
    context_text expands to window_size sentences on each side (LLM context).
    """
    sentences = _sentences(text)
    if not sentences:
        return []

    chunks: list[TextChunk] = []
    for i, sent in enumerate(sentences):
        lo = max(0, i - window_size)
        hi = min(len(sentences), i + window_size + 1)
        window = " ".join(sentences[lo:hi])

        idx = start_index + i
        chunks.append(TextChunk(
            text=sent,
            context_text=window,
            source_id=f"{source_path}:{idx}",
            doc_type=doc_type,
            chunk_index=idx,
            metadata={
                "strategy": "sentence_window",
                "window_size": window_size,
                "sentence_index": i,
                "total_sentences": len(sentences),
            },
        ))
    return chunks


def _fixed_size(
    text: str,
    source_path: str,
    doc_type: str,
    *,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    start_index: int = 0,
) -> list[TextChunk]:
    """Fixed-size token-approximate chunking with overlap.

    Uses word count as token approximation (1 word ≈ 1.3 tokens).
    """
    words = text.split()
    if not words:
        return []

    chunks: list[TextChunk] = []
    step = max(1, chunk_size - chunk_overlap)
    i = 0
    chunk_num = 0
    while i < len(words):
        window_words = words[i : i + chunk_size]
        chunk_text = " ".join(window_words)
        idx = start_index + chunk_num
        chunks.append(TextChunk(
            text=chunk_text,
            context_text=chunk_text,
            source_id=f"{source_path}:{idx}",
            doc_type=doc_type,
            chunk_index=idx,
            metadata={
                "strategy": "fixed_size",
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
                "word_offset": i,
            },
        ))
        i += step
        chunk_num += 1

    return chunks


def _hierarchical(
    text: str,
    source_path: str,
    doc_type: str,
    *,
    chunk_sizes: list[int] | None = None,
    start_index: int = 0,
) -> list[TextChunk]:
    """Hierarchical chunking: leaf nodes embedded, parent context returned.

    chunk_sizes: [large, medium, small] token counts for each level.
    Leaf nodes (smallest chunks) are what gets embedded.
    context_text is the parent-level chunk that contains the leaf.

    D7: text = leaf (small, precise); context_text = parent section (larger).
    """
    if chunk_sizes is None:
        chunk_sizes = [2048, 512, 128]

    if len(chunk_sizes) < 2:
        # Fall back to fixed-size if no meaningful hierarchy
        return _fixed_size(
            text, source_path, doc_type,
            chunk_size=chunk_sizes[0] if chunk_sizes else 512,
            start_index=start_index,
        )

    large_size, medium_size, leaf_size = (
        chunk_sizes[0],
        chunk_sizes[1] if len(chunk_sizes) > 1 else chunk_sizes[0] // 4,
        chunk_sizes[-1],
    )

    words = text.split()
    if not words:
        return []

    chunks: list[TextChunk] = []
    chunk_num = 0

    # Iterate over large (page-level) windows
    large_step = max(1, large_size)
    for large_start in range(0, len(words), large_step):
        large_words = words[large_start : large_start + large_size]
        large_text = " ".join(large_words)

        # Within each large block, iterate over medium (section-level) windows
        medium_step = max(1, medium_size)
        for med_offset in range(0, len(large_words), medium_step):
            medium_words = large_words[med_offset : med_offset + medium_size]
            medium_text = " ".join(medium_words)

            # Within each medium block, create leaf (paragraph-level) chunks
            leaf_step = max(1, leaf_size)
            for leaf_offset in range(0, len(medium_words), leaf_step):
                leaf_words = medium_words[leaf_offset : leaf_offset + leaf_size]
                if not leaf_words:
                    continue
                leaf_text = " ".join(leaf_words)
                idx = start_index + chunk_num

                chunks.append(TextChunk(
                    text=leaf_text,
                    context_text=medium_text,   # D7: LLM sees section, not fragment
                    source_id=f"{source_path}:{idx}",
                    doc_type=doc_type,
                    chunk_index=idx,
                    metadata={
                        "strategy": "hierarchical",
                        "chunk_sizes": chunk_sizes,
                        "level": "leaf",
                        "parent_text_preview": medium_text[:100],
                    },
                ))
                chunk_num += 1

    return chunks


def _semantic(
    text: str,
    source_path: str,
    doc_type: str,
    *,
    breakpoint_percentile: int = 92,
    start_index: int = 0,
    embedder: Any = None,
    max_sentences: int = 500,
) -> list[TextChunk]:
    """Semantic chunking: split where embedding distance spikes.

    D18: Falls back to sentence_window if sentence count exceeds max_sentences
    to prevent silent multi-minute hangs on large documents.

    Requires an embedder to compute sentence-level distances.
    Falls back to sentence_window if embedder is None.
    """
    sentences = _sentences(text)

    if len(sentences) > max_sentences:
        logger.warning(
            "Semantic chunking: %d sentences exceeds semantic_max_sentences=%d "
            "for '%s'. Falling back to sentence_window (window_size=3). "
            "Increase semantic_max_sentences or use a different doc_type.",
            len(sentences), max_sentences, source_path,
        )
        return _sentence_window(
            text, source_path, doc_type, window_size=3, start_index=start_index
        )

    if embedder is None:
        logger.warning(
            "Semantic chunking requested but no embedder provided for '%s'. "
            "Falling back to sentence_window.",
            source_path,
        )
        return _sentence_window(
            text, source_path, doc_type, window_size=3, start_index=start_index
        )

    if not sentences:
        return []

    try:
        # Embed all sentences to find topic boundaries
        vectors = embedder.embed(sentences, validate_tokens=False)
    except Exception as exc:
        logger.warning(
            "Semantic chunker: embedding failed for '%s': %s. "
            "Falling back to sentence_window.", source_path, exc
        )
        return _sentence_window(
            text, source_path, doc_type, window_size=3, start_index=start_index
        )

    # Compute cosine distances between adjacent sentence embeddings
    import math
    distances: list[float] = []
    for i in range(len(vectors) - 1):
        a, b = vectors[i], vectors[i + 1]
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a)) or 1e-9
        norm_b = math.sqrt(sum(x * x for x in b)) or 1e-9
        cosine_sim = dot / (norm_a * norm_b)
        distances.append(1.0 - cosine_sim)  # distance = 1 - similarity

    if not distances:
        chunk_text = " ".join(sentences)
        return [TextChunk(
            text=chunk_text,
            context_text=chunk_text,
            source_id=f"{source_path}:{start_index}",
            doc_type=doc_type,
            chunk_index=start_index,
            metadata={"strategy": "semantic"},
        )]

    # Find breakpoints where distance exceeds the percentile threshold
    sorted_distances = sorted(distances)
    threshold_idx = int(len(sorted_distances) * breakpoint_percentile / 100)
    threshold = sorted_distances[min(threshold_idx, len(sorted_distances) - 1)]

    breakpoints = {i + 1 for i, d in enumerate(distances) if d >= threshold}

    # Build chunks from sentence groups
    chunks: list[TextChunk] = []
    current_group: list[str] = []
    chunk_num = 0

    for i, sent in enumerate(sentences):
        if i in breakpoints and current_group:
            chunk_text = " ".join(current_group)
            idx = start_index + chunk_num
            chunks.append(TextChunk(
                text=chunk_text,
                context_text=chunk_text,
                source_id=f"{source_path}:{idx}",
                doc_type=doc_type,
                chunk_index=idx,
                metadata={
                    "strategy": "semantic",
                    "breakpoint_percentile": breakpoint_percentile,
                    "sentence_count": len(current_group),
                },
            ))
            chunk_num += 1
            current_group = []
        current_group.append(sent)

    # Final group
    if current_group:
        chunk_text = " ".join(current_group)
        idx = start_index + chunk_num
        chunks.append(TextChunk(
            text=chunk_text,
            context_text=chunk_text,
            source_id=f"{source_path}:{idx}",
            doc_type=doc_type,
            chunk_index=idx,
            metadata={
                "strategy": "semantic",
                "breakpoint_percentile": breakpoint_percentile,
                "sentence_count": len(current_group),
            },
        ))

    return chunks


# ---------------------------------------------------------------------------
# Chunker — public entry point
# ---------------------------------------------------------------------------

class Chunker:
    """Route documents to the correct chunking strategy based on doc_type.

    Args:
        config:           Full rag_lib config dict.
        embedder:         OllamaEmbedder instance (required for semantic strategy).
        max_embed_tokens: Hard ceiling for chunk.text word count. ChunkerError
                          raised if any leaf chunk exceeds this (D7 enforcement).
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        embedder: Any = None,
        max_embed_tokens: int = 1800,
    ) -> None:
        self._config = config or {}
        self._embedder = embedder
        self._max_embed_tokens = max_embed_tokens
        self._semantic_max = (
            self._config.get("chunker", {}).get("semantic_max_sentences", 500)
        )

    def chunk(self, doc: Any) -> list[TextChunk]:
        """Chunk a LoadedDocument. Returns list of TextChunk ready for embedding."""
        from .loader import LoadedDocument
        if not isinstance(doc, LoadedDocument):
            raise ChunkerError(f"Expected LoadedDocument, got {type(doc).__name__}")

        if not doc.text or not doc.text.strip():
            raise ChunkerError(
                f"Empty document after loading: {doc.source_path}. "
                "Check loader output or exclude this file."
            )

        doc_type_config = self._get_doc_type_config(doc.doc_type)
        strategy = doc_type_config.get("strategy", "fixed_size")

        chunks = self._dispatch(doc, strategy, doc_type_config)
        self._validate_chunks(chunks, doc.source_path)
        return chunks

    def _dispatch(
        self,
        doc: Any,
        strategy: str,
        cfg: dict[str, Any],
    ) -> list[TextChunk]:
        path = doc.source_path

        if strategy == "sentence_window":
            return _sentence_window(
                doc.text, path, doc.doc_type,
                window_size=cfg.get("window_size", 3),
            )
        elif strategy == "hierarchical":
            return _hierarchical(
                doc.text, path, doc.doc_type,
                chunk_sizes=cfg.get("chunk_sizes", [2048, 512, 128]),
            )
        elif strategy == "semantic":
            return _semantic(
                doc.text, path, doc.doc_type,
                breakpoint_percentile=cfg.get("breakpoint_percentile", 92),
                embedder=self._embedder,
                max_sentences=self._semantic_max,
            )
        else:  # fixed_size (default)
            return _fixed_size(
                doc.text, path, doc.doc_type,
                chunk_size=cfg.get("chunk_size", 512),
                chunk_overlap=cfg.get("chunk_overlap", 50),
            )

    def _validate_chunks(
        self,
        chunks: list[TextChunk],
        source_path: str,
    ) -> None:
        """Enforce D7: text must not exceed max_embed_tokens."""
        for chunk in chunks:
            word_count = len(chunk.text.split())
            if word_count > self._max_embed_tokens:
                raise ChunkerError(
                    f"Chunk from '{source_path}' (index {chunk.chunk_index}) "
                    f"exceeds max_embed_tokens: {word_count} words > {self._max_embed_tokens}. "
                    "Reduce chunk_sizes or chunk_size in the doc_type config."
                )

    def _get_doc_type_config(self, doc_type: str) -> dict[str, Any]:
        chunker_cfg = self._config.get("chunker", {})
        doc_types = chunker_cfg.get("doc_types", {})
        defaults = chunker_cfg.get("defaults", {
            "strategy": "fixed_size",
            "chunk_size": 512,
            "chunk_overlap": 50,
        })
        return {**defaults, **doc_types.get(doc_type, {})}
