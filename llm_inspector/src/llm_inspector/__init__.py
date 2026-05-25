"""
llm_inspector

Observability layer for LLM workflows. Normalizes traces from engines, memory
augmentation, and retrieval into a common model so runs can be inspected,
diffed, and exported.

Does not run inference itself — it inspects what other packages produce.

Quick start:
    from llm_inspector import ContextInspector, BaselineAugmenter, AugmentRequest, Turn

    inspector = ContextInspector()
    augmenter = BaselineAugmenter()
    req = AugmentRequest(turn=Turn(role="user", text="What is RAG?"), session_id="s1")
    trace = augmenter.augment(req)
    inspector.add(trace, label="baseline")
    report = inspector.compare()
    print(render_comparison(report))

With engram memory:
    from llm_inspector import make_engram
    augmenter = make_engram(base_dir="~/.myapp", project_id="demo")
"""

from importlib import import_module
from typing import Any

from llm_inspector.adapters import AdapterRegistry, AdapterSpec
from llm_inspector.adapters.engram_adapter import EngramAugmenter, make_engram
from llm_inspector.augmenters import BaselineAugmenter
from llm_inspector.core import (
    ContextResult,
    EvidenceItem,
    RunMetrics,
    Section,
    TokenAccounting,
    Trace,
    TraceEvent,
    Turn,
)
from llm_inspector.export import (
    bundle_to_dict,
    bundle_to_json,
    diff_to_dict,
    diff_to_json,
    report_to_dict,
    report_to_json,
)
from llm_inspector.inspectors import (
    CompareBundle,
    ComparisonReport,
    ContextInspector,
    DiffReport,
    NamedTrace,
    build_bundle,
    diff_traces,
)
from llm_inspector.interop import (
    describe_inspector,
    report_to_operation_result,
    trace_to_interop_events,
    trace_to_memory_records,
    trace_to_operation_result,
)
from llm_inspector.protocols import AugmentRequest, ContextAugmenter
from llm_inspector.renderers import render_comparison, render_diff

__version__ = "0.1.0"

_LAZY_EXPORTS = {
    "RAGInspector": ("llm_inspector.rag", "RAGInspector"),
    "EngramRAGAdapter": ("llm_inspector.rag", "EngramRAGAdapter"),
    "ChromaDBRAGAdapter": ("llm_inspector.rag", "ChromaDBRAGAdapter"),
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_EXPORTS:
        module_name, attr_name = _LAZY_EXPORTS[name]
        module = import_module(module_name)
        value = getattr(module, attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


__all__ = [
    "__version__",
    # Core trace model
    "Turn",
    "EvidenceItem",
    "Section",
    "TokenAccounting",
    "RunMetrics",
    "ContextResult",
    "TraceEvent",
    "Trace",
    # Augmenter protocol and baseline implementation
    "AugmentRequest",
    "ContextAugmenter",
    "BaselineAugmenter",
    # Inspector workflows
    "NamedTrace",
    "ComparisonReport",
    "ContextInspector",
    "DiffReport",
    "CompareBundle",
    "diff_traces",
    "build_bundle",
    # Exporters and renderers
    "report_to_dict",
    "report_to_json",
    "diff_to_dict",
    "diff_to_json",
    "bundle_to_dict",
    "bundle_to_json",
    "render_comparison",
    "render_diff",
    # Interop helpers
    "describe_inspector",
    "trace_to_operation_result",
    "trace_to_interop_events",
    "trace_to_memory_records",
    "report_to_operation_result",
    # Adapter registry and engram integration
    "AdapterSpec",
    "AdapterRegistry",
    "EngramAugmenter",
    "make_engram",
    # RAG utilities (lazy; require rag_lib installed)
    "RAGInspector",
    "EngramRAGAdapter",
    "ChromaDBRAGAdapter",
]
