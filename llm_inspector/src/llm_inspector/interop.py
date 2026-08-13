from __future__ import annotations

from llm_harness_core import CapabilityDescriptor, CapabilityKind, MemoryRecord, OperationResult, TraceEvent

from .inspectors import ComparisonReport


def describe_inspector(component: object | None = None) -> CapabilityDescriptor:
    component_name = component.__class__.__name__ if component is not None else "ContextInspector"
    return CapabilityDescriptor(
        kind=CapabilityKind.INSPECTOR,
        provider="llm_inspector",
        component=component_name,
        version="0.1.0",
        summary="Observability and comparison workflows for augmentation traces.",
        features=(
            "compare",
            "diff",
            "bundle",
            "trace_export",
            "console_rendering",
            "run_artifact_inspection",
            "run_artifact_comparison",
        ),
        input_types=("trace", "comparison_report", "run_artifact"),
        output_types=("operation_result", "trace_event[]", "json_report"),
        metadata={},
    )


def trace_to_operation_result(trace) -> OperationResult[dict]:
    return trace.to_interop_result()


def trace_to_interop_events(trace) -> list[TraceEvent]:
    return trace.to_interop_events()


def trace_to_memory_records(trace) -> list[MemoryRecord]:
    return [item.to_memory_record() for item in trace.context.evidence]


def report_to_operation_result(report: ComparisonReport) -> OperationResult[dict]:
    value = {
        "query": report.query,
        "traces": [
            {
                "name": named.name,
                "trace": named.trace.to_interop_result().value,
            }
            for named in report.traces
        ],
    }
    diagnostics = {
        "trace_count": len(report.traces),
        "adapters": [named.name for named in report.traces],
    }
    return OperationResult.success(value, diagnostics=diagnostics)
