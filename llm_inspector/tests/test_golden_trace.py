from __future__ import annotations

from pathlib import Path

from llm_inspector.core import ContextResult, Section, TokenAccounting, Trace, Turn
from llm_inspector.core.serialize import to_json

GOLDEN = Path(__file__).parent / "golden_trace.json"


def _make_sample_trace() -> Trace:
    turn = Turn(role="user", text="Summarize what cold storage does.")
    sections = [
        Section(title="System", text="You are a helpful assistant.", origin="system", tokens=8),
        Section(title="Working memory", text="(recent turns...)", origin="working", tokens=5),
        Section(title="User", text=turn.text, origin="user", tokens=7),
    ]
    accounting = TokenAccounting(
        target_tokens=2048,
        total_tokens=20,
        per_origin_budget={"working": 800},
        per_origin_used={"working": 5},
        truncated=False,
        compressed=False,
        notes=["sample fixture"],
    )
    ctx = ContextResult(sections=sections, token_accounting=accounting)
    return Trace(turn=turn, context=ctx)


def test_golden_trace_stable():
    trace = _make_sample_trace()
    payload = to_json(trace)

    if not GOLDEN.exists():
        GOLDEN.write_text(payload, encoding="utf-8")
        # First run creates fixture; subsequent runs enforce stability.
        assert GOLDEN.exists()
        return

    expected = GOLDEN.read_text(encoding="utf-8")
    assert payload == expected
