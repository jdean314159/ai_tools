from __future__ import annotations

from collections.abc import Mapping
import copy
from dataclasses import asdict, dataclass, field
import json
from typing import Any, Callable, Sequence

from llm_engines.contracts import (
    ChatMessage,
    ChatModel,
    GenerationRequest,
    GenerationResponse,
)

from ..contracts import (
    AgentAction,
    AgentContext,
    AgentRun,
    AgentRunLifecycleHook,
    AgentStep,
    AgentTask,
    EngineRoles,
)
from ..llm_engines_adapter import action_from_payload, extract_json_object
from .navigation_claims import NAVIGATION_CLAIMS_SCHEMA, navigation_claims_shape_error
from .navigation_contracts import NavigationConfigurationError
from .navigation_goals import (
    NAVIGATION_GOAL_STATE_SCHEMA,
    NavigationGoal,
    seed_navigation_goals,
    validate_goal_transition,
)
from .navigation_model_transport import ModelTokenizer
from .navigation_workspace import NAVIGATION_TOOL_SCHEMAS


SYSTEM_PROMPT = """You are a read-only repository navigation agent. Use evidence from tools only.
Return exactly one JSON object and no surrounding text.

Available actions:
1. {"kind":"tool","tool_name":"list_files","arguments":{"path":".","glob":"*.py","max_results":200},"message":"..."}
2. {"kind":"tool","tool_name":"grep","arguments":{"pattern":"...","path":".","glob":"*.py","max_matches":50},"message":"..."}
3. {"kind":"tool","tool_name":"read_file","arguments":{"path":"...","start_line":1,"line_count":200,"full":false},"message":"..."}
4. {"kind":"final","final_output":"Evidence-grounded answer.","navigation_claims":[{"path":"relative/file.py","symbol":"Class.method","operation":"exact observed operation","classification":"requested category","evidence":[{"path":"relative/file.py","start_line":10,"end_line":12}]}]}

Never request a write or execute operation. Do not guess locations. Search narrowly, inspect enough
context to classify each result, and finish when the requested set is complete. In the final answer,
list only qualifying locations; do not name excluded candidate paths. For every location, state the
symbol or operation and its requested classification. Every final claim must cite line ranges
actually returned by a successful tool result. Use an empty navigation_claims list only when the
evidence proves there are no qualifying locations. For grep evidence cite each matching line as a
single-line range (start_line equals end_line); never expand a sparse hit into an unread method
range. The symbol must be an exact enclosing class/function name visible in evidence. If a call's
enclosing symbol is not visible, inspect it before finalizing rather than inventing a symbol. Report
only direct storage mutation call sites, not indirect helper invocations.

Tool rules:
- `glob` is a filename pattern such as `*.py`; put directories in `path`, never in `glob`.
- For a slice, use `full=false` with `start_line` and `line_count`.
- For a whole file, use `full=true` and omit `start_line` and `line_count`; a whole-file read is
  refused if it exceeds the visible result cap.
- Every action must use `kind="tool"` or `kind="final"`; a tool name never belongs in `kind`."""

FINALIZATION_SYSTEM_PROMPT = """You are finalizing a read-only repository navigation task.
Use only the evidence already present in the supplied history. No tools are available and you must
not request another search or file read. Return exactly one JSON object with this shape and no
surrounding text: {"kind":"final","final_output":"Evidence-grounded answer.","navigation_claims":[{"path":"relative/file.py","symbol":"Class.method","operation":"exact observed operation","classification":"requested category","evidence":[{"path":"relative/file.py","start_line":10,"end_line":12}]}]}

The final answer must identify qualifying file paths, symbols or operations, and their requested
classification. Cite only contiguous lines actually present in the supplied history; use a
single-line reference for a sparse grep hit. Use exact enclosing symbols visible in evidence.
Do not invent evidence, infer indirect call sites, or mention excluded candidates."""

