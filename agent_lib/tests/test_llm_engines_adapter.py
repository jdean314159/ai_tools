from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from agent_lib import AgentContext, AgentTask, EngineRoles
from agent_lib.examples import run_programming_demo
from agent_lib.llm_engines_adapter import LLMActionPlanner, RoleEngineSet
from llm_engines.contracts import ChatMessage, EngineCapabilities, GenerationRequest, GenerationResponse, UsageStats


@dataclass
class MockEngine:
    model: str
    response_fn: Callable[[GenerationRequest], str]
    backend: str = "mock"
    call_count: int = 0
    requests: list[GenerationRequest] = field(default_factory=list)

    def get_capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(chat=True)

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.call_count += 1
        self.requests.append(request)
        content = self.response_fn(request)
        return GenerationResponse(
            message=ChatMessage(role="assistant", content=content),
            finish_reason="stop",
            usage=UsageStats(input_tokens=10, output_tokens=5, total_tokens=15),
            model_name=self.model,
            backend=self.backend,
        )


def test_llm_action_planner_invokes_planner_role_engine() -> None:
    planner_engine = MockEngine(
        model="mentor-mock",
        response_fn=lambda req: '{"kind":"tool","tool_name":"add","arguments":{"a":2,"b":3},"message":"Use the tool."}',
    )
    planner = LLMActionPlanner(
        engines=RoleEngineSet(planner=planner_engine),
        system_prompt="Return JSON only.",
        prompt_builder=lambda ctx: "Add 2 and 3.",
        engine_role="planner",
    )
    context = AgentContext(task=AgentTask(task_id="sum", goal="Add 2 and 3."), engine_roles=EngineRoles(planner="mentor"), steps=[])
    action = planner.plan(context)

    assert planner_engine.call_count == 1
    assert action.tool_call is not None
    assert action.tool_call.name == "add"
    assert action.meta["model_name"] == "mentor-mock"
    assert action.meta["engine_role"] == "planner"


def test_programming_demo_can_use_llm_engines_for_mentor_and_worker(tmp_path) -> None:
    planner_payloads = iter([
        '{"kind":"tool","tool_name":"read_file","arguments":{"path":"main.py"},"message":"Read the target file."}',
        '{"kind":"tool","tool_name":"run_check","arguments":{"path":"main.py","must_contain":"return a + b"},"message":"Verify the patch."}',
        '{"kind":"final","final_output":"Updated main.py so add(a, b) now returns a + b.","message":"Updated main.py so add(a, b) now returns a + b."}',
    ])
    planner_engine = MockEngine(model="mentor-mock", response_fn=lambda req: next(planner_payloads))
    executor_engine = MockEngine(
        model="worker-mock",
        response_fn=lambda req: '{"old":"return a - b","new":"return a + b","message":"Patch the buggy subtraction into addition."}',
    )

    run, root = run_programming_demo(
        root=tmp_path,
        memory_backend="engram_lite",
        planner_engine=planner_engine,
        executor_engine=executor_engine,
    )

    assert planner_engine.call_count == 2
    assert executor_engine.call_count == 1
    assert run.status == "completed"
    assert (root / "main.py").read_text(encoding="utf-8").strip().endswith("return a + b")
    assert run.steps[0].trace is not None and run.steps[0].trace.metrics.model == "mentor-mock"
    assert run.steps[1].trace is not None and run.steps[1].trace.metrics.model == "worker-mock"
