"""
tests/test_tools.py

ToolExecutor unit tests. No live LLM needed.

Uses a minimal FakeToolEngine class that satisfies the ToolCallingModel
Protocol naturally — no isinstance patching needed.
"""

from __future__ import annotations

import pytest

from llm_engines.contracts import (
    ChatMessage,
    GenerationRequest,
    GenerationResponse,
    ToolCall,
    UsageStats,
)
from llm_engines.contracts import ToolSpec, ToolParameterSchema
from llm_engines.tools import ToolExecutor, tool, _infer_tool_spec


# ---------------------------------------------------------------------------
# Minimal engine that satisfies ToolCallingModel Protocol
# ---------------------------------------------------------------------------


class FakeToolEngine:
    """
    Satisfies ToolCallingModel by implementing generate_with_tools().
    Returns responses from a provided sequence.
    """

    def __init__(self, responses: list[GenerationResponse]) -> None:
        self._responses = list(responses)
        self.call_count = 0
        self.captured_requests: list[GenerationRequest] = []

    def generate_with_tools(self, request: GenerationRequest, tools: list) -> GenerationResponse:
        self.call_count += 1
        self.captured_requests.append(request)
        if not self._responses:
            return _text_response("[no more responses]")
        return self._responses.pop(0)

    def get_capabilities(self):
        from llm_engines.contracts import EngineCapabilities

        return EngineCapabilities(
            chat=True,
            streaming=False,
            async_streaming=False,
            tool_calling=True,
            embeddings=False,
            structured_output=False,
            batch_generation=False,
            vision=False,
            usage_reporting=True,
            logprobs=False,
        )

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        return _text_response("direct generate")


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------


def _tool_call_response(name: str, arguments: dict, call_id: str = "call_1"):
    return GenerationResponse(
        message=ChatMessage(
            role="assistant",
            content=None,
            tool_calls=[ToolCall(call_id=call_id, name=name, arguments=arguments)],
        ),
        finish_reason="tool_call",
        usage=UsageStats(input_tokens=10, output_tokens=5, total_tokens=15, latency_ms=100.0),
        model_name="test-model",
        backend="test",
    )


def _text_response(content: str):
    return GenerationResponse(
        message=ChatMessage(role="assistant", content=content),
        finish_reason="stop",
        usage=UsageStats(input_tokens=20, output_tokens=10, total_tokens=30, latency_ms=200.0),
        model_name="test-model",
        backend="test",
    )


def _make_spec(name: str) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=f"Tool {name}",
        parameters={"city": ToolParameterSchema(type="string", description="City")},
        required_params=["city"],
    )


def _make_spec_no_args(name: str) -> ToolSpec:
    return ToolSpec(name=name, description=name, parameters={}, required_params=[])


# ---------------------------------------------------------------------------
# _infer_tool_spec tests
# ---------------------------------------------------------------------------


class TestInferToolSpec:
    def test_infers_name_from_function(self) -> None:
        def get_weather(city: str) -> str:
            "Get weather for a city."
            return ""

        spec = _infer_tool_spec(get_weather)
        assert spec.name == "get_weather"

    def test_infers_description_from_docstring(self) -> None:
        def my_tool(x: int) -> int:
            "Compute something useful."
            return x

        spec = _infer_tool_spec(my_tool)
        assert spec.description == "Compute something useful."

    def test_infers_parameter_types(self) -> None:
        def fn(name: str, count: int, active: bool) -> None:
            pass

        spec = _infer_tool_spec(fn)
        assert spec.parameters["name"].type == "string"
        assert spec.parameters["count"].type == "integer"
        assert spec.parameters["active"].type == "boolean"

    def test_required_params_no_default(self) -> None:
        def fn(required_arg: str, optional_arg: str = "default") -> None:
            pass

        spec = _infer_tool_spec(fn)
        assert "required_arg" in spec.required_params
        assert "optional_arg" not in spec.required_params

    def test_custom_name_override(self) -> None:
        def my_func() -> None:
            pass

        spec = _infer_tool_spec(my_func, name="custom_name")
        assert spec.name == "custom_name"

    def test_unannotated_params_default_to_string(self) -> None:
        def fn(x) -> None:
            pass

        spec = _infer_tool_spec(fn)
        assert spec.parameters["x"].type == "string"


