from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .contracts import AgentTask
from .programming_workspace import WorkspacePolicy


PlanStatus = Literal["pending", "in_progress", "completed", "failed"]


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    description: str
    status: PlanStatus = "pending"
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class VerificationResult:
    step_id: str
    success: bool
    summary: str
    command: str | None = None


@dataclass(frozen=True)
class PatchProposal:
    path: str
    old: str
    new: str
    rationale: str = ""
    status: Literal["proposed", "applied", "rejected"] = "proposed"


@dataclass(frozen=True)
class ToolFailurePolicy:
    tool_name: str
    max_retries: int = 0
    failure_behavior: Literal["retry", "escalate", "stop"] = "stop"
    empty_behavior: Literal["retry", "escalate", "stop", "ignore"] = "stop"
    timeout_seconds: float | None = None


@dataclass(frozen=True)
class FailurePolicy:
    max_retries_per_step: int = 2
    stop_on_repeated_tool_calls: int = 2
    retryable_tools: list[str] = field(
        default_factory=lambda: ["read_file", "replace_text", "run_check", "run_command"]
    )
    stop_on_empty_result: bool = True
    tool_policies: list[ToolFailurePolicy] = field(
        default_factory=lambda: [
            ToolFailurePolicy(
                "read_file", max_retries=1, failure_behavior="retry", empty_behavior="stop"
            ),
            ToolFailurePolicy(
                "replace_text", max_retries=1, failure_behavior="retry", empty_behavior="retry"
            ),
            ToolFailurePolicy(
                "run_check", max_retries=0, failure_behavior="escalate", empty_behavior="escalate"
            ),
            ToolFailurePolicy(
                "run_command", max_retries=0, failure_behavior="escalate", empty_behavior="escalate"
            ),
        ]
    )

    def policy_for(self, tool_name: str) -> ToolFailurePolicy:
        normalized = str(tool_name or "").strip()
        for policy in self.tool_policies:
            if policy.tool_name == normalized:
                return policy
        default_behavior: Literal["retry", "escalate", "stop"] = (
            "retry" if normalized in self.retryable_tools else "stop"
        )
        return ToolFailurePolicy(
            tool_name=normalized or "tool",
            max_retries=self.max_retries_per_step if normalized in self.retryable_tools else 0,
            failure_behavior=default_behavior,
            empty_behavior="stop" if self.stop_on_empty_result else "ignore",
        )


@dataclass(frozen=True)
class ProgrammingTask:
    task_id: str
    goal: str
    session_id: str = "default"
    workspace: WorkspacePolicy = field(default_factory=WorkspacePolicy)
    plan: list[PlanStep] = field(default_factory=list)
    verification_commands: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_agent_task(self) -> AgentTask:
        return AgentTask(
            task_id=self.task_id,
            goal=self.goal,
            session_id=self.session_id,
            context={
                "workspace_policy": asdict(self.workspace),
                "plan": [asdict(step) for step in self.plan],
                "verification_commands": list(self.verification_commands),
                **dict(self.metadata),
            },
        )
