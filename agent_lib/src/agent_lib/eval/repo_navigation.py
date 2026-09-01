from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from llm_engines.contracts import (
    ChatModel,
)

from ..contracts import (
    AgentRun,
    AgentTask,
)
from ..memory import NullMemoryAdapter
from ..runtime import AgentRuntime
from ..control import ActionTrajectoryGuardHook
from .navigation_claims import (
    NAVIGATION_CLAIMS_SCHEMA,
    navigation_claims_shape_error,
)
from .navigation_ground_truth import (
    GroundTruthRegion as _GroundTruthRegion,
    LEAD_QUESTION,
    load_ground_truth as _load_ground_truth,
    validate_ground_truth_snapshot as _validate_ground_truth_snapshot,
)
from .navigation_contracts import NavigationConfigurationError
from .navigation_context import (
    NoWriteContextBuilder,
    NoWriteContextConfig as _NoWriteContextConfig,
)
from .navigation_model_transport import (
    HuggingFaceModelTokenizer as _HuggingFaceModelTokenizer,
    LlamaServerClient as _LlamaServerClient,
    ModelTokenizer,
)
from .navigation_planner import (
    BudgetedNavigationPlanner,
    FINALIZATION_ACTION_SCHEMA as _FINALIZATION_ACTION_SCHEMA,
    FINALIZATION_SYSTEM_PROMPT as _FINALIZATION_SYSTEM_PROMPT,
    NAVIGATION_ACTION_SCHEMA as _NAVIGATION_ACTION_SCHEMA,
    NavigationBudget,
    NavigationRunHook,
    PlannerUsage as _PlannerUsage,
    STRUCTURED_NAVIGATION_ACTION_SCHEMA as _STRUCTURED_NAVIGATION_ACTION_SCHEMA,
    SYSTEM_PROMPT as _SYSTEM_PROMPT,
    navigation_action_schema as _navigation_action_schema,
)
from .navigation_artifacts import (
    build_environment_manifest as _build_environment_manifest,
    render_run_record as _render_run_record,
    tree_content_digest as _tree_content_digest,
)
from .navigation_scoring import score_navigation_run as _score_navigation_run
from .navigation_workspace import (
    NavigationPolicy,
    NavigationTelemetry as _NavigationTelemetry,
    NavigationToolRuntime,
    NavigationWorkspace,
)

load_ground_truth = _load_ground_truth
validate_ground_truth_snapshot = _validate_ground_truth_snapshot
HuggingFaceModelTokenizer = _HuggingFaceModelTokenizer
LlamaServerClient = _LlamaServerClient
NoWriteContextConfig = _NoWriteContextConfig
SYSTEM_PROMPT = _SYSTEM_PROMPT
FINALIZATION_SYSTEM_PROMPT = _FINALIZATION_SYSTEM_PROMPT
NAVIGATION_ACTION_SCHEMA = _NAVIGATION_ACTION_SCHEMA
STRUCTURED_NAVIGATION_ACTION_SCHEMA = _STRUCTURED_NAVIGATION_ACTION_SCHEMA
FINALIZATION_ACTION_SCHEMA = _FINALIZATION_ACTION_SCHEMA
navigation_action_schema = _navigation_action_schema
PlannerUsage = _PlannerUsage
GroundTruthRegion = _GroundTruthRegion
NavigationTelemetry = _NavigationTelemetry
score_navigation_run = _score_navigation_run
build_environment_manifest = _build_environment_manifest
tree_content_digest = _tree_content_digest
render_run_record = _render_run_record


@dataclass
class NavigationHarness:
    root: Path
    runtime: AgentRuntime
    planner: BudgetedNavigationPlanner
    tools: NavigationToolRuntime
    max_steps: int = 25
    action_guard_mode: str = "shadow"
    structured_navigation: bool = False

    def run(self, question: str = LEAD_QUESTION, *, task_id: str = "nav-test-00") -> AgentRun:
        return self.runtime.run(
            AgentTask(task_id=task_id, goal=question, context={"navigation_root": str(self.root)}),
            max_steps=self.max_steps,
        )


def build_navigation_harness(
    *,
    root: str | Path,
    engine: ChatModel,
    tokenizer: ModelTokenizer,
    policy: NavigationPolicy | None = None,
    budget: NavigationBudget | None = None,
    max_steps: int = 25,
    temperature: float = 0.0,
    metadata: dict[str, Any] | None = None,
    action_guard_mode: str = "shadow",
    structured_navigation: bool = False,
    navigation_goal_definitions: Sequence[tuple[str, str]] | None = None,
    system_prompt: str = SYSTEM_PROMPT,
    final_claim_name: str = "navigation_claims",
    final_claim_schema: Mapping[str, Any] = NAVIGATION_CLAIMS_SCHEMA,
    final_claim_validator: Callable[[object], str | None] = navigation_claims_shape_error,
    require_observed_evidence_before_final: bool = False,
) -> NavigationHarness:
    if max_steps < 1:
        raise NavigationConfigurationError("max_steps must be positive")
    if action_guard_mode not in {"off", "shadow", "enforce"}:
        raise NavigationConfigurationError("action_guard_mode must be one of: off, shadow, enforce")
    if structured_navigation and action_guard_mode != "off":
        raise NavigationConfigurationError("structured navigation requires action_guard_mode='off'")
    resolved_policy = policy or NavigationPolicy(Path(root))
    workspace = NavigationWorkspace(resolved_policy)
    tools = NavigationToolRuntime(workspace)
    planner = BudgetedNavigationPlanner(
        engine=engine,
        tokenizer=tokenizer,
        budget=budget,
        temperature=temperature,
        metadata=metadata,
        structured_navigation=structured_navigation,
        navigation_goal_definitions=navigation_goal_definitions,
        system_prompt=system_prompt,
        final_claim_name=final_claim_name,
        final_claim_schema=final_claim_schema,
        final_claim_validator=final_claim_validator,
        require_observed_evidence_before_final=require_observed_evidence_before_final,
    )
    control_hooks = (
        [] if action_guard_mode == "off" else [ActionTrajectoryGuardHook(mode=action_guard_mode)]
    )
    runtime = AgentRuntime(
        planner=planner,
        tool_runtime=tools,
        memory=NullMemoryAdapter(),
        context_builder=NoWriteContextBuilder(),
        lifecycle_hooks=[NavigationRunHook(planner)],
        control_hooks=control_hooks,
    )
    return NavigationHarness(
        root=resolved_policy.root,
        runtime=runtime,
        planner=planner,
        tools=tools,
        max_steps=max_steps,
        action_guard_mode=action_guard_mode,
        structured_navigation=structured_navigation,
    )
