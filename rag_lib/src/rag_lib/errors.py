"""
rag_lib.errors

Exception hierarchy for rag_lib. All public methods catch internal
exceptions (urllib, sqlite3, chromadb, sentence_transformers) and
re-raise as the appropriate subclass so callers never see library
internals.
"""

from __future__ import annotations


class RagLibError(Exception):
    """Base for all rag_lib errors."""


class EmbedderError(RagLibError):
    """Ollama embedder unreachable, model not loaded, or token limit exceeded.

    Common causes:
    - Ollama not running: start with `ollama serve`
    - Model not pulled: `ollama pull nomic-embed-text-v2-moe`
    - Text exceeds max_embed_tokens: check chunker config
    """


class StorageError(RagLibError):
    """ChromaDB operation failed.

    Includes embedding model version mismatch — raised when the configured
    embed_model differs from what was used to build the collection.
    Re-ingest with the original model, or delete the collection and rebuild.
    """


class LoaderError(RagLibError):
    """Document could not be loaded, parsed, or passed readability checks.

    Common causes:
    - DRM-encrypted MOBI/EPUB: use a DRM-free source
    - Corrupt or truncated file
    - Image-only PDF with OCR disabled: install pytesseract and enable [ocr]
    - Binary content detected in extracted text
    - Unsupported file format
    """


class ChunkerError(RagLibError):
    """Chunking produced invalid output.

    Common causes:
    - Empty document after loading
    - Chunk exceeds max_embed_tokens: text (not context_text) is being chunked,
      check that the strategy is not producing oversized leaf nodes
    - Semantic chunker timed out and fallback was disabled
    """


class RerankerError(RagLibError):
    """Cross-encoder not available or model download failed.

    The reranker requires sentence-transformers:
        pip install rag-lib[rerank]

    On first use, the model is downloaded from HuggingFace. For air-gapped
    machines, pre-download with:
        python -m rag_lib.scripts.setup_models --reranker

    The HuggingFace model cache is at: ~/.cache/huggingface/hub/
    """


class EvalError(RagLibError):
    """RAGAS evaluation failed.

    Common causes:
    - judge_llm not provided: required parameter, no default.
      Use a stronger model than the generator to avoid self-evaluation bias.
      Recommended: Claude Haiku (~$0.50/100 queries) or qwen3:32b judging qwen3:8b.
    - ragas not installed: pip install rag-lib[eval]
    - Ground truth dataset missing required fields (question, ground_truths)
    """
