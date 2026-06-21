"""
agent_lib — EXPERIMENTAL

Inspectable agent-orchestration layer for the ai_tools stack.

**This package is experimental. The API may change without notice between
releases. Do not build production systems on it.**

Core workflow:
    from agent_lib import AgentRuntime, AgentTask, LLMActionPlanner, RoleEngineSet
    from llm_engines import get_engine

    engines = RoleEngineSet(planner=get_engine("ollama", "qwen3:27b"),
                            executor=get_engine("ollama", "qwen3:8b"))
    planner = LLMActionPlanner(engines=engines)
    runtime = AgentRuntime(planner=planner)
    task = AgentTask(goal="Summarize the repo README", context={})
    run = runtime.run(task)

For deterministic testing, use SequencePlanner instead of LLMActionPlanner.
"""

# --- Contracts (stable within experimental tier) ---
from .contracts import (
    AgentAction,
    AgentContext,
    AgentObservation,
    AgentRun,
    AgentStep,
    AgentTask,
    AgentTraceEmitter,
    EngineRoles,
    Planner,
    StopReason,
    ToolCall,
    ToolResult,
    ToolRuntime,
    ToolSpec,
)

# --- Coordination / mailbox ---
from .coordination import (
    CoordinationMessage,
    ExternalAgentSession,
    ExternalAgentTeam,
    ExternalSessionCoordinator,
    FileReservation,
    InMemoryMailbox,
    SessionMailbox,
    build_coordinator_tool_runtime,
    build_session_tool_runtime,
    route_by_capability,
)

# --- Memory adapters ---
from .memory import (
    EngramLiteMemoryAdapter,  # deprecated alias — use EngramMemoryAdapter
    EngramMemoryAdapter,
    NullMemoryAdapter,
    create_memory_adapter,
)

# --- Planners ---
from .planners import SequencePlanner
from .llm_engines_adapter import LLMActionPlanner, RoleEngineSet, action_from_payload, extract_json_object

# --- Runtime ---
from .runtime import AgentRuntime, InspectorTraceEmitter

# --- Tools ---
from .tools import LocalTool, LocalToolRuntime

# --- Interop ---
from .interop import (
    describe_agent_runtime,
    describe_tool_runtime,
    run_to_interop_events,
    run_to_memory_records,
    run_to_operation_result,
    step_to_interop_events,
    tool_result_to_operation_result,
)

# --- Programming task module (advanced; import from agent_lib.programming directly) ---
from .programming import (
    ProgrammingTask,
    ProgrammingRuntimeConfig,
    ProgrammingRoleBindings,
    WorkspacePolicy,
    build_programming_task,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # Contracts
    "AgentAction",
    "AgentContext",
    "AgentObservation",
    "AgentRun",
    "AgentStep",
    "AgentTask",
    "AgentTraceEmitter",
    "EngineRoles",
    "Planner",
    "StopReason",
    "ToolCall",
    "ToolResult",
    "ToolRuntime",
    "ToolSpec",
    # Coordination
    "CoordinationMessage",
    "ExternalAgentSession",
    "ExternalAgentTeam",
    "ExternalSessionCoordinator",
    "FileReservation",
    "InMemoryMailbox",
    "SessionMailbox",
    "build_coordinator_tool_runtime",
    "build_session_tool_runtime",
    "route_by_capability",
    # Memory adapters
    "EngramMemoryAdapter",
    "NullMemoryAdapter",
    "create_memory_adapter",
    # Planners and action execution
    "SequencePlanner",
    "LLMActionPlanner",
    "RoleEngineSet",
    "action_from_payload",
    "extract_json_object",
    # Runtime
    "AgentRuntime",
    "InspectorTraceEmitter",
    # Tools
    "LocalTool",
    "LocalToolRuntime",
    # Interop
    "describe_agent_runtime",
    "describe_tool_runtime",
    "run_to_interop_events",
    "run_to_memory_records",
    "run_to_operation_result",
    "step_to_interop_events",
    "tool_result_to_operation_result",
    # Programming task (core types only; builders/runners in agent_lib.programming)
    "ProgrammingTask",
    "ProgrammingRuntimeConfig",
    "ProgrammingRoleBindings",
    "WorkspacePolicy",
    "build_programming_task",
]
