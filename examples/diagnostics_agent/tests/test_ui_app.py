from __future__ import annotations

from types import SimpleNamespace


def test_ui_app_imports_without_streamlit_server() -> None:
    from diagnostics_agent.ui import app

    assert callable(app.main)


def test_render_result_warns_when_sandbox_read_was_truncated() -> None:
    from diagnostics_agent import SandboxResult, Severity
    from diagnostics_agent.ui import app

    fake_st = _FakeStreamlit()
    result = SimpleNamespace(
        collected=SimpleNamespace(byte_count=20, command=["journalctl", "-o", "json"]),
        sandbox_result=SandboxResult(
            argv=["podman", "run"],
            inner_command=["cat", "/staging/collected.log"],
            stdout="",
            stderr="",
            exit_code=0,
            duration_s=0.1,
            timed_out=False,
            truncated=True,
        ),
        summary=SimpleNamespace(
            parsed_lines=1,
            unparsed_lines=0,
            severity_counts={Severity.WARNING: 1},
            findings=(),
            top_clusters=(),
        ),
        interpretation=SimpleNamespace(
            security_risk="none",
            operational_risk="low",
            summary="No security issue.",
            prioritized_concerns=[],
            recommended_checks=[],
        ),
        audit={},
    )

    app._render_result(fake_st, result)

    assert any("truncated to the most recent 16 MiB" in warning for warning in fake_st.warnings)


def test_render_engine_choice_sets_llamacpp_flash_attn() -> None:
    from diagnostics_agent.ui import app

    fake_st = _FakeEngineChoiceStreamlit()

    choice = app._render_engine_choice(fake_st, vram=None)

    assert choice is not None
    assert choice.backend == "llamacpp"
    assert choice.model == "/models/qwen.gguf"
    assert choice.n_gpu_layers == -1
    assert choice.n_ctx == 8192
    assert choice.n_batch == 128
    assert choice.n_ubatch is None
    assert choice.cache_type_k == "q8_0"
    assert choice.cache_type_v == "q8_0"
    assert choice.flash_attn is True
    assert choice.think is False


def test_optional_ollama_fallback_preserves_think_flag() -> None:
    from diagnostics_agent.engine_select import EngineChoice
    from diagnostics_agent.ui import app

    fake_st = _FakeFallbackStreamlit()
    choice = EngineChoice("llamacpp", "/models/qwen.gguf", think=False)

    rebuilt = app._with_optional_ollama_fallback(
        fake_st,
        choice,
        models=[],
        default_model="qwen3:8b",
    )

    assert rebuilt.think is False
    assert rebuilt.fallback is not None
    assert rebuilt.fallback.backend == "ollama"


class _FakeColumn:
    def metric(self, _label, _value) -> None:
        return None


class _FakeExpander:
    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        return None


class _FakeStreamlit:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def subheader(self, _text) -> None:
        return None

    def columns(self, count):
        if isinstance(count, int):
            return [_FakeColumn() for _ in range(count)]
        return [_FakeColumn() for _ in count]

    def code(self, _body, language=None) -> None:
        return None

    def caption(self, _body) -> None:
        return None

    def markdown(self, _body) -> None:
        return None

    def warning(self, body) -> None:
        self.warnings.append(body)

    def write(self, _body) -> None:
        return None

    def expander(self, _label):
        return _FakeExpander()

    def json(self, _body) -> None:
        return None

    def download_button(self, _label, *, data, file_name, mime) -> None:
        return None


class _FakeEngineChoiceStreamlit:
    def caption(self, _body) -> None:
        return None

    def selectbox(self, label, options, index=0, disabled=False):
        if label == "Backend":
            return "llamacpp"
        if label in {"KV cache K type", "KV cache V type"}:
            return "q8_0"
        return options[index]

    def radio(self, _label, _options):
        return "Custom GGUF path"

    def number_input(self, label, **_kwargs):
        if label == "n_gpu_layers":
            return -1
        if label == "n_ctx":
            return 8192
        if label == "n_batch":
            return 128
        if label == "n_ubatch":
            return None
        raise AssertionError(f"unexpected number input: {label}")

    def checkbox(self, label):
        return label in {
            "Set n_ctx",
            "Enable flash attention (required for quantized V cache)",
        }

    def text_input(self, label, value=""):
        if label == "GGUF path":
            return "/models/qwen.gguf"
        return value


class _FakeFallbackStreamlit:
    def checkbox(self, label):
        assert label == "Fall back to another Ollama on failure"
        return True

    def text_input(self, label, value=""):
        assert label == "Fallback Ollama base URL"
        return value
