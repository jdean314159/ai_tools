from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..contracts import (
    AgentContext,
    AgentContextBuilder,
    AgentStep,
    AgentTask,
    EngineRoles,
    ToolResult,
    ToolSpec,
)
from .navigation_contracts import NavigationConfigurationError


@dataclass(frozen=True)
class NoWriteContextConfig:
    max_visible_steps: int = 8
    max_tool_output_chars: int = 8_000
    summary_max_chars: int = 8_000

    def __post_init__(self) -> None:
        if (
            self.max_visible_steps < 1
            or self.max_tool_output_chars < 1
            or self.summary_max_chars < 1
        ):
            raise NavigationConfigurationError("No-write context limits must be positive")


class NoWriteContextBuilder(AgentContextBuilder):
    def __init__(self, config: NoWriteContextConfig | None = None) -> None:
        self.config = config or NoWriteContextConfig()

    def _bounded_step(self, step: AgentStep) -> AgentStep:
        observation = step.observation
        if observation is None or len(observation.text) <= self.config.max_tool_output_chars:
            return step
        from ..contracts import AgentObservation

        bounded_text = (
            observation.text[: self.config.max_tool_output_chars].rstrip()
            + "\n... [tool result truncated]"
        )
        tool_result = observation.tool_result
        if tool_result is not None:
            tool_result = ToolResult(
                name=tool_result.name,
                output=bounded_text,
                success=tool_result.success,
                meta=dict(tool_result.meta),
            )
        bounded_observation = AgentObservation(
            kind=observation.kind,
            text=bounded_text,
            tool_result=tool_result,
            meta=dict(observation.meta),
        )
        return AgentStep(
            index=step.index, action=step.action, observation=bounded_observation, trace=step.trace
        )

    def build_context(
        self,
        task: AgentTask,
        steps: Sequence[AgentStep],
        *,
        active_controller: str,
        escalated: bool,
        memory: Any,
        tool_specs: Sequence[ToolSpec],
        engine_roles: EngineRoles,
    ) -> AgentContext:
        all_steps = list(steps)
        recent = [self._bounded_step(step) for step in all_steps[-self.config.max_visible_steps :]]
        older = (
            all_steps[: -self.config.max_visible_steps]
            if len(all_steps) > self.config.max_visible_steps
            else []
        )
        summary_lines: list[str] = []
        for step in older:
            label = step.action.tool_call.name if step.action.tool_call else step.action.kind
            outcome = step.observation.text if step.observation else step.action.message
            summary_lines.append(f"step {step.index}: {label} -> {str(outcome)[:400]}")
        summary = "\n".join(summary_lines)
        if len(summary) > self.config.summary_max_chars:
            summary = summary[-self.config.summary_max_chars :]
        managed_task = AgentTask(
            task_id=task.task_id,
            goal=task.goal,
            session_id=task.session_id,
            context={
                **dict(task.context),
                "context_budget": {
                    "history_summary": summary,
                    "visible_step_count": len(recent),
                    "compacted_step_count": len(older),
                    "artifacts": [],
                },
            },
        )
        return AgentContext(
            task=managed_task,
            steps=recent,
            recalled=(),
            tool_specs=list(tool_specs),
            engine_roles=engine_roles,
            active_controller=active_controller,
            escalated=escalated,
        )