NAVIGATION_ACTION_SCHEMA: dict[str, Any] = {
    "oneOf": [
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "kind": {"type": "string", "enum": ["tool"]},
                "tool_name": {"type": "string", "enum": ["read_file", "grep", "list_files"]},
                "arguments": {"type": "object"},
                "message": {"type": "string"},
            },
            "required": ["kind", "tool_name", "arguments"],
        },
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "kind": {"type": "string", "enum": ["final"]},
                "final_output": {"type": "string", "minLength": 1},
                "navigation_claims": NAVIGATION_CLAIMS_SCHEMA,
            },
            "required": ["kind", "final_output", "navigation_claims"],
        },
    ]
}


def _structured_navigation_schema() -> dict[str, Any]:
    schema = copy.deepcopy(NAVIGATION_ACTION_SCHEMA)
    for branch in schema["oneOf"]:
        branch["properties"]["navigation_goals"] = NAVIGATION_GOAL_STATE_SCHEMA
        branch["required"].append("navigation_goals")
        if branch["properties"]["kind"]["enum"] == ["tool"]:
            branch["properties"]["serves_goal_ids"] = {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string", "minLength": 1},
            }
            branch["required"].append("serves_goal_ids")
    return schema


STRUCTURED_NAVIGATION_ACTION_SCHEMA = _structured_navigation_schema()


def navigation_action_schema(
    *,
    claim_name: str = "navigation_claims",
    claim_schema: Mapping[str, Any] = NAVIGATION_CLAIMS_SCHEMA,
    structured_navigation: bool = False,
) -> dict[str, Any]:
    """Build an action schema with one caller-selected final claim contract."""

    schema = copy.deepcopy(NAVIGATION_ACTION_SCHEMA)
    for branch in schema["oneOf"]:
        if branch["properties"]["kind"]["enum"] == ["final"]:
            branch["properties"].pop("navigation_claims")
            branch["required"].remove("navigation_claims")
            branch["properties"][claim_name] = copy.deepcopy(dict(claim_schema))
            branch["required"].append(claim_name)
        if structured_navigation:
            branch["properties"]["navigation_goals"] = copy.deepcopy(NAVIGATION_GOAL_STATE_SCHEMA)
            branch["required"].append("navigation_goals")
            if branch["properties"]["kind"]["enum"] == ["tool"]:
                branch["properties"]["serves_goal_ids"] = {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string", "minLength": 1},
                }
                branch["required"].append("serves_goal_ids")
    return schema


FINALIZATION_ACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "kind": {"type": "string", "enum": ["final"]},
        "final_output": {"type": "string", "minLength": 1},
        "navigation_claims": NAVIGATION_CLAIMS_SCHEMA,
    },
    "required": ["kind", "final_output", "navigation_claims"],
}


@dataclass(frozen=True)
class NavigationBudget:
    cumulative_token_limit: int = 120_000
    context_window: int = 40_000
    minimum_output_reserve: int = 512
    per_call_output_cap: int = 2_048

    def __post_init__(self) -> None:
        values = (
            self.cumulative_token_limit,
            self.context_window,
            self.minimum_output_reserve,
            self.per_call_output_cap,
        )
        if any(value < 1 for value in values):
            raise NavigationConfigurationError("Navigation budget values must be positive")
        if self.minimum_output_reserve >= self.context_window:
            raise NavigationConfigurationError(
                "minimum_output_reserve must be smaller than context_window"
            )


@dataclass
class PlannerUsage:
    calls: list[dict[str, Any]] = field(default_factory=list)
    cumulative_actual_tokens: int = 0
    fallback_usage_calls: int = 0
    stop_reason: str | None = None


def _observed_lines(steps: Sequence[AgentStep]) -> dict[str, set[int]]:
    observed: dict[str, set[int]] = {}
    for step in steps:
        observation = step.observation
        result = observation.tool_result if observation is not None else None
        if result is None or not result.success:
            continue
        for item in result.meta.get("evidence") or []:
            if not isinstance(item, Mapping) or not isinstance(item.get("path"), str):
                continue
            observed.setdefault(str(item["path"]), set()).update(
                int(line) for line in item.get("lines") or [] if isinstance(line, int)
            )
    return observed


