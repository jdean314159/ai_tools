from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Sequence

import pytest

from agent_lib import AgentContext, AgentStep, AgentTask, EngineRoles, ToolCall
from agent_lib.contracts import AgentAction, AgentObservation, AgentRun, ToolResult
from agent_lib.eval.repo_navigation import (
    BudgetedNavigationPlanner,
    FINALIZATION_ACTION_SCHEMA,
    GroundTruthRegion,
    LlamaServerClient,
    ModelTokenizer,
    NavigationBudget,
    NavigationPolicy,
    NavigationTelemetry,
    NavigationToolRuntime,
    NavigationWorkspace,
    NoWriteContextBuilder,
    NoWriteContextConfig,
    build_environment_manifest,
    build_navigation_harness,
    load_ground_truth,
    render_run_record,
    score_navigation_run,
    tree_content_digest,
    validate_ground_truth_snapshot,
    PlannerUsage,
)
from agent_lib.eval.navigation_goals import seed_navigation_goals
from agent_lib.eval.verifiable_navigation import (
    RELATION_CLAIMS_SCHEMA,
    relation_claims_shape_error,
)
from agent_lib.memory import NullMemoryAdapter
from llm_engines.contracts import (
    ChatMessage,
    EngineCapabilities,
    GenerationRequest,
    GenerationResponse,
    UsageStats,
)
from llm_engines.contracts import GenerationError


class WordTokenizer(ModelTokenizer):
    def count_messages(self, messages: Sequence[ChatMessage]) -> int:
        return sum(len((message.content or "").split()) for message in messages) + len(messages) * 2

    def count_text(self, text: str) -> int:
        return max(1, len(text.split()))


def _goal_payload(*, status: str = "open", with_evidence: bool = False) -> list[dict]:
    return [
        {
            **goal.as_dict(),
            "status": status,
            "resolution_summary": (f"Resolved {goal.goal_id}." if status != "open" else ""),
            "evidence": (
                [{"path": "short.py", "start_line": 1, "end_line": 1}] if with_evidence else []
            ),
        }
        for goal in seed_navigation_goals()
    ]


@dataclass
class RecordingEngine:
    responses: list[str]
    input_tokens: int | None = 20
    output_tokens: int | None = 10
    requests: list[GenerationRequest] = field(default_factory=list)

    def get_capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(chat=True)

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.requests.append(request)
        return GenerationResponse(
            message=ChatMessage(role="assistant", content=self.responses.pop(0)),
            finish_reason="stop",
            usage=UsageStats(input_tokens=self.input_tokens, output_tokens=self.output_tokens),
            model_name="qwen3.6:27b-test",
            backend="mock",
        )


class FakeLlamaServerClient(LlamaServerClient):
    def __init__(self, *, reused_prompt_tokens: int = 0, returned_seed: int = 7) -> None:
        super().__init__("http://llama.test:8080", seed=7)
        self.reused_prompt_tokens = reused_prompt_tokens
        self.returned_seed = returned_seed
        self.requests: list[tuple[str, str, dict[str, object] | None]] = []

    def _request_json(
        self, method: str, path: str, payload: dict[str, object] | None = None
    ) -> dict[str, object]:
        self.requests.append((method, path, payload))
        if path == "/health":
            return {"status": "ok"}
        if path == "/props":
            return {
                "model_path": "/models/qwen3.6-27b-q4.gguf",
                "build_info": "b123-abc",
                "chat_template": "template",
                "chat_template_caps": {},
                "default_generation_settings": {"n_ctx": 40_000},
            }
        if path == "/apply-template":
            return {"prompt": "templated prompt"}
        if path == "/tokenize":
            return {"tokens": [1, 2, 3]}
        if path == "/completion":
            return {
                "content": '{"kind":"final","final_output":"done","navigation_claims":[]}',
                "model": "qwen3.6-27b",
                "stop_type": "eos",
                "tokens_evaluated": 3,
                "tokens_predicted": 4,
                "tokens_cached": 7,
                "truncated": False,
                "generation_settings": {
                    "seed": self.returned_seed,
                    "temperature": 0.0,
                    "top_k": 0,
                    "top_p": 1.0,
                    "min_p": 0.0,
                    "presence_penalty": 0.0,
                    "n_predict": 20,
                },
                "timings": {"cache_n": self.reused_prompt_tokens},
            }
        raise AssertionError(path)


