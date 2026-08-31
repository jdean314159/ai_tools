"""
tests/contract_tests/conftest.py

Pytest fixtures for conformance tests.

Usage:
    # Test mock engine (no services required)
    pytest tests/contract_tests/ -k mock

    # Test Ollama chat only (qwen3:8b doesn't support embeddings)
    pytest tests/contract_tests/ --backend ollama --model qwen3:8b

    # Test Ollama chat + embeddings with a dedicated embedding model
    pytest tests/contract_tests/ --backend ollama --model qwen3:8b \
        --embed-model nomic-embed-text

    # Test all
    pytest tests/contract_tests/ --backend ollama --model qwen3:8b \
        --embed-model nomic-embed-text
"""

from __future__ import annotations

import pytest

from llm_engines.contracts import ChatModel, EmbeddingModel
from llm_engines.backends.mock import MockEngine


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--backend",
        action="store",
        default="mock",
        help="Backend to test: mock | ollama | anthropic | openai",
    )
    parser.addoption(
        "--model",
        action="store",
        default=None,
        help="Chat model name for live backend tests",
    )
    parser.addoption(
        "--embed-model",
        action="store",
        default=None,
        help="Embedding model name (e.g. nomic-embed-text). "
        "Required for embedding conformance tests against Ollama. "
        "Omit to skip embedding tests.",
    )


def _build_engine(backend: str, model: str | None) -> ChatModel:
    if backend == "mock":
        return MockEngine()

    if backend == "ollama":
        from llm_engines.backends.ollama import OllamaEngine

        return OllamaEngine(model=model or "qwen2.5:8b")

    if backend == "anthropic":
        from llm_engines.backends.anthropic import AnthropicEngine

        return AnthropicEngine(model=model or "claude-sonnet-4-6")

    if backend == "openai":
        from llm_engines.backends.openai import OpenAIEngine

        return OpenAIEngine(model=model or "gpt-4o-mini")

    raise ValueError(f"Unknown backend: {backend}")


def _build_embed_engine(backend: str, embed_model: str | None) -> EmbeddingModel | None:
    """Return an EmbeddingModel or None if no embed model was specified."""
    if embed_model is None:
        return None

    if backend == "mock":
        # MockEngine doesn't support embeddings — skip silently
        return None

    if backend == "ollama":
        from llm_engines.backends.ollama import OllamaEngine

        return OllamaEngine(model=embed_model)

    if backend == "openai":
        from llm_engines.backends.openai import OpenAIEngine

        return OpenAIEngine(model="gpt-4o-mini")

    return None


@pytest.fixture(scope="module")
def chat_engine(request: pytest.FixtureRequest) -> ChatModel:
    """Return a ChatModel for the requested backend."""
    backend = request.config.getoption("--backend", default="mock")
    model = request.config.getoption("--model", default=None)
    return _build_engine(backend, model)


@pytest.fixture(scope="module")
def embed_engine(request: pytest.FixtureRequest) -> EmbeddingModel:
    """
    Return an EmbeddingModel for the requested backend.

    Skips automatically when no --embed-model is provided, or when
    the backend/model combination doesn't support embeddings.

    Pass --embed-model nomic-embed-text (or similar) to enable.
    """
    backend = request.config.getoption("--backend", default="mock")
    embed_model = request.config.getoption("--embed-model", default=None)

    engine = _build_embed_engine(backend, embed_model)
    if engine is None:
        pytest.skip(
            "Embedding tests require --embed-model <model>. Example: --embed-model nomic-embed-text"
        )
    return engine
