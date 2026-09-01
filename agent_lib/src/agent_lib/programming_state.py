from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any

from .contracts import AgentContext, AgentRun, AgentStep, AgentTask
from .programming_contracts import (
    FailurePolicy,
    PatchProposal,
    PlanStatus,
    PlanStep,
    ProgrammingTask,
    VerificationResult,
)


@dataclass
class ProgrammingTaskState:
    task_id: str
    goal: str
    session_id: str
    status: str = "pending"
    current_step_id: str | None = None
    plan: list[PlanStep] = field(default_factory=list)
    step_count: int = 0
    retry_counts: dict[str, int] = field(default_factory=dict)
    touched_files: list[str] = field(default_factory=list)
    repeated_tool_calls: dict[str, int] = field(default_factory=dict)
    last_verification: VerificationResult | None = None
    last_patch: PatchProposal | None = None
    last_error: str | None = None
    last_policy_decision: str | None = None
    context_window_index: int = 0
    final_output: str | None = None
    escalations: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "session_id": self.session_id,
            "status": self.status,
            "current_step_id": self.current_step_id,
            "plan": [asdict(step) for step in self.plan],
            "step_count": self.step_count,
            "retry_counts": dict(self.retry_counts),
            "touched_files": list(self.touched_files),
            "repeated_tool_calls": dict(self.repeated_tool_calls),
            "last_verification": asdict(self.last_verification)
            if self.last_verification is not None
            else None,
            "last_patch": asdict(self.last_patch) if self.last_patch is not None else None,
            "last_error": self.last_error,
            "last_policy_decision": self.last_policy_decision,
            "context_window_index": self.context_window_index,
            "final_output": self.final_output,
            "escalations": self.escalations,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ProgrammingTaskState":
        plan = [PlanStep(**item) for item in list(payload.get("plan") or [])]
        last_verification = payload.get("last_verification")
        last_patch = payload.get("last_patch")
        return cls(
            task_id=str(payload.get("task_id") or ""),
            goal=str(payload.get("goal") or ""),
            session_id=str(payload.get("session_id") or "default"),
            status=str(payload.get("status") or "pending"),
            current_step_id=payload.get("current_step_id"),
            plan=plan,
            step_count=int(payload.get("step_count") or 0),
            retry_counts={
                str(k): int(v) for k, v in dict(payload.get("retry_counts") or {}).items()
            },
            touched_files=[str(item) for item in list(payload.get("touched_files") or [])],
            repeated_tool_calls={
                str(k): int(v) for k, v in dict(payload.get("repeated_tool_calls") or {}).items()
            },
            last_verification=VerificationResult(**last_verification)
            if isinstance(last_verification, dict)
            else None,
            last_patch=PatchProposal(**last_patch) if isinstance(last_patch, dict) else None,
            last_error=payload.get("last_error"),
            last_policy_decision=payload.get("last_policy_decision"),
            context_window_index=int(payload.get("context_window_index") or 0),
            final_output=payload.get("final_output"),
            escalations=int(payload.get("escalations") or 0),
        )


class ProgrammingTaskStateStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, task_id: str) -> Path:
        safe = str(task_id or "task").strip().replace("/", "_")
        return self.root / f"{safe}.json"

    def load(self, task_id: str) -> ProgrammingTaskState | None:
        path = self.path_for(task_id)
        if not path.exists():
            return None
        return ProgrammingTaskState.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save(self, state: ProgrammingTaskState) -> ProgrammingTaskState:
        path = self.path_for(state.task_id)
        path.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return state

    def initialize(self, task: ProgrammingTask) -> ProgrammingTaskState:
        existing = self.load(task.task_id)
        if existing is not None:
            return existing
        state = ProgrammingTaskState(
            task_id=task.task_id,
            goal=task.goal,
            session_id=task.session_id,
            status="running",
            plan=list(task.plan),
        )
        return self.save(state)