def test_planner_accepts_task_specific_goals_and_relation_claim_schema() -> None:
    planner = BudgetedNavigationPlanner(
        engine=RecordingEngine(responses=[]),
        tokenizer=WordTokenizer(),
        structured_navigation=True,
        navigation_goal_definitions=(("find_edge", "Find the requested edge."),),
        final_claim_name="relation_claims",
        final_claim_schema=RELATION_CLAIMS_SCHEMA,
        final_claim_validator=relation_claims_shape_error,
        require_observed_evidence_before_final=True,
    )

    assert [goal.goal_id for goal in planner.navigation_goals] == ["find_edge"]
    final_branch = next(
        branch
        for branch in planner.action_schema["oneOf"]
        if branch["properties"]["kind"]["enum"] == ["final"]
    )
    assert "relation_claims" in final_branch["required"]
    assert "navigation_claims" not in final_branch["properties"]
    assert planner.require_observed_evidence_before_final is True


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "rag_lib" / "src").mkdir(parents=True)
    (tmp_path / "rag_lib" / "src" / "chroma.py").write_text(
        "from chromadb import PersistentClient\n\nclient = PersistentClient(path='x')\ncollection.upsert(ids=['1'])\n",
        encoding="utf-8",
    )
    (tmp_path / "short.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "tests" / "case" / "runs").mkdir(parents=True)
    (tmp_path / "tests" / "case" / "runs" / "trace.py").write_text(
        "PersistentClient('junk')\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "case" / "runs" / "chroma.sqlite3").write_bytes(b"SQLite data")
    (tmp_path / "embedding_cache.db").write_bytes(b"SQLite data outside a run tree")
    (tmp_path / "examples" / "asc_probe" / "runs").mkdir(parents=True)
    (tmp_path / "examples" / "asc_probe" / "runs" / "trace.py").write_text(
        "PersistentClient('other junk')\n", encoding="utf-8"
    )
    (tmp_path / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    return tmp_path


def test_read_file_is_bounded_and_accepts_short_source(repo: Path) -> None:
    workspace = NavigationWorkspace(NavigationPolicy(repo, default_line_count=1))

    result = workspace.read_file("short.py")

    assert result.success
    assert result.output == "1: x = 1"
    assert result.meta["evidence"] == [{"path": "short.py", "lines": [1]}]


def test_read_file_rejects_secrets_binary_and_oversized_content(repo: Path) -> None:
    (repo / "binary.py").write_bytes(b"ok\x00bad")
    (repo / "large.json").write_text('"' + "x" * 100 + '"', encoding="utf-8")
    (repo / "large.py").write_text("x" * 200, encoding="utf-8")
    policy = NavigationPolicy(repo, max_file_bytes=128, max_json_bytes=32)
    workspace = NavigationWorkspace(policy)

    secret = workspace.read_file(".env")
    binary = workspace.read_file("binary.py")
    oversized = workspace.read_file("large.json")
    oversized_source = workspace.read_file("large.py", full=True)

    assert not secret.success and secret.meta["category"] == "denied_content"
    assert not binary.success and binary.meta["category"] == "binary_content"
    assert not oversized.success and oversized.meta["category"] == "oversized_json"
    assert not oversized_source.success and oversized_source.meta["category"] == "oversized_file"
    assert "secret" not in str(secret.output)


def test_confinement_rejects_absolute_parent_encoded_and_symlink_escape(
    repo: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outside = tmp_path_factory.mktemp("outside")
    (outside / "private.py").write_text("secret = True\n", encoding="utf-8")
    (repo / "escape").symlink_to(outside, target_is_directory=True)
    workspace = NavigationWorkspace(NavigationPolicy(repo))

    results = [
        workspace.read_file(str((outside / "private.py").resolve())),
        workspace.read_file("../outside/private.py"),
        workspace.read_file("%2e%2e/private.py"),
        workspace.read_file("escape/private.py"),
    ]

    assert all(not result.success for result in results)
    assert all(result.meta["category"] == "path_escape" for result in results)


def test_confinement_cannot_read_sibling_repo_agent_eval(tmp_path: Path) -> None:
    root = tmp_path / "ai_tools"
    root.mkdir()
    eval_root = tmp_path / "repo_agent_eval"
    eval_root.mkdir()
    (eval_root / "RUBRIC-00-elaboration-scoring.md").write_text("hidden rubric\n", encoding="utf-8")
    workspace = NavigationWorkspace(NavigationPolicy(root))

    result = workspace.read_file("../repo_agent_eval/RUBRIC-00-elaboration-scoring.md")

    assert not result.success
    assert result.meta["category"] == "path_escape"
    assert "hidden rubric" not in str(result.output)


def test_grep_and_list_prune_denied_run_tree_and_cap_results(repo: Path) -> None:
    workspace = NavigationWorkspace(NavigationPolicy(repo))

    grep_result = workspace.grep("PersistentClient", max_matches=1)
    list_result = workspace.list_files(max_results=1)

    assert grep_result.success
    assert "rag_lib/src/chroma.py:1" in grep_result.output
    assert "tests/" not in grep_result.output and "examples/" not in grep_result.output
    assert grep_result.meta["pruned_paths"] >= 1
    assert list_result.success and list_result.meta["truncated"] is True
    assert len(str(list_result.output).splitlines()) == 1


def test_run_tree_traversal_and_database_reads_are_actually_blocked(repo: Path) -> None:
    workspace = NavigationWorkspace(NavigationPolicy(repo))

    denied_run_read = workspace.read_file("tests/case/runs/trace.py")
    denied_run_walk = workspace.grep("PersistentClient", path="tests/case/runs")
    denied_database_read = workspace.read_file("embedding_cache.db")

    assert not denied_run_read.success and denied_run_read.meta["category"] == "denied_path"
    assert not denied_run_walk.success and denied_run_walk.meta["category"] == "denied_path"
    assert (
        not denied_database_read.success
        and denied_database_read.meta["category"] == "denied_content"
    )
    assert "junk" not in str(denied_run_read.output)
    assert "SQLite data" not in str(denied_database_read.output)


def test_result_character_cap_never_claims_unsurfaced_evidence(repo: Path) -> None:
    (repo / "long.py").write_text(
        "prefix " + "x" * 200 + " TARGET " + "y" * 200 + "\n", encoding="utf-8"
    )
    workspace = NavigationWorkspace(NavigationPolicy(repo, max_result_chars=80))

    grep_result = workspace.grep("TARGET", path="long.py")
    list_result = workspace.list_files(glob="*", max_results=100)

    assert grep_result.success and len(str(grep_result.output)) <= 80
    assert grep_result.meta["truncated"] is True
    assert grep_result.meta["evidence"] == []
    assert list_result.success and len(str(list_result.output)) <= 80


def test_invalid_arguments_and_unknown_tool_fail_closed_and_are_recorded(repo: Path) -> None:
    runtime = NavigationToolRuntime(NavigationWorkspace(NavigationPolicy(repo)))

    bad_arguments = runtime.invoke(ToolCall("grep", {"pattern": "x", "max_matches": 10_000}))
    unknown = runtime.invoke(ToolCall("write_file", {"path": "short.py"}))

    assert not bad_arguments.success and bad_arguments.meta["category"] == "invalid_arguments"
    assert not unknown.success and unknown.meta["error"] == "unknown_tool"
    assert [call["success"] for call in runtime.telemetry.calls] == [False, False]


def test_no_write_context_builder_bounds_outputs_without_creating_files(repo: Path) -> None:
    before = tree_content_digest(repo)
    step = AgentStep(
        index=1,
        action=AgentAction.tool("read_file", {"path": "short.py"}),
        observation=AgentObservation(
            kind="tool_result", text="x" * 100, tool_result=ToolResult("read_file", "x" * 100)
        ),
    )
    builder = NoWriteContextBuilder(
        NoWriteContextConfig(max_visible_steps=1, max_tool_output_chars=20)
    )

    context = builder.build_context(
        AgentTask(task_id="test", goal="find"),
        [step],
        active_controller="planner",
        escalated=False,
        memory=NullMemoryAdapter(),
        tool_specs=[],
        engine_roles=EngineRoles(),
    )

    assert context.steps[0].observation is not None
    assert "truncated" in context.steps[0].observation.text
    assert tree_content_digest(repo) == before


def test_budgeted_planner_validates_action_and_records_actual_usage() -> None:
    engine = RecordingEngine(
        ['{"kind":"tool","tool_name":"grep","arguments":{"pattern":"Chroma"}}']
    )
    planner = BudgetedNavigationPlanner(
        engine=engine,
        tokenizer=WordTokenizer(),
        budget=NavigationBudget(
            cumulative_token_limit=10_000,
            context_window=2_000,
            minimum_output_reserve=10,
            per_call_output_cap=100,
        ),
    )

    action = planner.plan(AgentContext(task=AgentTask(task_id="t", goal="find Chroma"), steps=[]))

    assert action.tool_call == ToolCall("grep", {"pattern": "Chroma"})
    assert planner.usage.cumulative_actual_tokens == 30
    assert planner.usage.calls[0]["backend_reported"] is True
    assert "cache_prompt" not in engine.requests[0].metadata
    assert engine.requests[0].json_schema is not None
    assert [
        branch["properties"]["kind"]["enum"] for branch in engine.requests[0].json_schema["oneOf"]
    ] == [["tool"], ["final"]]


def test_llama_server_client_uses_exact_template_tokenizer_and_disables_cache() -> None:
    client = FakeLlamaServerClient()
    messages = [
        ChatMessage(role="system", content="system"),
        ChatMessage(role="user", content="task"),
    ]

    assert client.count_messages(messages) == 3
    response = client.generate(GenerationRequest(messages=messages, max_tokens=20, temperature=0.0))
    deployment = client.deployment_info()

    completion_payload = next(
        payload for _, path, payload in client.requests if path == "/completion"
    )
    assert completion_payload is not None
    assert completion_payload["cache_prompt"] is False
    assert completion_payload["seed"] == 7
    assert completion_payload["top_k"] == 0
    assert completion_payload["top_p"] == 1.0
    assert completion_payload["presence_penalty"] == 0.0
    assert response.usage.input_tokens == 3
    assert response.usage.output_tokens == 4
    assert response.raw_provider_payload is not None
    assert response.raw_provider_payload["tokens_cached"] == 7
    assert response.raw_provider_payload["reused_prompt_tokens"] == 0
    assert deployment["default_generation_settings"] == {"n_ctx": 40_000}


@pytest.mark.parametrize(
    "client",
    [FakeLlamaServerClient(reused_prompt_tokens=2), FakeLlamaServerClient(returned_seed=8)],
)
def test_llama_server_client_rejects_unverified_or_reused_prompt_cache(
    client: FakeLlamaServerClient,
) -> None:
    messages = [ChatMessage(role="user", content="task")]
    client.count_messages(messages)

    with pytest.raises(GenerationError, match="setting mismatch|reused"):
        client.generate(GenerationRequest(messages=messages, max_tokens=20, temperature=0.0))


@pytest.mark.parametrize(
    ("limit", "context_window", "reason"),
    [(10, 10_000, "token_budget"), (10_000, 10, "context_limit")],
)
def test_budget_stops_before_invocation(limit: int, context_window: int, reason: str) -> None:
    engine = RecordingEngine(['{"kind":"final","final_output":"unused","navigation_claims":[]}'])
    planner = BudgetedNavigationPlanner(
        engine=engine,
        tokenizer=WordTokenizer(),
        budget=NavigationBudget(
            cumulative_token_limit=limit,
            context_window=context_window,
            minimum_output_reserve=5,
            per_call_output_cap=10,
        ),
    )

    action = planner.plan(AgentContext(task=AgentTask(task_id="t", goal="find Chroma"), steps=[]))

    assert action.kind == "final"
    assert action.meta["navigation_stop_reason"] == reason
    assert not engine.requests


def test_invalid_model_tool_is_rejected_before_tool_runtime(repo: Path) -> None:
    engine = RecordingEngine(
        ['{"kind":"tool","tool_name":"write_file","arguments":{"path":"short.py"}}']
    )
    planner = BudgetedNavigationPlanner(
        engine=engine,
        tokenizer=WordTokenizer(),
        budget=NavigationBudget(
            cumulative_token_limit=10_000,
            context_window=2_000,
            minimum_output_reserve=10,
            per_call_output_cap=100,
        ),
    )

    action = planner.plan(AgentContext(task=AgentTask(task_id="t", goal="find"), steps=[]))

    assert action.kind == "message"
    assert action.meta["invalid_action"] is True


def test_budgeted_planner_preserves_structured_final_claims() -> None:
    claims = [
        {
            "path": "pkg/module.py",
            "symbol": "Thing.run",
            "operation": "store.delete",
            "classification": "mutation",
            "evidence": [{"path": "pkg/module.py", "start_line": 10, "end_line": 11}],
        }
    ]
    engine = RecordingEngine(
        [json.dumps({"kind": "final", "final_output": "Done.", "navigation_claims": claims})]
    )
    planner = BudgetedNavigationPlanner(
        engine=engine,
        tokenizer=WordTokenizer(),
        budget=NavigationBudget(
            cumulative_token_limit=10_000,
            context_window=2_000,
            minimum_output_reserve=10,
            per_call_output_cap=100,
        ),
    )

    action = planner.plan(
        AgentContext(task=AgentTask(task_id="claims", goal="find mutations"), steps=[])
    )

    assert action.kind == "final"
    assert action.meta["navigation_claims"] == claims


def test_structured_planner_rejects_finalization_with_open_goals() -> None:
    engine = RecordingEngine(
        [
            json.dumps(
                {
                    "kind": "final",
                    "final_output": "Premature.",
                    "navigation_claims": [],
                    "navigation_goals": _goal_payload(),
                }
            )
        ]
    )
    planner = BudgetedNavigationPlanner(
        engine=engine,
        tokenizer=WordTokenizer(),
        structured_navigation=True,
    )

    action = planner.plan(
        AgentContext(task=AgentTask(task_id="structured", goal="find all"), steps=[])
    )

    assert action.kind == "message"
    assert action.meta["invalid_navigation_goals"] is True
    assert "cannot finalize with open navigation goals" in action.message


def test_structured_harness_completes_only_after_resolving_seeded_goals(
    repo: Path,
) -> None:
    tool_payload = {
        "kind": "tool",
        "tool_name": "read_file",
        "arguments": {"path": "short.py", "start_line": 1, "line_count": 10},
        "serves_goal_ids": [goal.goal_id for goal in seed_navigation_goals()],
        "navigation_goals": _goal_payload(),
    }
    final_payload = {
        "kind": "final",
        "final_output": "Resolved from observed evidence.",
        "navigation_claims": [],
        "navigation_goals": _goal_payload(status="resolved", with_evidence=True),
    }
    engine = RecordingEngine([json.dumps(tool_payload), json.dumps(final_payload)])
    harness = build_navigation_harness(
        root=repo,
        engine=engine,
        tokenizer=WordTokenizer(),
        action_guard_mode="off",
        structured_navigation=True,
    )

    run = harness.run("Find all required categories", task_id="nav-struct-test")

    assert run.status == "completed"
    assert run.final_output == "Resolved from observed evidence."
    assert all(goal["status"] == "resolved" for goal in run.meta["structured_navigation"]["goals"])
    assert run.steps[-1].action.meta["navigation_goals"] == final_payload["navigation_goals"]


def test_harness_runs_existing_runtime_and_preserves_tree(repo: Path) -> None:
    engine = RecordingEngine(
        [
            '{"kind":"tool","tool_name":"grep","arguments":{"pattern":"PersistentClient","path":"rag_lib/src"}}',
            '{"kind":"final","final_output":"rag_lib/src/chroma.py initializes PersistentClient.","navigation_claims":[]}',
        ]
    )
    harness = build_navigation_harness(
        root=repo,
        engine=engine,
        tokenizer=WordTokenizer(),
        budget=NavigationBudget(
            cumulative_token_limit=20_000,
            context_window=4_000,
            minimum_output_reserve=10,
            per_call_output_cap=100,
        ),
    )
    before = tree_content_digest(repo)

    run = harness.run("Find PersistentClient")

    assert run.status == "completed"
    assert run.stop_reason == "completed"
    assert len(harness.tools.telemetry.calls) == 1
    guard = run.meta["action_guard"]
    assert guard["fired"] is False
    assert guard["checks"] == 1
    assert guard["mode"] == "shadow"
    assert guard["detector_trace"]["actions"][0]["action"]["tool_call"]["name"] == "grep"
    assert guard["detector_trace"]["decisions"][0]["fired"] is False
    assert tree_content_digest(repo) == before


def test_harness_exposes_token_budget_stop_reason(repo: Path) -> None:
    engine = RecordingEngine(['{"kind":"final","final_output":"unused","navigation_claims":[]}'])
    harness = build_navigation_harness(
        root=repo,
        engine=engine,
        tokenizer=WordTokenizer(),
        budget=NavigationBudget(
            cumulative_token_limit=10,
            context_window=2_000,
            minimum_output_reserve=5,
            per_call_output_cap=10,
        ),
    )

    run = harness.run("Find PersistentClient")

    assert run.status == "stopped"
    assert run.stop_reason == "token_budget"
    assert not engine.requests


def _guard_triggering_responses(final_response: str) -> list[str]:
    responses = [
        json.dumps(
            {
                "kind": "tool",
                "tool_name": "read_file",
                "arguments": {
                    "path": "short.py",
                    "start_line": 1 + offset * 100,
                    "line_count": 100,
                },
            }
        )
        for offset in range(8)
    ]
    repeated = json.dumps(
        {
            "kind": "tool",
            "tool_name": "read_file",
            "arguments": {"path": "short.py", "start_line": 1, "line_count": 100},
        }
    )
    return [*responses, repeated, repeated, final_response]


def test_action_guard_uses_one_tool_free_finalization_call(repo: Path) -> None:
    engine = RecordingEngine(
        _guard_triggering_responses(
            '{"kind":"final","final_output":"short.py:1 is the relevant evidence.","navigation_claims":[]}'
        )
    )
    harness = build_navigation_harness(
        root=repo,
        engine=engine,
        tokenizer=WordTokenizer(),
        budget=NavigationBudget(
            cumulative_token_limit=100_000,
            context_window=10_000,
            minimum_output_reserve=10,
            per_call_output_cap=100,
        ),
        action_guard_mode="enforce",
    )

    run = harness.run("Find the relevant evidence", task_id="guard-success")

    assert run.status == "completed"
    assert run.final_output == "short.py:1 is the relevant evidence."
    assert len(engine.requests) == 11
    final_request = engine.requests[-1]
    assert final_request.metadata["phase"] == "guard_finalization"
    assert final_request.metadata["tools_enabled"] is False
    assert final_request.json_schema == FINALIZATION_ACTION_SCHEMA
    assert "Available actions" not in (final_request.messages[0].content or "")
    assert run.meta["action_guard"]["finalization_outcome"] == "success"
    assert run.meta["action_guard"]["discarded_context_range"] == [8, 10]
    assert run.meta["action_guard"]["token_savings"] > 0
    assert len(run.steps) == 11
    assert run.steps[8].action.kind == "tool"  # Original looping trajectory is retained for audit.


def test_action_guard_stops_after_one_non_final_response(repo: Path) -> None:
    engine = RecordingEngine(
        _guard_triggering_responses(
            '{"kind":"tool","tool_name":"read_file","arguments":{"path":"short.py"}}'
        )
    )
    harness = build_navigation_harness(
        root=repo,
        engine=engine,
        tokenizer=WordTokenizer(),
        budget=NavigationBudget(
            cumulative_token_limit=100_000,
            context_window=10_000,
            minimum_output_reserve=10,
            per_call_output_cap=100,
        ),
        action_guard_mode="enforce",
    )

    run = harness.run("Find the relevant evidence", task_id="guard-no-answer")

    assert run.status == "stopped"
    assert run.stop_reason == "guard_no_answer"
    assert run.meta["action_guard"]["finalization_outcome"] == "no_answer"
    assert len(engine.requests) == 11
    assert len(harness.tools.telemetry.calls) == 10


def test_action_guard_shadow_mode_records_without_intervening(repo: Path) -> None:
    responses = _guard_triggering_responses(
        '{"kind":"final","final_output":"Normal planner final answer.","navigation_claims":[]}'
    )
    engine = RecordingEngine(responses)
    harness = build_navigation_harness(
        root=repo,
        engine=engine,
        tokenizer=WordTokenizer(),
        budget=NavigationBudget(
            cumulative_token_limit=100_000,
            context_window=10_000,
            minimum_output_reserve=10,
            per_call_output_cap=100,
        ),
        action_guard_mode="shadow",
    )

    run = harness.run("Find the relevant evidence", task_id="guard-shadow")

    assert run.status == "completed"
    assert run.final_output == "Normal planner final answer."
    assert len(engine.requests) == 11
    assert all(request.metadata.get("phase") != "guard_finalization" for request in engine.requests)
    assert run.meta["action_guard"]["fired"] is False
    assert run.meta["action_guard"]["would_fire"] is True
    assert run.meta["action_guard"]["shadow_intervention"]["loop_start_action"] == 9
    trace = run.meta["action_guard"]["detector_trace"]
    assert len(trace["actions"]) == 10
    assert len(trace["decisions"]) == 10
    assert trace["decisions"][-1]["would_fire"] is True


def test_action_guard_off_mode_records_no_guard_telemetry(repo: Path) -> None:
    engine = RecordingEngine(['{"kind":"final","final_output":"done","navigation_claims":[]}'])
    harness = build_navigation_harness(
        root=repo,
        engine=engine,
        tokenizer=WordTokenizer(),
        action_guard_mode="off",
    )

    run = harness.run("Finish immediately", task_id="guard-off")

    assert run.status == "completed"
    assert "action_guard" not in run.meta


def test_finalizer_budget_unavailable_does_not_call_engine() -> None:
    engine = RecordingEngine(
        ['{"kind":"final","final_output":"must not be used","navigation_claims":[]}']
    )
    planner = BudgetedNavigationPlanner(
        engine=engine,
        tokenizer=WordTokenizer(),
        budget=NavigationBudget(
            cumulative_token_limit=20,
            context_window=2_000,
            minimum_output_reserve=10,
            per_call_output_cap=100,
        ),
    )
    context = AgentContext(
        task=AgentTask(task_id="budget", goal="A task whose final prompt cannot fit safely"),
        steps=[],
        tool_specs=[],
    )

    action = planner.finalize(context, "Finalize now.", full_context=context)

    assert action.kind == "message"
    assert action.meta["finalization_outcome"] == "budget_unavailable"
    assert action.meta["budget_blockers"] == ["cumulative_token_limit"]
    assert action.meta["required_minimum_tokens"] > action.meta["available_cumulative_tokens"]
    assert not engine.requests
    assert planner.usage.cumulative_actual_tokens == 0


def test_manifest_hashes_allowed_sources_without_secret_paths(repo: Path) -> None:
    manifest = build_environment_manifest(NavigationPolicy(repo))

    allowed_paths = {item["path"] for item in manifest["allowed_sources"]}
    assert "short.py" in allowed_paths
    assert ".env" not in allowed_paths
    assert manifest["manifest_sha256"]
    assert manifest["totals"]["denied_or_unscoped_files"] >= 2


def test_ground_truth_loading_scoring_and_run_record(repo: Path, tmp_path: Path) -> None:
    answer_key = tmp_path / "answer.json"
    manifest = build_environment_manifest(NavigationPolicy(repo))
    source_hash = next(
        item["sha256"]
        for item in manifest["allowed_sources"]
        if item["path"] == "rag_lib/src/chroma.py"
    )
    answer_key.write_text(
        json.dumps(
            {
                "question": "Find Chroma",
                "snapshot": {
                    "git_sha": manifest["git_sha"],
                    "source_sha256": {"rag_lib/src/chroma.py": source_hash},
                },
                "regions": [
                    {
                        "id": "GT-01",
                        "path": "rag_lib/src/chroma.py",
                        "start_line": 1,
                        "end_line": 3,
                        "symbol": "ChromaStorage._make_client",
                        "classification": "client initialization",
                        "anchors": ["PersistentClient"],
                        "required_answer_terms": ["PersistentClient"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    question, regions = load_ground_truth(answer_key)
    validate_ground_truth_snapshot(answer_key, manifest, repo)
    telemetry = NavigationTelemetry(
        calls=[
            {
                "tool": "grep",
                "arguments": {"pattern": "PersistentClient"},
                "success": True,
                "category": "ok",
                "paths": ["rag_lib/src/chroma.py"],
                "evidence": [{"path": "rag_lib/src/chroma.py", "lines": [1, 3]}],
                "result_chars": 20,
                "elapsed_ms": 1.0,
            }
        ]
    )
    run = AgentRun(
        task=AgentTask(task_id="t", goal=question),
        status="completed",
        stop_reason="completed",
        final_output="rag_lib/src/chroma.py initializes PersistentClient.",
        meta={
            "planner_usage": {"cumulative_actual_tokens": 50},
            "navigation_claims": [
                {
                    "path": "rag_lib/src/chroma.py",
                    "symbol": "ChromaStorage._make_client",
                    "operation": "PersistentClient initialization",
                    "classification": "client initialization",
                    "evidence": [
                        {
                            "path": "rag_lib/src/chroma.py",
                            "start_line": 1,
                            "end_line": 1,
                        }
                    ],
                }
            ],
        },
    )
    run.steps.append(AgentStep(1, AgentAction.final(run.final_output)))
    budget = NavigationBudget(cumulative_token_limit=100)

    score = score_navigation_run(run, telemetry, regions, budget)

    assert score["passed"] is True
    assert score["evidence_recall"] == 1.0
    assert score["answer_correctness"] == 1.0
    assert score["useful_call_rate"] == 1.0

    stub_harness = SimpleNamespace(
        planner=SimpleNamespace(usage=PlannerUsage(cumulative_actual_tokens=50)),
        tools=SimpleNamespace(telemetry=telemetry),
    )

    record = render_run_record(
        run=run,
        harness=stub_harness,  # type: ignore[arg-type]
        manifest=manifest,
        pre_tree_digest="same",
        post_tree_digest="same",
        score=score,
    )
    assert record["read_only_verified"] is True
    assert record["run"]["steps"][0]["action"]["kind"] == "final"


def test_repeated_blocked_requests_fail_scoring() -> None:
    region = GroundTruthRegion("GT-01", "x.py", 1, 1, "write", ("write",))
    blocked_call = {
        "tool": "read_file",
        "arguments": {"path": ".env"},
        "success": False,
        "category": "denied_content",
        "paths": [],
        "evidence": [],
        "result_chars": 10,
        "elapsed_ms": 1.0,
    }
    telemetry = NavigationTelemetry(calls=[blocked_call, dict(blocked_call)])
    run = AgentRun(
        task=AgentTask(task_id="t", goal="find"),
        status="completed",
        stop_reason="completed",
        final_output="x.py write",
        meta={"planner_usage": {"cumulative_actual_tokens": 1}},
    )
    run.steps.append(AgentStep(1, AgentAction.final("x.py write")))

    score = score_navigation_run(
        run, telemetry, [region], NavigationBudget(cumulative_token_limit=100)
    )

    assert score["passed"] is False
    assert score["repeated_blocked_attempts"] == 1
