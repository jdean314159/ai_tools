from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from agent_lib import ProgrammingRoleBindings, ProgrammingRuntimeConfig
from agent_lib.examples import build_default_programming_config, run_programming_demo_from_config
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


def test_programming_runtime_config_round_trip() -> None:
    config = build_default_programming_config(
        session_id="cfg_demo",
        path="src/main.py",
        memory_backend="engram",
        role_bindings=ProgrammingRoleBindings(planner="mentor", executor="worker", critic="mentor"),
    )

    payload = config.to_dict()
    restored = ProgrammingRuntimeConfig.from_dict(payload)

    assert restored.memory_backend == "engram"
    assert restored.session_id == "cfg_demo"
    assert restored.task.metadata["path"] == "src/main.py"
    assert restored.role_bindings.executor == "worker"
    assert restored.failure_policy.tool_policies[0].tool_name == "read_file"
    assert restored.context_budget.max_visible_steps == config.context_budget.max_visible_steps


def test_programming_demo_can_run_from_config_with_named_role_engines(tmp_path) -> None:
    planner_payloads = iter([
        '{"kind":"tool","tool_name":"read_file","arguments":{"path":"main.py"},"message":"Read the target file."}',
        '{"kind":"tool","tool_name":"run_check","arguments":{"path":"main.py","must_contain":"return a + b"},"message":"Verify the patch."}',
        '{"kind":"final","final_output":"Updated main.py so add(a, b) now returns a + b.","message":"Updated main.py so add(a, b) now returns a + b."}',
    ])
    mentor_engine = MockEngine(model="mentor-mock", response_fn=lambda req: next(planner_payloads))
    worker_engine = MockEngine(
        model="worker-mock",
        response_fn=lambda req: '{"old":"return a - b","new":"return a + b","message":"Patch the buggy subtraction into addition."}',
    )

    config = build_default_programming_config(
        session_id="cfg_demo",
        memory_backend="engram",
        role_bindings=ProgrammingRoleBindings(planner="deepseek", executor="local_worker", critic="deepseek"),
    )

    run, root = run_programming_demo_from_config(
        config,
        root=tmp_path,
        engines_by_name={"deepseek": mentor_engine, "local_worker": worker_engine},
    )

    assert run.status == "completed"
    assert mentor_engine.call_count == 2
    assert worker_engine.call_count == 1
    assert (root / "main.py").read_text(encoding="utf-8").strip().endswith("return a + b")
    assert run.steps[0].trace is not None and run.steps[0].trace.metrics.model == "mentor-mock"
    assert run.steps[1].trace is not None and run.steps[1].trace.metrics.model == "worker-mock"


from agent_lib.programming import load_programming_runtime_config, save_programming_runtime_config
from agent_lib.examples import run_programming_demo_from_file, write_programming_config_file


def test_programming_runtime_config_can_be_saved_and_loaded_from_json(tmp_path) -> None:
    config = build_default_programming_config(
        session_id="cfg_file_demo",
        memory_backend="engram",
        role_bindings=ProgrammingRoleBindings(planner="mentor", executor="worker", critic="mentor"),
    )
    path = tmp_path / "programming_demo.json"
    save_programming_runtime_config(config, path)
    restored = load_programming_runtime_config(path)

    assert path.exists()
    assert restored.session_id == "cfg_file_demo"
    assert restored.role_bindings.planner == "mentor"


def test_programming_demo_can_run_from_file_config_with_named_engines(tmp_path) -> None:
    planner_payloads = iter([
        '{"kind":"tool","tool_name":"read_file","arguments":{"path":"main.py"},"message":"Read the target file."}',
        '{"kind":"tool","tool_name":"run_check","arguments":{"path":"main.py","must_contain":"return a + b"},"message":"Verify the patch."}',
        '{"kind":"final","final_output":"Updated main.py so add(a, b) now returns a + b.","message":"Updated main.py so add(a, b) now returns a + b."}',
    ])
    mentor_engine = MockEngine(model="mentor-mock", response_fn=lambda req: next(planner_payloads))
    worker_engine = MockEngine(
        model="worker-mock",
        response_fn=lambda req: '{"old":"return a - b","new":"return a + b","message":"Patch the buggy subtraction into addition."}',
    )

    config_path = write_programming_config_file(
        tmp_path / "programming_demo.json",
        session_id="cfg_file_demo",
        task_path="main.py",
        memory_backend="engram",
        mentor="deepseek",
        worker="local_worker",
        critic="deepseek",
    )

    run, root = run_programming_demo_from_file(
        config_path,
        root=tmp_path / "workspace",
        engines_by_name={"deepseek": mentor_engine, "local_worker": worker_engine},
    )

    assert run.status == "completed"
    assert (root / "main.py").read_text(encoding="utf-8").strip().endswith("return a + b")
    assert mentor_engine.call_count == 2
    assert worker_engine.call_count == 1
