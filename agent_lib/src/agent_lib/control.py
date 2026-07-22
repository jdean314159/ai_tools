"""Runtime control-hook adapters."""

from __future__ import annotations

from typing import Literal, Sequence

from action_trajectory_loop_guard import assess_trajectory

from .contracts import AgentRun, AgentStep, AgentTask, ContinueRun, ControlDirective, FinalizeOnce


class ActionTrajectoryGuardHook:
    """Translate pure action-loop advice into a runtime finalization directive."""

    def __init__(self, *, mode: Literal["shadow", "enforce"] = "enforce") -> None:
        if mode not in {"shadow", "enforce"}:
            raise ValueError("action guard mode must be 'shadow' or 'enforce'")
        self.mode = mode

    def after_step(
        self,
        task: AgentTask,
        trajectory: Sequence[AgentStep],
        run: AgentRun,
    ) -> ControlDirective:
        assessment = assess_trajectory(trajectory)
        intervention = assessment.intervention
        detector_metadata = {
            "detector_schema_version": assessment.schema_version,
            "detector_action": assessment.actions[-1] if assessment.actions else None,
            "detector_decision": (
                assessment.action_assessments[-1] if assessment.action_assessments else None
            ),
        }
        if intervention is None:
            return ContinueRun(
                metadata={
                    "control_hook": "action_trajectory_loop_guard",
                    "mode": self.mode,
                    "fired": False,
                    **detector_metadata,
                }
            )
        intervention_metadata = {
            "control_hook": "action_trajectory_loop_guard",
            "mode": self.mode,
            "loop_start_action": intervention.loop_start_action,
            "confirmation_actions": intervention.confirmation_actions,
            "evidence_novelty": intervention.evidence_novelty,
            "repeated_action": intervention.repeated_action,
            "truncation_point": intervention.truncation_point,
            "instruction": intervention.instruction,
            **detector_metadata,
        }
        if self.mode == "shadow":
            return ContinueRun(metadata={**intervention_metadata, "fired": False, "would_fire": True})
        return FinalizeOnce(
            truncation_point=intervention.truncation_point,
            instruction=intervention.instruction,
            metadata=intervention_metadata,
        )
