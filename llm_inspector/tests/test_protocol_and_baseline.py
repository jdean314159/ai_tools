from llm_inspector.augmenters import BaselineAugmenter
from llm_inspector.protocols import AugmentRequest, ContextAugmenter
from llm_inspector.core import Turn


def test_baseline_conforms_to_protocol():
    aug = BaselineAugmenter()
    assert isinstance(aug, ContextAugmenter)

    trace = aug.augment(AugmentRequest(turn=Turn(role="user", text="hello")))
    assert trace.turn.role == "user"
    assert len(trace.context.sections) == 2
    assert trace.context.sections[0].origin == "system"
    assert trace.context.sections[1].origin == "user"


def test_baseline_token_accounting_is_deterministic():
    aug = BaselineAugmenter(system_prompt="a b c")
    trace = aug.augment(AugmentRequest(turn=Turn(role="user", text="d e")))
    assert trace.context.token_accounting.total_tokens == 5
