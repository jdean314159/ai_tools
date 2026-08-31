from __future__ import annotations

from llm_harness_core import CapabilityDescriptor, CapabilityKind
from llm_inspector_ui.panels.startup_panel import _agent_execution_capability_rows
from llm_inspector_ui.utils.trace_access import (
    get_agent_events,
    get_agent_execution_rows,
    get_agent_execution_summary,
    get_agent_summary,
)


def test_trace_access_returns_agent_summary_and_events():
    trace = {
        "context": {
            "signals": {
                "agent_summary": {
                    "active_controller": "planner",
                    "tool_count": 2,
                },
            }
        },
        "events": [
            {
                "event_type": "agent_tool_result",
                "source_package": "agent_lib",
                "source_component": "InspectorTraceEmitter",
                "payload": {"kind": "tool_result", "text": "5"},
                "tags": ["agent", "tool", "observation"],
            }
        ],
    }
    assert get_agent_summary(trace)["tool_count"] == 2
    assert get_agent_events(trace)[0]["event_type"] == "agent_tool_result"


def test_trace_access_derives_agent_execution_summary_from_events():
    trace = {
        "context": {
            "signals": {"agent_summary": {"active_controller": "planner", "tool_count": 1}}
        },
        "events": [
            {
                "event_type": "agent_tool_result",
                "source_package": "agent_lib",
                "payload": {
                    "tool_result": {
                        "name": "run_command",
                        "success": False,
                        "meta": {
                            "error": "command_denied",
                            "approval_required": True,
                            "sandbox_requested_backend": "docker",
                            "sandbox_backend": "host",
                            "sandbox_fallback_used": True,
                        },
                    }
                },
                "tags": ["agent", "tool", "observation", "approval", "blocked", "degraded"],
            }
        ],
    }
    summary = get_agent_execution_summary(trace)
    rows = get_agent_execution_rows(trace)
    assert summary["blocked_count"] == 1
    assert summary["degraded_count"] == 1
    assert summary["approval_count"] == 1
    assert rows[0]["tool_name"] == "run_command"
    assert rows[0]["blocked"] is True
    assert rows[0]["degraded"] is True


def test_startup_panel_extracts_agent_execution_capability_rows():
    rows = _agent_execution_capability_rows(
        [
            CapabilityDescriptor(
                kind=CapabilityKind.TOOL_PROVIDER,
                provider="agent_lib",
                component="ProgrammingToolRuntime",
                version="0.1.0",
                summary="Programming runtime",
                features=("approval_gates",),
                input_types=(),
                output_types=(),
                metadata={
                    "blocked_execution_reporting": True,
                    "degraded_execution_reporting": True,
                },
            )
        ]
    )
    assert rows and rows[0]["provider"] == "agent_lib"
    assert rows[0]["blocked_execution_reporting"] is True
    assert rows[0]["degraded_execution_reporting"] is True
    assert rows[0]["approval_gates"] is True
