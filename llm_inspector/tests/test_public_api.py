from llm_inspector import (
    AdapterRegistry,
    AdapterSpec,
    AugmentRequest,
    BaselineAugmenter,
    CompareBundle,
    ComparisonReport,
    ContextInspector,
    ContextResult,
    ContextAugmenter,
    DiffReport,
    EvidenceItem,
    Section,
    TokenAccounting,
    Trace,
    TraceEvent,
    Turn,
    build_bundle,
    bundle_to_json,
    diff_traces,
    render_comparison,
    render_diff,
    report_to_json,
    describe_inspector,
    trace_to_operation_result,
)


def test_top_level_public_api_exposes_core_workflow():
    aug = BaselineAugmenter()
    inspector = ContextInspector([aug])
    report = inspector.run("hello world")

    assert isinstance(report, ComparisonReport)
    assert isinstance(report.traces[0].trace, Trace)
    assert isinstance(report.traces[0].trace.turn, Turn)
    assert isinstance(report.traces[0].trace.context, ContextResult)
    assert isinstance(report.traces[0].trace.context.sections[0], Section)
    assert isinstance(report.traces[0].trace.context.token_accounting, TokenAccounting)

    bundle = build_bundle(report)
    assert isinstance(bundle, CompareBundle)
    assert isinstance(report_to_json(report), str)
    assert isinstance(bundle_to_json(bundle), str)
    assert isinstance(render_comparison(report), str)
    assert isinstance(
        render_diff(
            diff_traces(report.traces[0].trace, report.traces[0].trace, name_a="a", name_b="b")
        ),
        str,
    )


def test_top_level_types_are_importable():
    assert AdapterRegistry is not None
    assert AdapterSpec is not None
    assert AugmentRequest is not None
    assert BaselineAugmenter is not None
    assert ContextAugmenter is not None
    assert DiffReport is not None
    assert EvidenceItem is not None
    assert TraceEvent is not None
    assert describe_inspector is not None
    assert trace_to_operation_result is not None


def test_rag_exports_are_lazy_and_listed_in_dir():
    import sys
    import llm_inspector

    # Any adapter imported at module level may have already loaded llm_inspector.rag
    # as a side effect during this pytest session.  Reset the relevant entries so the
    # test checks the lazy-load contract in isolation, not session history.
    _rag_names = ("RAGInspector", "EngramRAGAdapter", "ChromaDBRAGAdapter")
    for name in _rag_names:
        llm_inspector.__dict__.pop(name, None)
    sys.modules.pop("llm_inspector.rag", None)
    sys.modules.pop("engram", None)

    assert "RAGInspector" in dir(llm_inspector)
    assert "llm_inspector.rag" not in sys.modules