class BudgetedNavigationPlanner:
    allowed_tools = frozenset({"read_file", "grep", "list_files"})

    def __init__(
        self,
        *,
        engine: ChatModel,
        tokenizer: ModelTokenizer,
        budget: NavigationBudget | None = None,
        temperature: float = 0.0,
        metadata: dict[str, Any] | None = None,
        structured_navigation: bool = False,
        navigation_goal_definitions: Sequence[tuple[str, str]] | None = None,
        system_prompt: str = SYSTEM_PROMPT,
        final_claim_name: str = "navigation_claims",
        final_claim_schema: Mapping[str, Any] = NAVIGATION_CLAIMS_SCHEMA,
        final_claim_validator: Callable[[object], str | None] = navigation_claims_shape_error,
        require_observed_evidence_before_final: bool = False,
    ) -> None:
        self.engine = engine
        self.tokenizer = tokenizer
        self.budget = budget or NavigationBudget()
        self.temperature = temperature
        self.metadata = dict(metadata or {})
        self.structured_navigation = structured_navigation
        self.navigation_goal_definitions = navigation_goal_definitions
        self.system_prompt = system_prompt
        self.final_claim_name = final_claim_name
        self.final_claim_validator = final_claim_validator
        self.require_observed_evidence_before_final = require_observed_evidence_before_final
        self.action_schema = navigation_action_schema(
            claim_name=final_claim_name,
            claim_schema=final_claim_schema,
            structured_navigation=structured_navigation,
        )
        self.usage = PlannerUsage()
        self.navigation_goals = (
            seed_navigation_goals(navigation_goal_definitions)
            if navigation_goal_definitions is not None
            else seed_navigation_goals()
        )

    def reset_navigation_goals(self) -> None:
        self.navigation_goals = (
            seed_navigation_goals(self.navigation_goal_definitions)
            if self.navigation_goal_definitions is not None
            else seed_navigation_goals()
        )

    def _context_history(self, context: AgentContext, *, heading: str) -> list[str]:
        parts: list[str] = []
        history_summary = dict(context.task.context.get("context_budget") or {}).get(
            "history_summary"
        )
        if history_summary:
            parts.append(f"Earlier bounded history:\n{history_summary}")
        if not context.steps:
            return parts

        rendered: list[str] = []
        for step in context.steps:
            if step.action.tool_call:
                rendered.append(
                    f"Step {step.index} request: {step.action.tool_call.name} "
                    f"{json.dumps(step.action.tool_call.arguments, sort_keys=True)}"
                )
            else:
                rendered.append(
                    f"Step {step.index} action: {step.action.kind} {step.action.message}"
                )
            if step.observation:
                rendered.append(f"Step {step.index} result: {step.observation.text}")
        parts.append(f"{heading}:\n" + "\n".join(rendered))
        return parts

    def _user_prompt(self, context: AgentContext) -> str:
        parts = [f"Task:\n{context.task.goal}"]
        if self.structured_navigation:
            parts.append(
                "Required navigation goals (return this complete ledger in "
                "`navigation_goals` on every action):\n"
                + json.dumps(
                    [goal.as_dict() for goal in self.navigation_goals],
                    indent=2,
                    sort_keys=True,
                )
            )
            parts.append(
                "A tool action must include `serves_goal_ids` naming open goals it "
                "advances. Resolve a goal only with exact observed evidence. Do not "
                "finalize while a goal is open; abandon only with an explicit reason."
            )
        parts.extend(self._context_history(context, heading="Recent tool history"))
        parts.append("Choose the next tool call or return the final answer as JSON.")
        return "\n\n".join(parts)

    def _finalization_user_prompt(self, context: AgentContext, instruction: str) -> str:
        parts = [f"Task:\n{context.task.goal}"]
        parts.extend(self._context_history(context, heading="Preserved tool history"))
        parts.append(f"Control instruction:\n{instruction}")
        parts.append("Return the final answer now. No tool action is permitted.")
        return "\n\n".join(parts)

    def _budget_stop(self, reason: str) -> AgentAction:
        self.usage.stop_reason = reason
        return AgentAction.final(
            f"Navigation stopped before model invocation: {reason}.",
            meta={"navigation_stop_reason": reason, "usage": asdict(self.usage)},
        )

    def _record_usage(
        self,
        response: GenerationResponse,
        *,
        prompt_tokens: int,
        max_output_tokens: int,
        system_prompt: str,
        user_prompt: str,
        phase: str | None = None,
    ) -> None:
        actual_input = response.usage.input_tokens
        actual_output = response.usage.output_tokens
        used_fallback = actual_input is None or actual_output is None
        if actual_input is None:
            actual_input = prompt_tokens
        if actual_output is None:
            actual_output = self.tokenizer.count_text(response.message.content or "")
        actual_total = int(actual_input) + int(actual_output)
        self.usage.cumulative_actual_tokens += actual_total
        if used_fallback:
            self.usage.fallback_usage_calls += 1
        call = {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "prompt_tokens_pre_call": prompt_tokens,
            "requested_max_output_tokens": max_output_tokens,
            "actual_input_tokens": actual_input,
            "actual_output_tokens": actual_output,
            "actual_total_tokens": actual_total,
            "backend_reported": not used_fallback,
            "model": response.model_name,
            "backend": response.backend,
            "finish_reason": response.finish_reason,
            "latency_ms": response.usage.latency_ms,
            "response_text": response.message.content or "",
        }
        if phase is not None:
            call["phase"] = phase
        self.usage.calls.append(call)

    def _validate_payload(self, payload: dict[str, Any]) -> str | None:
        kind = str(payload.get("kind") or "").strip().lower()
        if kind == "final":
            if not str(
                payload.get("final_output") or payload.get("output") or payload.get("message") or ""
            ).strip():
                return "final_output must be non-empty"
            claim_error = self.final_claim_validator(payload.get(self.final_claim_name))
            if claim_error:
                return claim_error
            return None
        if kind != "tool":
            return "kind must be tool or final"
        name = str(payload.get("tool_name") or payload.get("name") or "")
        if name not in self.allowed_tools:
            return f"tool_name must be one of {sorted(self.allowed_tools)}"
        arguments = payload.get("arguments") or payload.get("args") or {}
        if not isinstance(arguments, dict):
            return "arguments must be an object"
        schema = NAVIGATION_TOOL_SCHEMAS[name]
        allowed = set(schema.get("properties") or {})
        required = set(schema.get("required") or [])
        if set(arguments) - allowed:
            return f"unknown arguments for {name}: {sorted(set(arguments) - allowed)}"
        if required - set(arguments):
            return f"missing arguments for {name}: {sorted(required - set(arguments))}"
        for key, value in arguments.items():
            expected = schema["properties"][key].get("type")
            if expected == "string" and not isinstance(value, str):
                return f"{key} must be a string"
            if expected == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
                return f"{key} must be an integer"
            if expected == "boolean" and not isinstance(value, bool):
                return f"{key} must be a boolean"
        return None

    def plan(self, context: AgentContext) -> AgentAction:
        messages = [
            ChatMessage(role="system", content=self.system_prompt),
            ChatMessage(role="user", content=self._user_prompt(context)),
        ]
        prompt_tokens = self.tokenizer.count_messages(messages)
        remaining_cumulative = (
            self.budget.cumulative_token_limit - self.usage.cumulative_actual_tokens
        )
        if prompt_tokens + self.budget.minimum_output_reserve > remaining_cumulative:
            return self._budget_stop("token_budget")
        if prompt_tokens + self.budget.minimum_output_reserve > self.budget.context_window:
            return self._budget_stop("context_limit")
        max_output = min(
            self.budget.per_call_output_cap,
            remaining_cumulative - prompt_tokens,
            self.budget.context_window - prompt_tokens,
        )
        response = self.engine.generate(
            GenerationRequest(
                messages=messages,
                max_tokens=max_output,
                temperature=self.temperature,
                json_schema=self.action_schema,
                metadata={
                    **self.metadata,
                    "task_id": context.task.task_id,
                    "structured_navigation": self.structured_navigation,
                },
            )
        )
        self._record_usage(
            response,
            prompt_tokens=prompt_tokens,
            max_output_tokens=max_output,
            system_prompt=self.system_prompt,
            user_prompt=messages[1].content or "",
        )
        try:
            payload = extract_json_object(response.message.content or "")
        except (ValueError, json.JSONDecodeError) as exc:
            return AgentAction.message_only(
                f"Rejected invalid JSON action: {exc}", meta={"invalid_action": True}
            )
        validation_error = self._validate_payload(payload)
        if validation_error:
            return AgentAction.message_only(
                f"Rejected invalid action: {validation_error}", meta={"invalid_action": True}
            )
        if (
            self.require_observed_evidence_before_final
            and str(payload.get("kind") or "").strip().lower() == "final"
            and not _observed_lines(context.steps)
        ):
            return AgentAction.message_only(
                "Rejected final action before any source evidence was observed.",
                meta={"invalid_action": True, "missing_observed_evidence": True},
            )
        if self.structured_navigation:
            goal_error, proposed_goals = self._validate_goal_payload(payload, context)
            if goal_error:
                return AgentAction.message_only(
                    f"Rejected invalid navigation goals: {goal_error}",
                    meta={"invalid_action": True, "invalid_navigation_goals": True},
                )
            self.navigation_goals = proposed_goals
        return action_from_payload(payload, response=response, engine_role="planner")

    def _validate_goal_payload(
        self,
        payload: Mapping[str, Any],
        context: AgentContext,
    ) -> tuple[str | None, tuple[NavigationGoal, ...]]:
        raw_goals = payload.get("navigation_goals")
        if not isinstance(raw_goals, list) or not all(
            isinstance(item, Mapping) for item in raw_goals
        ):
            return "navigation_goals must be an array of objects", self.navigation_goals
        try:
            proposed = tuple(NavigationGoal.from_mapping(item) for item in raw_goals)
        except (TypeError, ValueError) as exc:
            return f"invalid navigation goal: {exc}", self.navigation_goals
        serves = payload.get("serves_goal_ids") or []
        if not isinstance(serves, list) or not all(isinstance(item, str) for item in serves):
            return "serves_goal_ids must be an array of strings", self.navigation_goals
        error = validate_goal_transition(
            proposed,
            previous=self.navigation_goals,
            observed_lines=_observed_lines(context.steps),
            action_kind=str(payload.get("kind") or ""),
            serves_goal_ids=serves,
        )
        return error, proposed

    def finalize(
        self,
        context: AgentContext,
        instruction: str,
        *,
        full_context: AgentContext | None = None,
    ) -> AgentAction:
        messages = [
            ChatMessage(role="system", content=FINALIZATION_SYSTEM_PROMPT),
            ChatMessage(role="user", content=self._finalization_user_prompt(context, instruction)),
        ]
        full_messages = [
            ChatMessage(role="system", content=FINALIZATION_SYSTEM_PROMPT),
            ChatMessage(
                role="user",
                content=self._finalization_user_prompt(full_context or context, instruction),
            ),
        ]
        prompt_tokens = self.tokenizer.count_messages(messages)
        full_prompt_tokens = self.tokenizer.count_messages(full_messages)
        remaining_cumulative = (
            self.budget.cumulative_token_limit - self.usage.cumulative_actual_tokens
        )
        required_minimum = prompt_tokens + self.budget.minimum_output_reserve
        telemetry = {
            "full_prompt_tokens": full_prompt_tokens,
            "truncated_prompt_tokens": prompt_tokens,
            "token_savings": full_prompt_tokens - prompt_tokens,
            "available_cumulative_tokens": remaining_cumulative,
            "available_context_tokens": self.budget.context_window,
            "required_minimum_tokens": required_minimum,
        }
        if required_minimum > remaining_cumulative or required_minimum > self.budget.context_window:
            blockers = []
            if required_minimum > remaining_cumulative:
                blockers.append("cumulative_token_limit")
            if required_minimum > self.budget.context_window:
                blockers.append("context_window")
            return AgentAction.message_only(
                "Insufficient safe budget for constrained finalization.",
                meta={
                    "finalization_outcome": "budget_unavailable",
                    "budget_blockers": blockers,
                    **telemetry,
                },
            )

        max_output = min(
            self.budget.per_call_output_cap,
            remaining_cumulative - prompt_tokens,
            self.budget.context_window - prompt_tokens,
        )
        response = self.engine.generate(
            GenerationRequest(
                messages=messages,
                max_tokens=max_output,
                temperature=0.0,
                json_schema=FINALIZATION_ACTION_SCHEMA,
                metadata={
                    **self.metadata,
                    "task_id": context.task.task_id,
                    "phase": "guard_finalization",
                    "tools_enabled": False,
                },
            )
        )
        self._record_usage(
            response,
            prompt_tokens=prompt_tokens,
            max_output_tokens=max_output,
            system_prompt=FINALIZATION_SYSTEM_PROMPT,
            user_prompt=messages[1].content or "",
            phase="guard_finalization",
        )
        try:
            payload = extract_json_object(response.message.content or "")
        except (ValueError, json.JSONDecodeError) as exc:
            return AgentAction.message_only(
                f"Constrained finalization returned invalid JSON: {exc}",
                meta={"finalization_outcome": "no_answer", **telemetry},
            )
        if set(payload) - {"kind", "final_output", "navigation_claims"}:
            return AgentAction.message_only(
                "Constrained finalization returned unsupported fields.",
                meta={"finalization_outcome": "no_answer", **telemetry},
            )
        if str(payload.get("kind") or "").strip().lower() != "final":
            return AgentAction.message_only(
                "Constrained finalization did not return a final action.",
                meta={"finalization_outcome": "no_answer", **telemetry},
            )
        output = str(payload.get("final_output") or "").strip()
        if not output:
            return AgentAction.message_only(
                "Constrained finalization returned an empty answer.",
                meta={"finalization_outcome": "no_answer", **telemetry},
            )
        claim_error = navigation_claims_shape_error(payload.get("navigation_claims"))
        if claim_error:
            return AgentAction.message_only(
                f"Constrained finalization returned invalid claims: {claim_error}.",
                meta={"finalization_outcome": "no_answer", **telemetry},
            )
        action = action_from_payload(payload, response=response, engine_role="planner")
        return AgentAction.final(
            output, meta={**dict(action.meta), "finalization_outcome": "success", **telemetry}
        )


class NavigationRunHook(AgentRunLifecycleHook):
    def __init__(self, planner: BudgetedNavigationPlanner) -> None:
        self.planner = planner

    def on_start(self, task: AgentTask, *, max_steps: int, engine_roles: EngineRoles) -> None:
        self.planner.reset_navigation_goals()

    def on_step(
        self, task: AgentTask, context: AgentContext, step: AgentStep, run: AgentRun
    ) -> None:
        return None

    def on_finish(self, run: AgentRun) -> None:
        run.meta["planner_usage"] = asdict(self.planner.usage)
        if self.planner.structured_navigation:
            run.meta["structured_navigation"] = {
                "enabled": True,
                "goals": [goal.as_dict() for goal in self.planner.navigation_goals],
            }
        if self.planner.usage.stop_reason:
            run.status = "stopped"
            if self.planner.usage.stop_reason == "token_budget":
                run.stop_reason = "token_budget"
            elif self.planner.usage.stop_reason == "context_limit":
                run.stop_reason = "context_limit"
