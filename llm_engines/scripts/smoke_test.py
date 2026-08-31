#!/usr/bin/env python3
"""
scripts/smoke_test.py

Quick validation of the llm_engines installation against your actual environment.
Run this before the full test suite to catch environment issues early.

Usage:
    cd ~/ai_tools/llm_engines
    source ~/ai-env/bin/activate
    python scripts/smoke_test.py

    # Skip Ollama checks (offline mode):
    python scripts/smoke_test.py --offline

    # Also test cloud backends:
    python scripts/smoke_test.py --anthropic --openai
"""

from __future__ import annotations

import argparse
import sys
import time

# ---------------------------------------------------------------------------
# Colour output helpers (no dependencies)
# ---------------------------------------------------------------------------


def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m"


def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m"


def _yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m"


def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m"


_results: list[tuple[str, bool, str]] = []


def _check(name: str, fn):
    """Run a check function, record pass/fail."""
    try:
        detail = fn()
        _results.append((name, True, detail or ""))
        print(f"  {_green('PASS')} {name}" + (f"  ({detail})" if detail else ""))
        return True
    except Exception as e:
        _results.append((name, False, str(e)))
        print(f"  {_red('FAIL')} {name}")
        print(f"       {_red(str(e))}")
        return False


def _section(title: str) -> None:
    print(f"\n{_bold(title)}")
    print("-" * 50)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_imports() -> None:
    _section("1. Import checks")

    def _contracts():
        from llm_engines.contracts import (  # noqa: F401
            ChatMessage,
            ChatModel,
            EmbeddingModel,
            EmbeddingRequest,
            EmbeddingResponse,
            GenerationRequest,
            GenerationResponse,
            LogprobModel,
            StreamingModel,
        )
        from llm_engines.router import FailoverEngine  # noqa: F401

        return "contracts OK"

    def _llm_engines():
        import llm_engines

        return f"v{llm_engines.__version__}"

    def _pydantic():
        import pydantic

        v = pydantic.VERSION
        if not v.startswith("2."):
            raise RuntimeError(f"Pydantic v2 required, got {v}")
        return f"pydantic {v}"

    def _yaml():
        import yaml  # noqa: F401

        return "pyyaml OK"

    def _structured_output():
        from llm_engines.utils.structured_output import StructuredOutputHandler
        from pydantic import BaseModel

        class T(BaseModel):
            x: int

        result = StructuredOutputHandler.parse('{"x": 42}', T)
        assert result.x == 42
        return "parse OK"

    def _mock_engine():
        from llm_engines.backends.mock import MockEngine
        from llm_engines.contracts import ChatMessage, GenerationRequest

        engine = MockEngine()
        resp = engine.generate(GenerationRequest(messages=[ChatMessage(role="user", content="hi")]))
        assert resp.message.content
        assert resp.backend == "mock"
        return "MockEngine generate OK"

    _check("contracts imports", _contracts)
    _check("llm_engines imports", _llm_engines)
    _check("pydantic v2", _pydantic)
    _check("pyyaml", _yaml)
    _check("StructuredOutputHandler", _structured_output)
    _check("MockEngine", _mock_engine)


def check_hardware() -> None:
    _section("2. Hardware detection")

    def _detect():
        from llm_engines.discovery import detect_hardware

        hw = detect_hardware()
        parts = [f"CPU cores={hw.cpu_cores}", f"RAM={hw.memory_total_mb}MB"]
        if hw.has_cuda:
            parts.append(f"CUDA GPUs={len(hw.gpus)}")
            parts.append(f"VRAM={hw.vram_total_mb}MB")
            for g in hw.gpus:
                parts.append(f"  GPU[{g.id}]: {g.name} {g.vram_mb}MB")
        else:
            parts.append("CUDA=False (CPU-only)")
        return " | ".join(parts[:3])

    _check("detect_hardware()", _detect)