class ProgrammingStateTracker:
    def __init__(
        self,
        store: ProgrammingTaskStateStore,
        task: ProgrammingTask,
        *,
        failure_policy: FailurePolicy | None = None,
    ) -> None:
        self.store = store
        self.task = task
        self.failure_policy = failure_policy or FailurePolicy()
        self.state = self.store.initialize(task)

    def _touch_file(self, path: str) -> None:
        norm = str(path).strip()
        if norm and norm not in self.state.touched_files:
            self.state.touched_files.append(norm)

    def _set_step_status(
        self, step_id: str | None, status: PlanStatus, note: str | None = None
    ) -> None:
        if not step_id:
            return
        updated: list[PlanStep] = []
        for step in self.state.plan:
            if step.step_id != step_id:
                updated.append(step)
                continue
            notes = list(step.notes)
            if note and note not in notes:
                notes.append(note)
            updated.append(
                PlanStep(
                    step_id=step.step_id, description=step.description, status=status, notes=notes
                )
            )
        self.state.plan = updated
        self.state.current_step_id = step_id

    def attach_to_context(self, context: dict[str, Any]) -> dict[str, Any]:
        out = dict(context)
        out["programming_state"] = self.state.to_dict()
        out["failure_policy"] = asdict(self.failure_policy)
        return out

    def on_start(self, task: AgentTask, *, max_steps: int, engine_roles: Any) -> None:
        self.state.status = "running"
        if self.state.step_count > 0:
            self.state.context_window_index += 1
        policy_note = str(task.context.get("_programming_policy_note") or "").strip()
        if policy_note:
            self.state.last_policy_decision = policy_note
        task.context.update(self.attach_to_context(task.context))
        self.store.save(self.state)

    def on_step(
        self, task: AgentTask, context: AgentContext, step: AgentStep, run: AgentRun
    ) -> None:
        self.state.step_count = len(run.steps)
        self.state.escalations = run.escalations
        step_id = str(step.action.meta.get("plan_step_id") or "").strip() or None
        if step_id is not None:
            self._set_step_status(step_id, "in_progress")

        if step.action.tool_call is not None:
            call = step.action.tool_call
            signature = f"{call.name}:{json.dumps(call.arguments, sort_keys=True)}"
            self.state.repeated_tool_calls[signature] = (
                self.state.repeated_tool_calls.get(signature, 0) + 1
            )
            path = call.arguments.get("path")
            if isinstance(path, str):
                self._touch_file(path)
            if call.name == "replace_text":
                patch_status = "proposed"
                if (
                    step.observation
                    and step.observation.tool_result
                    and step.observation.tool_result.success
                ):
                    patch_status = str(
                        step.observation.tool_result.meta.get("patch_status") or "applied"
                    )
                self.state.last_patch = PatchProposal(
                    path=str(call.arguments.get("path") or ""),
                    old=str(call.arguments.get("old") or ""),
                    new=str(call.arguments.get("new") or ""),
                    rationale=str(step.action.message or ""),
                    status=patch_status
                    if patch_status in {"proposed", "applied", "rejected"}
                    else "proposed",
                )

        if step.observation and step.observation.tool_result is not None:
            tool_result = step.observation.tool_result
            if tool_result.name in {"run_check", "run_command"}:
                self.state.last_verification = VerificationResult(
                    step_id=step_id or "verification",
                    success=bool(tool_result.success),
                    summary=str(tool_result.output),
                    command=str(
                        tool_result.meta.get("command")
                        or tool_result.meta.get("must_contain")
                        or ""
                    ),
                )
            if not tool_result.success:
                self.state.last_error = str(tool_result.output)
                if step_id is not None:
                    self.state.retry_counts[step_id] = self.state.retry_counts.get(step_id, 0) + 1
                    self._set_step_status(step_id, "failed", note=str(tool_result.output))
            elif step_id is not None:
                self._set_step_status(step_id, "completed", note=str(tool_result.output))
        elif step.action.kind == "final":
            if step_id is not None:
                self._set_step_status(
                    step_id, "completed", note=step.action.final_output or step.action.message
                )

        task.context.update(self.attach_to_context(task.context))
        self.store.save(self.state)

    def on_finish(self, run: AgentRun) -> None:
        self.state.status = str(run.status)
        self.state.escalations = run.escalations
        self.state.final_output = run.final_output
        self.state.step_count = len(run.steps)
        policy_note = str(run.task.context.get("_programming_policy_note") or "").strip()
        if policy_note:
            self.state.last_policy_decision = policy_note
        run.task.context.update(self.attach_to_context(run.task.context))
        self.store.save(self.state)
