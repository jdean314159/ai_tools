from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from llm_inspector_ui.state.models import RunArtifact
from llm_inspector_ui.state.session_store import SessionStore


@dataclass
class RunPlan:
    session_id: str
    user_text: str
    engine_id: str
    model_id: Optional[str]
    augmenter_ids: list[str] = field(default_factory=lambda: ["baseline"])

    engine_config: dict[str, Any] = field(default_factory=dict)
    engine_settings: dict[str, Any] = field(default_factory=dict)
    augmenter_options: dict[str, dict[str, Any]] = field(default_factory=dict)

    max_prompt_tokens: Optional[int] = None
    reserve_output_tokens: int = 512


class WorkbenchOrchestrator:
    def __init__(
        self,
        *,
        session_store: SessionStore,
        engine_service: Any,
        augmenter_service: Any,
        inspector_service: Any,
    ):
        self.session_store = session_store
        self.engine_service = engine_service
        self.augmenter_service = augmenter_service
        self.inspector_service = inspector_service

    def run(self, plan: RunPlan) -> list[RunArtifact]:
        mode = "compare" if len(plan.augmenter_ids) > 1 else "chat"

        user_turn = self.session_store.add_turn(
            plan.session_id,
            "user",
            plan.user_text,
            meta={"mode": mode},
        )

        history_turns = self.session_store.list_turns(plan.session_id)
        prior_turns = history_turns[:-1] if history_turns else []

        engine = self.engine_service.create_engine(plan.engine_id, plan.engine_config)

        artifacts: list[RunArtifact] = []

        for augmenter_id in plan.augmenter_ids:
            assistant_turn_id: Optional[str] = None
            branch_options = plan.augmenter_options.get(augmenter_id, {})
            branch_readiness = self.augmenter_service.get_augmenter_readiness(
                augmenter_id,
                options=branch_options,
            )

            if not branch_readiness.can_run:
                artifact = RunArtifact(
                    run_id=str(uuid4()),
                    session_id=plan.session_id,
                    turn_id=user_turn.turn_id,
                    assistant_turn_id=None,
                    created_at=datetime.now(timezone.utc),
                    engine_id=plan.engine_id,
                    model_id=plan.model_id,
                    augmenter_id=augmenter_id,
                    mode=mode,
                    status="skipped",
                    user_text=plan.user_text,
                    prompt="",
                    response_text="",
                    trace=None,
                    engine_metrics={},
                    settings=self._artifact_settings(
                        plan,
                        branch_options=branch_options,
                        branch_readiness=branch_readiness,
                    ),
                    error=branch_readiness.message,
                )
                self.session_store.save_run(artifact)
                artifacts.append(artifact)
                continue

            try:
                augmenter = self.augmenter_service.create(
                    augmenter_id,
                    session_id=plan.session_id,
                    options=branch_options,
                )

                augmenter.new_session(plan.session_id)
                for turn in prior_turns:
                    augmenter.add_turn(turn.role, turn.text, plan.session_id)

                augment_result = augmenter.augment(request=self._make_augment_request(plan))
                normalized_trace = self.inspector_service.inspect(
                    augmenter_id=augmenter_id,
                    augment_result=augment_result,
                    user_text=plan.user_text,
                    session_id=plan.session_id,
                )

                response = engine.invoke(
                    prompt=augment_result.prompt,
                    model_id=plan.model_id,
                    settings=plan.engine_settings,
                    session_id=plan.session_id,
                )

                response_text = self._response_text(response)
                response_metrics = self._response_metrics(response)

                if mode == "chat":
                    assistant_turn = self.session_store.add_turn(
                        plan.session_id,
                        "assistant",
                        response_text,
                        meta={
                            "augmenter_id": augmenter_id,
                            "engine_id": plan.engine_id,
                            "model_id": plan.model_id,
                        },
                    )
                    assistant_turn_id = assistant_turn.turn_id

                artifact = RunArtifact(
                    run_id=str(uuid4()),
                    session_id=plan.session_id,
                    turn_id=user_turn.turn_id,
                    assistant_turn_id=assistant_turn_id,
                    created_at=datetime.now(timezone.utc),
                    engine_id=plan.engine_id,
                    model_id=plan.model_id,
                    augmenter_id=augmenter_id,
                    mode=mode,
                    status="ok",
                    user_text=plan.user_text,
                    prompt=augment_result.prompt,
                    response_text=response_text,
                    trace=normalized_trace,
                    engine_metrics=response_metrics,
                    settings=self._artifact_settings(plan, branch_options=branch_options),
                    error=None,
                )
            except Exception as exc:
                artifact = RunArtifact(
                    run_id=str(uuid4()),
                    session_id=plan.session_id,
                    turn_id=user_turn.turn_id,
                    assistant_turn_id=assistant_turn_id,
                    created_at=datetime.now(timezone.utc),
                    engine_id=plan.engine_id,
                    model_id=plan.model_id,
                    augmenter_id=augmenter_id,
                    mode=mode,
                    status="error",
                    user_text=plan.user_text,
                    prompt="",
                    response_text="",
                    trace=None,
                    engine_metrics={},
                    settings=self._artifact_settings(plan, branch_options=branch_options),
                    error=f"{type(exc).__name__}: {exc}",
                )

            self.session_store.save_run(artifact)
            artifacts.append(artifact)

        return artifacts

    def _artifact_settings(
        self,
        plan: RunPlan,
        *,
        branch_options: dict[str, Any],
        branch_readiness: Any | None = None,
    ) -> dict[str, Any]:
        settings = {
            "engine_config": copy.deepcopy(plan.engine_config),
            "engine_settings": copy.deepcopy(plan.engine_settings),
            "augmenter_options": copy.deepcopy(branch_options),
            "augmenter_options_all": copy.deepcopy(plan.augmenter_options),
            "selected_augmenter_ids": list(plan.augmenter_ids),
            "max_prompt_tokens": plan.max_prompt_tokens,
            "reserve_output_tokens": plan.reserve_output_tokens,
        }
        if branch_readiness is not None:
            settings["branch_readiness"] = {
                "augmenter_id": branch_readiness.augmenter_id,
                "can_run": branch_readiness.can_run,
                "severity": branch_readiness.severity,
                "message": branch_readiness.message,
                "details": copy.deepcopy(branch_readiness.details),
            }
        return settings

    def _make_augment_request(self, plan: RunPlan):
        from engram.contracts import AugmentRequest

        return AugmentRequest(
            session_id=plan.session_id,
            user_text=plan.user_text,
            query=plan.user_text,
            max_prompt_tokens=plan.max_prompt_tokens,
            reserve_output_tokens=plan.reserve_output_tokens,
        )

    def _response_text(self, response: Any) -> str:
        if isinstance(response, dict):
            for key in ("text", "content", "message", "response"):
                value = response.get(key)
                if isinstance(value, str):
                    return value
            return str(response)

        for attr in ("text", "content", "message", "response"):
            value = getattr(response, attr, None)
            if isinstance(value, str):
                return value

        return str(response)

    def _response_metrics(self, response: Any) -> dict[str, Any]:
        if isinstance(response, dict):
            value = response.get("metrics")
            return value if isinstance(value, dict) else {}

        value = getattr(response, "metrics", None)
        return value if isinstance(value, dict) else {}
