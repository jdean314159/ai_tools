"""
tests/test_optimizations.py

ComboEngine and TurboQuantEngine offline unit tests.

Key constraint: transformers imports safetensors, which has a PyO3 binary
compiled for CPython 3.8. On Python 3.12 this raises:
  "PyO3 modules compiled for CPython 3.8 or older may only be initialized once"

The fix: never use patch("transformers.AutoXxx.from_pretrained", ...) because
patch() imports the module before patching it. Instead inject fake modules into
sys.modules BEFORE any import of transformers or safetensors can occur.

All tests here use __new__ + manual attribute assignment to bypass __init__
entirely — no real model loading, no GPU required.

Live tests: pytest -m slow (requires GPU, model files, turboquant package)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import torch

from llm_engines.contracts import ChatMessage, GenerationRequest, GenerationResponse


# ---------------------------------------------------------------------------
# Shared mock infrastructure
# ---------------------------------------------------------------------------

class _FakeBatchEncoding(dict):
    """dict subclass with .to() method, mimicking HuggingFace BatchEncoding."""
    def to(self, device):
        return self


def _fake_tokenizer(vocab_size: int = 150000) -> MagicMock:
    tok = MagicMock()
    tok.apply_chat_template.return_value = (
        "<|im_start|>user\nHi<|im_end|>\n<|im_start|>assistant\n"
    )
    ids = torch.tensor([[1, 2, 3, 4, 5]])
    tok.return_value = _FakeBatchEncoding(
        {"input_ids": ids, "attention_mask": torch.ones_like(ids)}
    )
    tok.decode.return_value = "Generated response text"
    tok.__len__ = lambda self: vocab_size
    return tok


def _fake_model(output_tokens: int = 20) -> MagicMock:
    model = MagicMock()
    param = MagicMock()
    param.device = torch.device("cpu")
    model.parameters.return_value = iter([param])
    generated = torch.arange(100, 100 + output_tokens).unsqueeze(0)
    full_output = torch.cat([torch.tensor([[1, 2, 3, 4, 5]]), generated], dim=1)
    model.generate.return_value = full_output
    return model


def _fake_tq_cls() -> MagicMock:
    return MagicMock(return_value=MagicMock())


def _fake_transformers_module(fake_tok, fake_model_inst) -> MagicMock:
    """Complete sys.modules replacement for transformers — no real import needed."""
    m = MagicMock()
    m.AutoTokenizer.from_pretrained.return_value = fake_tok
    m.AutoModelForCausalLM.from_pretrained.return_value = fake_model_inst
    m.TextIteratorStreamer = MagicMock
    return m


def _sys_modules_patch(fake_tok, fake_model_inst, tq):
    """patch.dict that blocks transformers + safetensors imports entirely."""
    fake_tf = _fake_transformers_module(fake_tok, fake_model_inst)
    fake_tq_mod = MagicMock(TurboQuantCache=tq)
    return patch.dict("sys.modules", {
        "transformers": fake_tf,
        "turboquant": fake_tq_mod,
        "safetensors": MagicMock(),
        "safetensors.torch": MagicMock(),
        "accelerate": MagicMock(),
    })


def _make_tq_engine(bits: int = 4):
    fake_tok = _fake_tokenizer()
    fake_model_inst = _fake_model()
    tq = _fake_tq_cls()

    with _sys_modules_patch(fake_tok, fake_model_inst, tq):
        from llm_engines.optimizations.turboquant import TurboQuantEngine
        engine = TurboQuantEngine.__new__(TurboQuantEngine)
        engine.model_name = "Qwen/Qwen2.5-32B-Instruct"
        engine.bits = bits
        engine._bits = bits
        engine._max_new_tokens = 512
        engine._tokenizer = fake_tok
        engine._model = fake_model_inst
        engine._tq_cache_cls = tq
        engine._torch = torch
        engine._transformers = MagicMock()
        return engine, fake_tok, fake_model_inst, tq


def _make_combo_engine(
    main: str = "Qwen/Qwen2.5-32B-Instruct",
    draft: str = "Qwen/Qwen2.5-1.5B-Instruct",
):
    fake_tok = _fake_tokenizer()
    fake_main = _fake_model()
    fake_draft = _fake_model()
    tq = _fake_tq_cls()

    from llm_engines.optimizations.combo import ComboEngine
    engine = ComboEngine.__new__(ComboEngine)
    engine.main_model_name = main
    engine.draft_model_name = draft
    engine.turboquant_bits = 4
    engine.num_speculative_tokens = 5
    engine._max_new_tokens = 512
    engine._total_tokens_generated = 0
    engine._total_draft_tokens_proposed = 0
    engine._total_draft_tokens_accepted = 0
    engine._tokenizer = fake_tok
    engine._main = fake_main
    engine._draft = fake_draft
    engine._tq_cache_cls = tq
    engine._torch = torch
    engine._transformers = MagicMock()
    return engine, fake_tok, fake_main, fake_draft, tq


def _no_grad_patch():
    m = MagicMock()
    m.__enter__ = lambda s: None
    m.__exit__ = lambda s, *a: None
    return patch("torch.no_grad", return_value=m)


# ---------------------------------------------------------------------------
# TurboQuantEngine tests
# ---------------------------------------------------------------------------

class TestTurboQuantEngine:

    def test_invalid_bits_raises(self) -> None:
        from llm_engines.contracts import EngineConfigError
        with _sys_modules_patch(MagicMock(), MagicMock(), MagicMock()):
            from llm_engines.optimizations.turboquant import TurboQuantEngine
            engine = TurboQuantEngine.__new__(TurboQuantEngine)
            with pytest.raises(EngineConfigError, match="bits must be 2, 3, or 4"):
                engine.__init__("model", bits=8)

    def test_capabilities(self) -> None:
        engine, *_ = _make_tq_engine()
        caps = engine.get_capabilities()
        assert caps.chat is True
        assert caps.streaming is True
        assert caps.embeddings is False
        assert caps.logprobs is False
        assert caps.kv_cache_compression is True
        assert "turboquant" in caps.kv_cache_compression_modes
        assert caps.speculative_decoding is False

    def test_generate_returns_response(self) -> None:
        engine, *_ = _make_tq_engine()
        with _no_grad_patch():
            resp = engine.generate(GenerationRequest(
                messages=[ChatMessage(role="user", content="Hello")]
            ))
        assert isinstance(resp, GenerationResponse)
        assert resp.message.role == "assistant"
        assert "turboquant" in resp.backend
        assert resp.usage.input_tokens == 5
        assert len(resp.active_optimizations) == 1
        assert resp.active_optimizations[0].kind == "kv_cache_compression"
        assert resp.active_optimizations[0].parameters["bits"] == engine.bits

    def test_tq_cache_created_with_correct_bits(self) -> None:
        engine, _, _, tq = _make_tq_engine(bits=3)
        with _no_grad_patch():
            engine.generate(GenerationRequest(
                messages=[ChatMessage(role="user", content="Hi")]
            ))
        tq.assert_called_once_with(bits=3)

    def test_empty_messages_raises(self) -> None:
        from llm_engines.contracts import GenerationError
        engine, *_ = _make_tq_engine()
        with pytest.raises(GenerationError):
            engine.generate(GenerationRequest(messages=[]))

    def test_backend_includes_bit_width(self) -> None:
        engine, *_ = _make_tq_engine(bits=4)
        with _no_grad_patch():
            resp = engine.generate(GenerationRequest(
                messages=[ChatMessage(role="user", content="Hi")]
            ))
        assert "4bit" in resp.backend


# ---------------------------------------------------------------------------
# ComboEngine tests
# ---------------------------------------------------------------------------

class TestComboEngine:

    def test_capabilities(self) -> None:
        engine, *_ = _make_combo_engine()
        caps = engine.get_capabilities()
        assert caps.chat is True
        assert caps.streaming is True
        assert caps.speculative_decoding is True
        assert caps.kv_cache_compression is True
        assert "turboquant" in caps.kv_cache_compression_modes

    def test_generate_returns_response(self) -> None:
        engine, *_ = _make_combo_engine()
        with _no_grad_patch():
            resp = engine.generate(GenerationRequest(
                messages=[ChatMessage(role="user", content="What is 2+2?")]
            ))
        assert isinstance(resp, GenerationResponse)
        assert resp.backend == "combo_tq_speculative"
        assert [item.kind for item in resp.active_optimizations] == ["speculative_decoding", "kv_cache_compression"]
        assert resp.active_optimizations[0].parameters["draft_model"] == engine.draft_model_name

    def test_generate_passes_assistant_model(self) -> None:
        engine, _, main, draft, _ = _make_combo_engine()
        with _no_grad_patch():
            engine.generate(GenerationRequest(
                messages=[ChatMessage(role="user", content="Hi")]
            ))
        assert main.generate.call_args[1]["assistant_model"] is draft

    def test_generate_passes_tq_cache(self) -> None:
        engine, _, main, _, tq = _make_combo_engine()
        tq_instance = MagicMock()
        tq.return_value = tq_instance
        with _no_grad_patch():
            engine.generate(GenerationRequest(
                messages=[ChatMessage(role="user", content="Hi")]
            ))
        assert main.generate.call_args[1]["past_key_values"] is tq_instance

    def test_model_name_describes_both_models(self) -> None:
        engine, *_ = _make_combo_engine()
        with _no_grad_patch():
            resp = engine.generate(GenerationRequest(
                messages=[ChatMessage(role="user", content="Hi")]
            ))
        assert "Qwen2.5-32B" in resp.model_name
        assert "Qwen2.5-1.5B" in resp.model_name
        assert "tq4bit" in resp.model_name

    def test_empty_messages_raises(self) -> None:
        from llm_engines.contracts import GenerationError
        engine, *_ = _make_combo_engine()
        with pytest.raises(GenerationError):
            engine.generate(GenerationRequest(messages=[]))

    def test_get_stats_returns_config(self) -> None:
        engine, *_ = _make_combo_engine()
        stats = engine.get_stats()
        assert stats["turboquant_bits"] == 4
        assert stats["num_speculative_tokens"] == 5
        assert stats["vram_compression_ratio"] == "4.0x"

    def test_invalid_bits_raises_at_construction(self) -> None:
        from llm_engines.contracts import EngineConfigError
        from llm_engines.optimizations.combo import ComboEngine
        engine = ComboEngine.__new__(ComboEngine)
        with pytest.raises(EngineConfigError):
            engine.__init__("main", "draft", turboquant_bits=8)

    def test_oom_error_gives_helpful_message(self) -> None:
        from llm_engines.contracts import GenerationError
        engine, _, main, _, _ = _make_combo_engine()
        main.generate.side_effect = RuntimeError("CUDA out of memory")
        with _no_grad_patch():
            with pytest.raises(GenerationError, match="OOM"):
                engine.generate(GenerationRequest(
                    messages=[ChatMessage(role="user", content="Hi")]
                ))


@pytest.mark.slow
class TestComboEngineLive:
    """Live tests — require GPU, model files, and turboquant package."""

    def test_combo_small_models(self) -> None:
        from llm_engines.optimizations.combo import ComboEngine
        engine = ComboEngine(
            main_model="Qwen/Qwen2.5-7B-Instruct",
            draft_model="Qwen/Qwen2.5-1.5B-Instruct",
            turboquant_bits=4,
            num_speculative_tokens=5,
        )
        resp = engine.generate(GenerationRequest(
            messages=[ChatMessage(
                role="user",
                content="What is 2+2? Reply with just the number."
            )],
            max_tokens=10,
            temperature=0.0,
        ))
        assert resp.message.content is not None
        assert "4" in resp.message.content
        print(f"\nLatency: {resp.usage.latency_ms:.0f}ms")
        print(f"Stats: {engine.get_stats()}")
