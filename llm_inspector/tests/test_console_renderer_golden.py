from __future__ import annotations

from pathlib import Path

from llm_inspector.augmenters import BaselineAugmenter
from llm_inspector.inspectors import ContextInspector
from llm_inspector.renderers import render_comparison

GOLDEN = Path(__file__).parent / "golden_compare.txt"


def test_console_renderer_golden():
    a1 = BaselineAugmenter(system_prompt="You are a helpful assistant.", _name="baseline_a")
    a2 = BaselineAugmenter(system_prompt="You are a strict assistant.", _name="baseline_b")

    insp = ContextInspector([a1, a2])
    report = insp.run("hello world")

    out = render_comparison(report)

    if not GOLDEN.exists():
        GOLDEN.write_text(out, encoding="utf-8")
        assert GOLDEN.exists()
        return

    expected = GOLDEN.read_text(encoding="utf-8")
    assert out == expected
