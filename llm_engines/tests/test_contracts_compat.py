import llm_engines.contracts as contracts_module
from llm_engines.contracts import EngineDescriptor, ProvisionResult


def test_compat_contracts_module_reexports_canonical_registry_types():
    assert contracts_module.EngineDescriptor is EngineDescriptor
    assert contracts_module.ProvisionResult is ProvisionResult