def check_ollama(args) -> None:
    _section("3. Ollama")

    def _running():
        from llm_engines.discovery import check_ollama_running

        if not check_ollama_running():
            raise RuntimeError("Ollama not reachable at localhost:11434. Run: ollama serve")
        return "reachable"

    def _models():
        from llm_engines.discovery import list_ollama_models

        models = list_ollama_models()
        if not models:
            raise RuntimeError("No models pulled. Run: ollama pull qwen3:8b")
        names = [m.name for m in models[:5]]
        return f"{len(models)} models: {', '.join(names)}"

    def _logprobs_version():
        from llm_engines.discovery import check_ollama_logprobs_support

        supported = check_ollama_logprobs_support()
        if not supported:
            return "WARN: Ollama < 0.12.11 — logprobs unavailable (surprise filter limited)"
        return "logprobs supported (>=0.12.11)"

    def _registry():
        from llm_engines.discovery import ModelRegistry, detect_hardware

        registry = ModelRegistry()
        hw = detect_hardware()
        registry.list_available_models("ollama")
        rec = registry.recommend_model("chat", hw, "ollama")
        return f"recommend_model → {rec}"

    if not _check("ollama running", _running):
        print(f"  {_yellow('SKIP')} remaining Ollama checks (server not running)")
        return

    _check("list models", _models)
    _check("logprobs version check", _logprobs_version)
    _check("ModelRegistry.recommend_model()", _registry)

    # Pick a small model that's likely available
    from llm_engines.discovery import list_ollama_models

    available = [m.name for m in list_ollama_models()]
    test_model = next(
        (m for m in available if any(x in m for x in ["8b", "3b", "7b", "9b"])),
        available[0] if available else None,
    )
    if not test_model:
        print(f"  {_yellow('SKIP')} generate/embed tests — no models available")
        return

    print(f"  Using model: {test_model}")

    def _generate():
        from llm_engines.backends.ollama import OllamaEngine
        from llm_engines.contracts import ChatMessage, GenerationRequest

        engine = OllamaEngine(model=test_model, keep_alive=0)
        t0 = time.perf_counter()
        resp = engine.generate(
            GenerationRequest(
                messages=[ChatMessage(role="user", content="Reply with exactly the word: OK")],
                max_tokens=10,
                temperature=0.0,
            )
        )
        elapsed = time.perf_counter() - t0
        assert resp.message.content, "Empty response"
        assert resp.backend == "ollama"
        assert resp.usage.output_tokens is not None
        return f"{elapsed:.1f}s, {resp.usage.output_tokens} tokens"

    def _think_false():
        """Verify think=False is being honoured (no <think> in output)."""
        from llm_engines.backends.ollama import OllamaEngine
        from llm_engines.contracts import ChatMessage, GenerationRequest

        engine = OllamaEngine(model=test_model, keep_alive=0, think=False)
        resp = engine.generate(
            GenerationRequest(
                messages=[ChatMessage(role="user", content="What is 2+2?")],
                max_tokens=50,
                temperature=0.0,
            )
        )
        content = resp.message.content or ""
        if "<think>" in content.lower():
            raise RuntimeError("think=False not working — <think> block in response")
        return "no <think> block"

    def _failover():
        from llm_engines import EngineFactory

        # Use the first available profile rather than hardcoding 'test'
        from llm_engines.config_loader import load_config

        cfg = load_config()
        profiles = list((cfg.get("profiles") or {}).keys())
        if not profiles:
            return "no profiles configured — skipping"
        profile_name = profiles[0]
        EngineFactory.from_profile(profile_name)
        return f"FailoverEngine via profile '{profile_name}' OK"

    _check(f"OllamaEngine.generate() [{test_model}]", _generate)
    _check("think=False enforced", _think_false)
    _check("FailoverEngine (mock profile)", _failover)

    # Embedding check — look for an embedding model
    embed_model = next(
        (m for m in available if any(x in m for x in ["embed", "nomic", "bge", "mxbai"])),
        None,
    )
    if embed_model:

        def _embed():
            from llm_engines.backends.ollama import OllamaEngine
            from llm_engines.contracts import EmbeddingRequest

            engine = OllamaEngine(model=embed_model, keep_alive=0)
            resp = engine.embed(EmbeddingRequest(texts=["Hello world", "Test sentence"]))
            assert len(resp.vectors) == 2
            assert resp.dimensions > 0
            return f"{embed_model} dim={resp.dimensions}"

        _check(f"OllamaEngine.embed() [{embed_model}]", _embed)
    else:
        print(f"  {_yellow('SKIP')} embed test — no embedding model pulled")
        print("         Run: ollama pull nomic-embed-text")


