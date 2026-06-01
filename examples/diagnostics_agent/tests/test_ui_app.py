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
