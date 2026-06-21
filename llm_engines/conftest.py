from __future__ import annotations

import os
import socket

import pytest


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def pytest_collection_modifyitems(items: list) -> None:
    skip_openai = pytest.mark.skip(reason="OPENAI_API_KEY not set")
    skip_vllm = pytest.mark.skip(reason="vLLM server not running at localhost:8000")
    skip_slow = pytest.mark.skip(
        reason="turboquant not installed (pip install llm-engines[optimizations])"
    )
    skip_ollama = pytest.mark.skip(reason="Ollama not running at localhost:11434")

    has_openai_key = bool(os.getenv("OPENAI_API_KEY"))
    vllm_up: bool | None = None
    ollama_up: bool | None = None
    turboquant_ok: bool | None = None

    for item in items:
        if "openai" in item.keywords and not has_openai_key:
            item.add_marker(skip_openai)

        if "vllm" in item.keywords:
            if vllm_up is None:
                vllm_up = _port_open("127.0.0.1", 8000)
            if not vllm_up:
                item.add_marker(skip_vllm)

        if "slow" in item.keywords:
            if turboquant_ok is None:
                try:
                    import turboquant  # noqa: F401

                    turboquant_ok = True
                except ImportError:
                    turboquant_ok = False
            if not turboquant_ok:
                item.add_marker(skip_slow)

        if "ollama" in item.keywords:
            if ollama_up is None:
                ollama_up = _port_open("127.0.0.1", 11434)
            if not ollama_up:
                item.add_marker(skip_ollama)
