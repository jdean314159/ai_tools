"""
rag_lib test configuration.

Markers:
    ollama:      requires running Ollama with nomic-embed-text-v2-moe pulled
    integration: requires external services (Ollama + ChromaDB on disk)
    slow:        long-running tests (large corpus)

Run unit tests only (no external services):
    PYTHONPATH=src python -m pytest tests/ -v

Run with integration tests:
    PYTHONPATH=src python -m pytest tests/ -v -m "not slow"

Run everything:
    PYTHONPATH=src python -m pytest tests/ -v --run-integration
"""
from __future__ import annotations

import socket
import tempfile
from pathlib import Path
from typing import Any

import pytest


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def pytest_addoption(parser: Any) -> None:
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests requiring external services",
    )


def pytest_collection_modifyitems(config: Any, items: list) -> None:
    skip_ollama = pytest.mark.skip(
        reason="Ollama not running at localhost:11434 (or nomic-embed-text-v2-moe not pulled)"
    )
    skip_integration = pytest.mark.skip(
        reason="Integration tests disabled — run with --run-integration"
    )

    ollama_up: bool | None = None
    run_integration = config.getoption("--run-integration", default=False)

    for item in items:
        if "ollama" in item.keywords:
            if ollama_up is None:
                ollama_up = _port_open("127.0.0.1", 11434)
            if not ollama_up:
                item.add_marker(skip_ollama)

        if "integration" in item.keywords and not run_integration:
            item.add_marker(skip_integration)


# ------------------------------------------------------------------
# Shared fixtures
# ------------------------------------------------------------------

@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    """Temporary directory cleaned up after each test."""
    return tmp_path


@pytest.fixture
def sample_config(tmp_dir: Path) -> dict:
    """Minimal rag_lib config for unit tests."""
    return {
        "embedder": {
            "host": "http://localhost:11434",
            "model": "nomic-embed-text-v2-moe",
            "timeout": 30,
            "batch_size": 4,
            "keep_alive": 60,
            "doc_prefix": "search_document: ",
            "query_prefix": "search_query: ",
        },
        "storage": {
            "backend": "chromadb",
            "path": str(tmp_dir / "chroma"),
            "collection_prefix": "test_",
            "bm25_path": str(tmp_dir / "bm25"),
        },
        "chunker": {
            "max_embed_tokens": 1800,
            "semantic_max_sentences": 500,
            "defaults": {"strategy": "fixed_size", "chunk_size": 50, "chunk_overlap": 5},
            "doc_types": {
                "policy": {"strategy": "sentence_window", "window_size": 2},
                "spec": {"strategy": "hierarchical", "chunk_sizes": [200, 50, 20]},
                "thesis": {"strategy": "hierarchical", "chunk_sizes": [400, 100, 30]},
                "paper": {"strategy": "sentence_window", "window_size": 3},
            },
        },
        "retriever": {
            "n_candidates": 10,
            "n_results": 3,
            "bm25_weight": 0.4,
            "max_context_tokens": 1000,
        },
        "reranker": {"enabled": False},
        "tables": {
            "complex_threshold": 3,
            "complex_handler": "csv",
            "row_separator": " | ",
        },
        "loader": {
            "min_readable_words": 10,
            "ocr_word_threshold": 5,
            "exclude_patterns": ["**/.svn/**", "*.svn-base"],
        },
    }


@pytest.fixture
def mock_embedder(mocker: Any) -> Any:
    """Mock OllamaEmbedder that returns deterministic vectors."""
    embedder = mocker.MagicMock()
    embedder._doc_prefix = "search_document: "
    embedder._query_prefix = "search_query: "
    embedder._max_embed_tokens = 1800
    embedder.model = "nomic-embed-text-v2-moe"

    def fake_embed(texts, validate_tokens=True):
        # Return a different vector per text based on hash
        import hashlib
        result = []
        for text in texts:
            h = int(hashlib.md5(text.encode()).hexdigest(), 16)
            vec = [(h >> i & 0xFF) / 255.0 for i in range(0, 768 * 8, 8)]
            result.append(vec[:768])
        return result

    def fake_embed_query(text):
        import hashlib
        h = int(hashlib.md5(text.encode()).hexdigest(), 16)
        vec = [(h >> i & 0xFF) / 255.0 for i in range(0, 768 * 8, 8)]
        return vec[:768]

    def fake_dimensions():
        return 768

    embedder.embed.side_effect = fake_embed
    embedder.embed_query.side_effect = fake_embed_query
    embedder.dimensions.side_effect = fake_dimensions
    return embedder


@pytest.fixture
def in_memory_store(sample_config: dict, mock_embedder: Any) -> Any:
    """ChromaStorage backed by in-memory ChromaDB for fast unit tests."""
    pytest.importorskip('chromadb')
    from rag_lib.storage.chroma import ChromaStorage

    store = ChromaStorage(
        path=sample_config["storage"]["path"],
        collection_prefix=sample_config["storage"]["collection_prefix"],
        embed_model="nomic-embed-text-v2-moe",
        embed_dimensions=768,
    )
    return store


class _MiniMocker:
    def __init__(self) -> None:
        import unittest.mock as mock
        self._mock = mock
        self._patches: list[Any] = []
        self.MagicMock = mock.MagicMock
        self.Mock = mock.Mock

    def patch(self, target: str, *args: Any, **kwargs: Any) -> Any:
        patcher = self._mock.patch(target, *args, **kwargs)
        started = patcher.start()
        self._patches.append(patcher)
        return started

    def stopall(self) -> None:
        while self._patches:
            self._patches.pop().stop()


@pytest.fixture

def mocker() -> Any:
    mm = _MiniMocker()
    try:
        yield mm
    finally:
        mm.stopall()