# ---------------------------------------------------------------------------
# @tool decorator tests
# ---------------------------------------------------------------------------


class TestToolDecorator:
    def test_attaches_spec(self) -> None:
        @tool
        def search(query: str) -> str:
            "Search for information."
            return ""

        assert hasattr(search, "_tool_spec")
        assert search._tool_spec.name == "search"

    def test_custom_name(self) -> None:
        @tool(name="web_search")
        def search(query: str) -> str:
            "Search."
            return ""

        assert search._tool_spec.name == "web_search"

    def test_function_still_callable(self) -> None:
        @tool
        def add(x: int, y: int) -> int:
            "Add two numbers."
            return x + y

        assert add(2, 3) == 5


# ---------------------------------------------------------------------------
# ToolExecutor construction
# ---------------------------------------------------------------------------


class TestToolExecutorInit:
    def test_accepts_tool_calling_model(self) -> None:
        engine = FakeToolEngine([])
        ex = ToolExecutor(engine)
        assert ex.engine is engine

    def test_rejects_non_tool_calling_model(self) -> None:
        from llm_engines.backends.mock import MockEngine

        with pytest.raises(TypeError, match="ToolCallingModel"):
            ToolExecutor(MockEngine())

    def test_register_decorator(self) -> None:
        ex = ToolExecutor(FakeToolEngine([]))

        @ex.register
        def get_weather(city: str) -> str:
            "Get weather."
            return f"Sunny in {city}"

        assert "get_weather" in ex._tools
        assert "get_weather" in ex._specs
        assert ex._specs["get_weather"].parameters["city"].type == "string"

    def test_register_with_custom_name(self) -> None:
        ex = ToolExecutor(FakeToolEngine([]))

        @ex.register(name="weather")
        def get_weather(city: str) -> str:
            "Get weather."
            return ""

        assert "weather" in ex._tools

    def test_available_tools_returns_specs(self) -> None:
        ex = ToolExecutor(FakeToolEngine([]))
        ex._tools["t"] = lambda: None
        ex._specs["t"] = _make_spec_no_args("t")
        assert len(ex.available_tools) == 1


# ---------------------------------------------------------------------------
# ToolExecutor.run tests
# ---------------------------------------------------------------------------


