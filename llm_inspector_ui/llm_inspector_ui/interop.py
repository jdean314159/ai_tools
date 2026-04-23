from __future__ import annotations

from typing import Any

from llm_harness_core import CapabilityDescriptor, CapabilityKind, OperationResult


def describe_ui(component: object | None = None) -> CapabilityDescriptor:
    component_name = component.__class__.__name__ if component is not None else "LLMInspectorUI"
    return CapabilityDescriptor(
        kind=CapabilityKind.UI,
        provider="llm_inspector_ui",
        component=component_name,
        version="0.1.0",
        summary="Interactive UI for engine selection, trace inspection, and compare workflows.",
        features=(
            "trace_visualization",
            "capability_inspection",
            "compare_runs",
            "model_selection",
            "startup_diagnostics",
        ),
        input_types=("trace", "operation_result", "capability_descriptor"),
        output_types=("streamlit_view", "json_bundle"),
        metadata={},
    )


def artifact_to_operation_result(artifact: Any) -> OperationResult[dict[str, Any]]:
    trace = getattr(artifact, "trace", None)
    if isinstance(trace, dict):
        return OperationResult.success(
            trace,
            diagnostics={
                "run_id": getattr(artifact, "run_id", None),
                "augmenter_id": getattr(artifact, "augmenter_id", None),
                "engine_id": getattr(artifact, "engine_id", None),
                "status": getattr(artifact, "status", None),
            },
        )

    return OperationResult.failure(
        code="missing_trace",
        message="Run artifact does not contain a serialized trace.",
        details={
            "run_id": getattr(artifact, "run_id", None),
            "status": getattr(artifact, "status", None),
        },
    )
