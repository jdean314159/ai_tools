from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol, Sequence

from llm_inspector import EvidenceItem, Trace

ActionKind = Literal["tool", "final", "message"]
StopReason = Literal["completed", "max_steps", "planner_stop", "error", "critic_completed", "token_budget", "context_limit"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResult:
    name: str
    output: Any
    success: bool = True
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentAction:
    kind: ActionKind
    message: str = ""
    tool_call: ToolCall | None = None
    final_output: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def tool(
        cls,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        message: str = "",
        meta: dict[str, Any] | None = None,
    ) -> "AgentAction":
        return cls(
            kind="tool",
            message=message,
            tool_call=ToolCall(name=name, arguments=dict(arguments or {})),
            meta=dict(meta or {}),
        )

    @classmethod
    def final(cls, output: str, *, meta: dict[str, Any] | None = None) -> "AgentAction":
        return cls(kind="final", final_output=output, message=output, meta=dict(meta or {}))

    @classmethod
    def message_only(cls, message: str, *, meta: dict[str, Any] | None = None) -> "AgentAction":
        return cls(kind="message", message=message, meta=dict(meta or {}))


@dataclass(frozen=True)
class AgentObservation:
    kind: str
    text: str
    tool_result: ToolResult | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EngineRoles:
    planner: str | None = None
    executor: str | None = None
    critic: str | None = None
    fallback: str | None = None


@dataclass(frozen=True)
class AgentTask:
    task_id: str
    goal: str
    session_id: str = "default"
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentStep:
    index: int
    action: AgentAction
    observation: AgentObservation | None = None
    trace: Trace | None = None


@dataclass(frozen=True)
class AgentContext:
    task: AgentTask
    steps: Sequence[AgentStep]
    recalled: Sequence[EvidenceItem] = field(default_factory=tuple)
    memory_trace: Trace | None = None
    tool_specs: Sequence[ToolSpec] = field(default_factory=tuple)
    engine_roles: EngineRoles = field(default_factory=EngineRoles)
    active_controller: str = "planner"
    escalated: bool = False


@dataclass
class AgentRun:
    task: AgentTask
    steps: list[AgentStep] = field(default_factory=list)
    status: str = "running"
    stop_reason: StopReason | None = None
    final_output: str | None = None
    engine_roles: EngineRoles = field(default_factory=EngineRoles)
    meta: dict[str, Any] = field(default_factory=dict)
    escalations: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    elapsed_seconds: float | None = None


class AgentRunLifecycleHook(Protocol):
    def on_start(self, task: AgentTask, *, max_steps: int, engine_roles: EngineRoles) -> None: ...
    def on_step(self, task: AgentTask, context: AgentContext, step: AgentStep, run: AgentRun) -> None: ...
    def on_finish(self, run: AgentRun) -> None: ...


RetryActionPayload = dict[str, Any]


class AgentContextBuilder(Protocol):
    def build_context(
        self,
        task: AgentTask,
        steps: Sequence[AgentStep],
        *,
        active_controller: str,
        escalated: bool,
        memory: AgentMemoryAdapter,
        tool_specs: Sequence[ToolSpec],
        engine_roles: EngineRoles,
    ) -> AgentContext: ...

class Planner(Protocol):
    def plan(self, context: AgentContext) -> AgentAction: ...


class ToolRuntime(Protocol):
    def list_tools(self) -> list[ToolSpec]: ...
    def invoke(self, call: ToolCall) -> ToolResult: ...


class AgentMemoryAdapter(Protocol):
    backend_name: str

    def recall(self, task: AgentTask, steps: Sequence[AgentStep], *, limit: int = 5) -> list[EvidenceItem]: ...
    def record_step(self, task: AgentTask, step: AgentStep) -> None: ...
    def trace_recall(self, task: AgentTask, steps: Sequence[AgentStep], *, limit: int = 5) -> Trace | None: ...


class AgentTraceEmitter(Protocol):
    def emit_step(
        self,
        *,
        context: AgentContext,
        action: AgentAction,
        observation: AgentObservation | None,
    ) -> Trace: ...
