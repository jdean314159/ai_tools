"""
tests/test_ollama_backend.py

OllamaEngine offline unit tests.

Our OllamaEngine uses raw urllib (no ollama package dependency), so we patch
urllib.request.urlopen rather than an ollama Client. This means these tests
run with no Ollama server and no network.

Live tests: pytest tests/contract_tests/ --backend ollama --model qwen3:8b
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from llm_engines.contracts import (
    BackendUnavailableError,
    ChatMessage,
    EmbeddingRequest,
    GenerationRequest,
    GenerationResponse,
    ModelNotFoundError,
)


# ---------------------------------------------------------------------------
# Helpers: fake HTTP responses
# ---------------------------------------------------------------------------

def _fake_urlopen(response_dict: dict, status: int = 200):
    """Return a context manager that yields a fake HTTP response."""
    body = json.dumps(response_dict).encode()

    class _FakeResp:
        def read(self):
            return body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    return _FakeResp()


def _tags_response(names: list[str]) -> dict:
    """Fake /api/tags response."""
    return {"models": [{"name": n, "size": 5_000_000_000} for n in names]}


def _version_response(version: str = "0.12.11") -> dict:
    return {"version": version}


def _chat_response(content: str = "Hello!", prompt_tokens: int = 10, eval_tokens: int = 5) -> dict:
    return {
        "model": "qwen3:8b",
        "message": {"role": "assistant", "content": content},
        "done": True,
        "done_reason": "stop",
        "prompt_eval_count": prompt_tokens,
        "eval_count": eval_tokens,
    }


def _embed_response(vectors: list[list[float]]) -> dict:
    return {"embeddings": vectors}


# ---------------------------------------------------------------------------
# Fixture: patch all urllib calls for a single test
# ---------------------------------------------------------------------------

def _make_url_dispatch(routes: dict):
    """
    Returns a side_effect callable for urlopen that dispatches by URL path.
    routes: {path_suffix: response_dict}  e.g. {"/api/tags": {...}}
    """
    def _dispatch(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        for path, data in routes.items():
            if path in url:
                return _fake_urlopen(data)
        raise ValueError(f"Unexpected URL in test: {url}")
    return _dispatch


@pytest.fixture()
def ollama_engine():
    """OllamaEngine with all urllib calls mocked. Model: qwen3:8b."""
    routes = {
        "/api/tags":    _tags_response(["qwen3:8b", "nomic-embed-text"]),
        "/api/version": _version_response("0.12.11"),
        "/api/chat":    _chat_response("Mocked response"),
        "/api/embed":   _embed_response([[0.1, 0.2, 0.3]]),
    }
    with patch("urllib.request.urlopen", side_effect=_make_url_dispatch(routes)):
        from llm_engines.backends.ollama import OllamaEngine
        yield OllamaEngine(model="qwen3:8b", host="http://localhost:11434")


def _req(content: str = "Hello") -> GenerationRequest:
    return GenerationRequest(messages=[ChatMessage(role="user", content=content)])


def _nested_schema() -> dict:
    return {
        "$defs": {
            "Concern": {
                "type": "object",
                "properties": {"finding_ref": {"type": "string"}},
                "required": ["finding_ref"],
            }
        },
        "type": "object",
        "properties": {"concern": {"$ref": "#/$defs/Concern"}},
        "required": ["concern"],
    }


# ---------------------------------------------------------------------------
# ChatModel
# ---------------------------------------------------------------------------

class TestOllamaGenerate:

    def test_seed_zero_is_in_payload_and_acceptance_is_reported(self, ollama_engine) -> None:
        payload = ollama_engine._base_payload([], 10, 0, seed=0)
        assert payload["options"]["seed"] == 0

        response = ollama_engine.generate(
            GenerationRequest(messages=_req().messages, seed=0)
        )
        assert response.seed_status == "accepted"

    def test_returns_generation_response(self, ollama_engine) -> None:
        routes = {"/api/chat": _chat_response("Test response")}
        with patch("urllib.request.urlopen", side_effect=_make_url_dispatch(routes)):
            response = ollama_engine.generate(_req())
        assert isinstance(response, GenerationResponse)
        assert response.message.content == "Test response"
        assert response.message.role == "assistant"
        assert response.finish_reason == "stop"
        assert response.backend == "ollama"
        assert response.model_name == "qwen3:8b"

    def test_usage_tokens_populated(self, ollama_engine) -> None:
        routes = {"/api/chat": _chat_response(prompt_tokens=12, eval_tokens=7)}
        with patch("urllib.request.urlopen", side_effect=_make_url_dispatch(routes)):
            response = ollama_engine.generate(_req())
        assert response.usage.input_tokens == 12
        assert response.usage.output_tokens == 7
        assert response.usage.total_tokens == 19
        assert response.usage.latency_ms is not None and response.usage.latency_ms >= 0

    def test_empty_messages_raises(self, ollama_engine) -> None:
        from llm_engines.contracts import GenerationError
        with pytest.raises(GenerationError):
            ollama_engine.generate(GenerationRequest(messages=[]))

    def test_think_false_in_payload(self, ollama_engine) -> None:
        """Ensure think=False is sent in payload (suppresses CoT for Qwen3)."""
        captured_payloads = []

        def capture(req, timeout=None):
            body = req.data
            if body:
                captured_payloads.append(json.loads(body))
            return _fake_urlopen(_chat_response())

        with patch("urllib.request.urlopen", side_effect=capture):
            ollama_engine.generate(_req())

        assert len(captured_payloads) == 1
        assert captured_payloads[0]["think"] is False

    def test_num_gpu_in_payload(self) -> None:
        """num_gpu must appear in options when set."""
        routes = {
            "/api/tags":    _tags_response(["qwen3:27b"]),
            "/api/version": _version_response(),
        }
        with patch("urllib.request.urlopen", side_effect=_make_url_dispatch(routes)):
            from llm_engines.backends.ollama import OllamaEngine
            engine = OllamaEngine(model="qwen3:27b", num_gpu=40)

        captured = []
        def capture(req, timeout=None):
            if req.data:
                captured.append(json.loads(req.data))
            return _fake_urlopen(_chat_response())

        with patch("urllib.request.urlopen", side_effect=capture):
            engine.generate(_req())

        assert captured[0]["options"]["num_gpu"] == 40

    def test_stop_sequences_in_payload(self, ollama_engine) -> None:
        captured = []
        def capture(req, timeout=None):
            if req.data:
                captured.append(json.loads(req.data))
            return _fake_urlopen(_chat_response())

        request = GenerationRequest(
            messages=[ChatMessage(role="user", content="Hi")],
            stop=["<|endoftext|>", "\n\n"],
        )
        with patch("urllib.request.urlopen", side_effect=capture):
            ollama_engine.generate(request)

        assert captured[0]["options"]["stop"] == ["<|endoftext|>", "\n\n"]

    def test_keep_alive_in_payload(self, ollama_engine) -> None:
        captured = []
        def capture(req, timeout=None):
            if req.data:
                captured.append(json.loads(req.data))
            return _fake_urlopen(_chat_response())

        with patch("urllib.request.urlopen", side_effect=capture):
            ollama_engine.generate(_req())

        assert "keep_alive" in captured[0]
        assert captured[0]["keep_alive"] == 300  # default

    def test_json_schema_in_payload_format_when_set(self, ollama_engine) -> None:
        schema = {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        }
        captured = []

        def capture(req, timeout=None):
            if req.data:
                captured.append(json.loads(req.data))
            return _fake_urlopen(_chat_response('{"summary":"ok"}'))

        request = GenerationRequest(
            messages=[ChatMessage(role="user", content="Hi")],
            json_schema=schema,
        )
        with patch("urllib.request.urlopen", side_effect=capture):
            ollama_engine.generate(request)

        assert captured[0]["format"] == schema

    def test_nested_json_schema_refs_are_inlined_in_payload_format(self, ollama_engine) -> None:
        schema = _nested_schema()
        captured = []

        def capture(req, timeout=None):
            if req.data:
                captured.append(json.loads(req.data))
            return _fake_urlopen(_chat_response('{"concern":{"finding_ref":"x"}}'))

        request = GenerationRequest(
            messages=[ChatMessage(role="user", content="Hi")],
            json_schema=schema,
        )
        with patch("urllib.request.urlopen", side_effect=capture):
            ollama_engine.generate(request)

        payload_schema = captured[0]["format"]
        assert "$defs" not in payload_schema
        assert "$ref" not in json.dumps(payload_schema)
        assert payload_schema["properties"]["concern"]["type"] == "object"
        assert payload_schema["properties"]["concern"]["properties"]["finding_ref"]["type"] == "string"
        assert schema["properties"]["concern"]["$ref"] == "#/$defs/Concern"

    def test_format_absent_without_json_schema(self, ollama_engine) -> None:
        captured = []

        def capture(req, timeout=None):
            if req.data:
                captured.append(json.loads(req.data))
            return _fake_urlopen(_chat_response())

        with patch("urllib.request.urlopen", side_effect=capture):
            ollama_engine.generate(_req())

        assert "format" not in captured[0]


# ---------------------------------------------------------------------------
# EmbeddingModel
# ---------------------------------------------------------------------------

class TestOllamaEmbed:

    def test_embed_returns_vectors(self, ollama_engine) -> None:
        routes = {"/api/embed": _embed_response([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])}
        with patch("urllib.request.urlopen", side_effect=_make_url_dispatch(routes)):
            response = ollama_engine.embed(EmbeddingRequest(texts=["a", "b"]))
        assert len(response.vectors) == 2
        assert response.dimensions == 3
        assert response.backend == "ollama"

    def test_embed_uses_request_model_when_set(self, ollama_engine) -> None:
        captured = []
        def capture(req, timeout=None):
            if req.data:
                captured.append(json.loads(req.data))
            return _fake_urlopen(_embed_response([[0.1]]))

        with patch("urllib.request.urlopen", side_effect=capture):
            ollama_engine.embed(EmbeddingRequest(texts=["test"], model="nomic-embed-text"))

        assert captured[0]["model"] == "nomic-embed-text"


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------

class TestOllamaCapabilities:

    def test_capabilities_flags(self, ollama_engine) -> None:
        caps = ollama_engine.get_capabilities()
        assert caps.chat is True
        assert caps.streaming is True
        assert caps.embeddings is True
        assert caps.async_streaming is False
        assert caps.tool_calling is False  # Phase 2
        assert caps.structured_output is True

    def test_logprobs_capability_matches_version(self) -> None:
        """Logprobs capability should be False for Ollama < 0.12.11."""
        routes = {
            "/api/tags":    _tags_response(["qwen3:8b"]),
            "/api/version": _version_response("0.9.0"),  # too old
        }
        with patch("urllib.request.urlopen", side_effect=_make_url_dispatch(routes)):
            from llm_engines.backends.ollama import OllamaEngine
            engine = OllamaEngine(model="qwen3:8b")
        assert engine.get_capabilities().logprobs is False


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestOllamaErrors:

    def test_unavailable_raises_backend_unavailable(self) -> None:
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            from llm_engines.backends.ollama import OllamaEngine
            with pytest.raises(BackendUnavailableError):
                OllamaEngine(model="qwen3:8b")

    def test_model_not_found_raises(self) -> None:
        routes = {
            "/api/tags":    _tags_response(["qwen3:8b"]),
            "/api/version": _version_response(),
        }
        with patch("urllib.request.urlopen", side_effect=_make_url_dispatch(routes)):
            from llm_engines.backends.ollama import OllamaEngine
            with pytest.raises(ModelNotFoundError):
                OllamaEngine(model="nonexistent:99b")

    def test_exact_match_required_for_ambiguous_prefix(self) -> None:
        """qwen3:27b should NOT match when only qwen3:8b is available."""
        routes = {
            "/api/tags":    _tags_response(["qwen3:8b"]),
            "/api/version": _version_response(),
        }
        with patch("urllib.request.urlopen", side_effect=_make_url_dispatch(routes)):
            from llm_engines.backends.ollama import OllamaEngine
            with pytest.raises(ModelNotFoundError):
                OllamaEngine(model="qwen3:27b")

    def test_unambiguous_prefix_match_accepted(self) -> None:
        """qwen3:27b should match when it's the only qwen3 variant available."""
        routes = {
            "/api/tags":    _tags_response(["qwen3:27b"]),
            "/api/version": _version_response(),
        }
        with patch("urllib.request.urlopen", side_effect=_make_url_dispatch(routes)):
            from llm_engines.backends.ollama import OllamaEngine
            engine = OllamaEngine(model="qwen3:27b")
        assert engine.model == "qwen3:27b"

    def test_normalize_host_strips_v1(self) -> None:
        from llm_engines.backends.ollama import _normalize_host_url
        assert _normalize_host_url("http://localhost:11434/v1") == "http://localhost:11434"
        assert _normalize_host_url("http://localhost:11434") == "http://localhost:11434"
        assert _normalize_host_url("http://localhost:11434/v1/") == "http://localhost:11434"