class TestToolExecutorRun:
    def _executor(self, responses, max_steps=5, system=None):
        engine = FakeToolEngine(responses)
        ex = ToolExecutor(engine, max_steps=max_steps, system=system)
        return ex, engine

    def _register_weather(self, ex):
        ex._tools["get_weather"] = lambda city: f"Sunny, 22°C in {city}"
        ex._specs["get_weather"] = _make_spec("get_weather")

    def test_no_tools_raises(self) -> None:
        ex, _ = self._executor([_text_response("Hi")])
        with pytest.raises(RuntimeError, match="No tools registered"):
            ex.run(messages=[ChatMessage(role="user", content="Hi")])

    def test_direct_text_response(self) -> None:
        """Model responds without tool calls."""
        ex, _ = self._executor([_text_response("Paris is the capital of France.")])
        self._register_weather(ex)
        response = ex.run(messages=[ChatMessage(role="user", content="What is the capital?")])
        assert response.finish_reason == "stop"
        assert response.message.content == "Paris is the capital of France."

    def test_single_tool_call_then_done(self) -> None:
        ex, engine = self._executor(
            [
                _tool_call_response("get_weather", {"city": "Paris"}),
                _text_response("It is sunny in Paris."),
            ]
        )
        self._register_weather(ex)
        response = ex.run(messages=[ChatMessage(role="user", content="Weather in Paris?")])
        assert response.finish_reason == "stop"
        assert response.message.content == "It is sunny in Paris."
        assert engine.call_count == 2

    def test_thinking_preference_is_preserved_across_tool_rounds(self) -> None:
        ex, engine = self._executor(
            [
                _tool_call_response("get_weather", {"city": "Paris"}),
                _text_response("It is sunny in Paris."),
            ]
        )
        self._register_weather(ex)

        ex.run(
            messages=[ChatMessage(role="user", content="Weather in Paris?")],
            thinking=True,
        )

        assert len(engine.captured_requests) == 2
        assert all(request.thinking is True for request in engine.captured_requests)

    def test_seed_preference_is_preserved_across_tool_rounds(self) -> None:
        engine = FakeToolEngine(
            [
                _tool_call_response("add", {"a": 2, "b": 3}),
                _text_response("5"),
            ]
        )
        executor = ToolExecutor(engine, max_steps=2)
        executor._tools["add"] = lambda a, b: a + b
        executor._specs["add"] = _make_spec("add")

        executor.run(
            [ChatMessage(role="user", content="Add two and three")],
            seed=0,
        )

        assert len(engine.captured_requests) == 2
        assert all(request.seed == 0 for request in engine.captured_requests)

    def test_tool_result_in_second_request(self) -> None:
        """Tool result message must appear in subsequent request."""
        ex, engine = self._executor(
            [
                _tool_call_response("get_weather", {"city": "London"}),
                _text_response("Rainy in London."),
            ]
        )
        self._register_weather(ex)
        ex.run(messages=[ChatMessage(role="user", content="Weather in London?")])

        second_request = engine.captured_requests[1]
        roles = [m.role for m in second_request.messages]
        assert "tool" in roles

    def test_assistant_tool_call_in_history(self) -> None:
        """Assistant message with tool_calls must be appended before tool result."""
        ex, engine = self._executor(
            [
                _tool_call_response("get_weather", {"city": "Berlin"}),
                _text_response("Cloudy in Berlin."),
            ]
        )
        self._register_weather(ex)
        ex.run(messages=[ChatMessage(role="user", content="Weather in Berlin?")])

        second_request = engine.captured_requests[1]
        roles = [m.role for m in second_request.messages]
        # user → assistant (tool_calls) → tool → (model responds)
        assert roles.index("assistant") < roles.index("tool")

    def test_unknown_tool_does_not_raise(self) -> None:
        ex, _ = self._executor(
            [
                _tool_call_response("nonexistent_tool", {}),
                _text_response("I handled the error."),
            ]
        )
        # Register a different tool so run() doesn't bail
        ex._tools["other"] = lambda: "ok"
        ex._specs["other"] = _make_spec_no_args("other")

        response = ex.run(messages=[ChatMessage(role="user", content="Do something.")])
        assert response is not None

    def test_tool_exception_captured_not_raised(self) -> None:
        ex, _ = self._executor(
            [
                _tool_call_response("failing_tool", {}),
                _text_response("The tool failed."),
            ]
        )

        def failing():
            raise RuntimeError("deliberate failure")

        ex._tools["failing_tool"] = failing
        ex._specs["failing_tool"] = _make_spec_no_args("failing_tool")

        response = ex.run(messages=[ChatMessage(role="user", content="Do it.")])
        assert response is not None

    def test_max_steps_stops_loop(self) -> None:
        """Model keeps calling tools — should stop after max_steps."""
        responses = [_tool_call_response("loop_tool", {})] * 20
        ex, engine = self._executor(responses, max_steps=3)
        ex._tools["loop_tool"] = lambda: "ok"
        ex._specs["loop_tool"] = _make_spec_no_args("loop_tool")

        ex.run(messages=[ChatMessage(role="user", content="Go.")])
        assert engine.call_count == 3

    def test_system_prompt_prepended(self) -> None:
        ex, engine = self._executor(
            [_text_response("Done.")],
            system="You are a helpful assistant.",
        )
        self._register_weather(ex)
        ex.run(messages=[ChatMessage(role="user", content="Hi.")])

        first_request = engine.captured_requests[0]
        assert first_request.messages[0].role == "system"
        assert "helpful assistant" in first_request.messages[0].content

    def test_tool_output_json_serialised(self) -> None:
        """Dict output from tool should be JSON in tool result message."""
        ex, engine = self._executor(
            [
                _tool_call_response("get_data", {"key": "x"}),
                _text_response("Got the data."),
            ]
        )
        ex._tools["get_data"] = lambda key: {"value": 42, "key": key}
        ex._specs["get_data"] = ToolSpec(
            name="get_data",
            description="Get data",
            parameters={"key": ToolParameterSchema(type="string", description="Key")},
            required_params=["key"],
        )
        ex.run(messages=[ChatMessage(role="user", content="Get data for x.")])

        second_request = engine.captured_requests[1]
        tool_msg = next(m for m in second_request.messages if m.role == "tool")
        import json

        parsed = json.loads(tool_msg.content)
        assert parsed["value"] == 42
