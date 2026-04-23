from __future__ import annotations

from pathlib import Path

from llm_inspector import EngramLiteAugmenter
from llm_inspector.protocols import AugmentRequest
from llm_inspector.core import Turn


def test_engram_lite_adapter_returns_trace(tmp_path: Path) -> None:
    augmenter = EngramLiteAugmenter(base_dir=tmp_path / 'memory', project_id='inspector_demo', max_prompt_tokens=256)
    trace = augmenter.augment(
        AugmentRequest(
            turn=Turn(role='user', text='Remember that I prefer Spanish drills.', session_id='s1'),
            query='Spanish drills preference',
            session_id='s1',
        )
    )
    assert trace.metrics.engine == 'engram_lite'
    assert trace.context.sections
    assert any(section.title in {'System', 'User', 'Final prompt'} for section in trace.context.sections)
    assert trace.events[0].event_type == 'prompt_build_completed'
    assert trace.events[0].kind == 'prompt_build_completed'
    assert trace.events[0].source_package == 'engram_lite'