def check_engram_adapter() -> None:
    _section("4. Engram semantic extraction")

    def _import():
        from engram.semantic.extractor import SemanticExtractor  # noqa: F401

        return "import OK"

    def _extract_entities():
        from engram.semantic.extractor import SemanticExtractor
        from llm_engines.backends.mock import MockEngine
        import json

        payload = json.dumps(
            [{"type": "preference", "subject": "auth", "value": "Alice", "confidence": 0.8}]
        )
        engine = MockEngine(response_fn=lambda r: payload)
        extractor = SemanticExtractor(llm_engine=engine, enable_llm_extraction=True)
        result = extractor.extract("Alice works on auth")
        assert result.facts[0].subject == "auth"
        return "SemanticExtractor OK"

    if not _check("engram.semantic import", _import):
        print(f"  {_yellow('INFO')} Install with: pip install -e ~/ai_tools/engram")
        return

    _check("SemanticExtractor.extract()", _extract_entities)


def check_rag_inspector() -> None:
    _section("5. RAGInspector")

    def _import():
        from llm_inspector import EngramRAGAdapter, RAGInspector  # noqa: F401

        return "import OK"

    def _compare():
        from llm_inspector.rag import RAGInspector
        from llm_engines.contracts import Chunk

        class FakePipeline:
            def retrieve(self, q):
                return [Chunk(content="Some fact.", source_id="1", score=0.9)]

            def assemble_prompt(self, q, chunks):
                return f"Q: {q}"

            def generate(self, p):
                return "Answer"

        inspector = RAGInspector()
        inspector.add_pipeline("test", FakePipeline())
        results = inspector.query_all("What is the answer?")
        assert len(results) == 1
        assert results[0].error is None
        return f"1 pipeline, 1 chunk, latency={results[0].latency_ms:.0f}ms"

    if not _check("llm_inspector import", _import):
        print(f"  {_yellow('INFO')} Install with: pip install -e ~/ai_tools/llm_inspector")
        return

    _check("RAGInspector.query_all()", _compare)


def check_anthropic(args) -> None:
    _section("6. AnthropicEngine (cloud)")

    import os

    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        print(f"  {_yellow('SKIP')} ANTHROPIC_API_KEY not set")
        return

    def _generate():
        from llm_engines.backends.anthropic import AnthropicEngine
        from llm_engines.contracts import ChatMessage, GenerationRequest

        engine = AnthropicEngine(model="claude-haiku-4-5")
        resp = engine.generate(
            GenerationRequest(
                messages=[ChatMessage(role="user", content="Reply with exactly: OK")],
                max_tokens=10,
                temperature=0.0,
            )
        )
        assert resp.message.content
        assert resp.backend == "anthropic"
        return f"content='{resp.message.content.strip()}' tokens={resp.usage.total_tokens}"

    _check("AnthropicEngine.generate()", _generate)


def check_openai(args) -> None:
    _section("7. OpenAIEngine (cloud)")

    import os

    key = os.getenv("OPENAI_API_KEY")
    if not key:
        print(f"  {_yellow('SKIP')} OPENAI_API_KEY not set")
        return

    def _generate():
        from llm_engines.backends.openai import OpenAIEngine
        from llm_engines.contracts import ChatMessage, GenerationRequest

        engine = OpenAIEngine(model="gpt-4o-mini")
        resp = engine.generate(
            GenerationRequest(
                messages=[ChatMessage(role="user", content="Reply with exactly: OK")],
                max_tokens=10,
                temperature=0.0,
            )
        )
        assert resp.message.content
        return f"content='{resp.message.content.strip()}' tokens={resp.usage.total_tokens}"

    _check("OpenAIEngine.generate()", _generate)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="llm_engines smoke test")
    parser.add_argument("--offline", action="store_true", help="Skip all live service checks")
    parser.add_argument(
        "--anthropic", action="store_true", help="Test Anthropic API (requires ANTHROPIC_API_KEY)"
    )
    parser.add_argument(
        "--openai", action="store_true", help="Test OpenAI API (requires OPENAI_API_KEY)"
    )
    args = parser.parse_args()

    print(_bold("\n=== llm_engines smoke test ==="))

    check_imports()
    check_hardware()

    if not args.offline:
        check_ollama(args)

    check_engram_adapter()
    check_rag_inspector()

    if args.anthropic or not args.offline:
        check_anthropic(args)

    if args.openai or not args.offline:
        check_openai(args)

    # Summary
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = sum(1 for _, ok, _ in _results if not ok)
    total = len(_results)

    print(f"\n{'=' * 50}")
    print(_bold(f"Results: {passed}/{total} passed"))
    if failed:
        print(_red(f"         {failed} failed:"))
        for name, ok, detail in _results:
            if not ok:
                print(f"  • {name}: {detail[:100]}")
    else:
        print(_green("         All checks passed ✓"))
    print()

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
