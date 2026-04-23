from llm_inspector.adapters import AdapterRegistry, AdapterSpec
from llm_inspector.protocols import ContextAugmenter


def test_registry_creates_baseline_adapter():
    reg = AdapterRegistry()
    reg.register(AdapterSpec("baseline", "llm_inspector.adapters.baseline:make_baseline"))

    aug = reg.create("baseline", _name="baseline")
    assert isinstance(aug, ContextAugmenter)
    assert aug.name == "baseline"
