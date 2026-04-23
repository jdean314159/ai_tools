from __future__ import annotations

from pathlib import Path

from llm_inspector.augmenters import BaselineAugmenter
from llm_inspector.inspectors import ContextInspector
from llm_inspector.inspectors.diff import diff_traces
from llm_inspector.renderers.diff_console import render_diff

GOLDEN = Path(__file__).parent / "golden_diff.txt"


def test_diff_golden():
    a = BaselineAugmenter(system_prompt="You are a helpful assistant.", _name="a")
    b = BaselineAugmenter(system_prompt="You are a strict assistant.", _name="b")
    insp = ContextInspector([a, b])
    report = insp.run("hello world")

    ta = report.traces[0].trace
    tb = report.traces[1].trace

    diff = diff_traces(ta, tb, name_a="a", name_b="b")
    out = render_diff(diff)

    if not GOLDEN.exists():
        GOLDEN.write_text(out, encoding="utf-8")
        assert GOLDEN.exists()
        return

    assert out == GOLDEN.read_text(encoding="utf-8")