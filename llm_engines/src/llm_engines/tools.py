"""
llm_engines/tools.py

ToolExecutor: closes the agentic tool-calling loop.

The model decides which tools to call; ToolExecutor calls them and feeds
results back until the model produces a final text response or the step
limit is reached.

Usage:
    from llm_engines.tools import ToolExecutor, tool
    from llm_engines import EngineFactory

    engine = EngineFactory.create("anthropic", model="claude-sonnet-4-6")
    executor = ToolExecutor(engine)

    @executor.register
    def get_weather(city: str) -> str:
        return f"Sunny, 22°C in {city}"

    response = executor.run(
        messages=[ChatMessage(role="user", content="What's the weather in Paris?")]
    )
    print(response.message.content)

Design:
    - Tools are plain Python callables (sync or async).
    - ToolSpec is generated automatically from type annotations and docstrings.
    - The executor manages the conversation history internally.
    - max_steps prevents infinite loops.
    - Errors in tool execution are returned as tool results (not raised),
      so the model can handle them gracefully.
"""
from __future__ import annotations

import inspect
import json
import logging
import time
from typing import Any, Callable

from llm_engines.contracts import (
    ChatMessage,
    GenerationRequest,
    GenerationResponse,
    ToolCall,
    ToolCallingModel,
    UsageStats,
)
from llm_engines.contracts import (
    ToolInvocation,
    ToolParameterSchema,
    ToolResult,
    ToolSpec,
)

logger = logging.getLogger(__name__)

# Python type → JSON Schema type
_PY_TO_JSON: dict[str, str] = {
    "str":   "string",
    "int":   "integer",
    "float": "number",
    "bool":  "boolean",
    "list":  "array",
    "dict":  "object",
}


def _infer_tool_spec(fn: Callable[..., Any], name: str | None = None) -> ToolSpec:
    """
    Build a ToolSpec from a Python callable's signature and docstring.

    Type annotations are used for parameter types. The docstring is used
    as the tool description. Parameters without annotations default to
    "string".
    """
    sig = inspect.signature(fn)
    doc = inspect.getdoc(fn) or f"Call {fn.__name__}"
    tool_name = name or fn.__name__

    params: dict[str, ToolParameterSchema] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue

        # Infer JSON type from annotation
        annotation = param.annotation
        if annotation is inspect.Parameter.empty:
            json_type = "string"
        else:
            type_name = getattr(annotation, "__name__", str(annotation))
            json_type = _PY_TO_JSON.get(type_name, "string")

        # Extract parameter description from docstring if present
        param_doc = ""
        if doc:
            for line in doc.splitlines():
                line = line.strip()
                if line.startswith(f"{param_name}:") or line.startswith(f"{param_name} "):
                    param_doc = line.split(":", 1)[-1].strip()
                    break

        params[param_name] = ToolParameterSchema(
            type=json_type,
            description=param_doc or param_name,
        )

        # Required if no default value
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    # Use first line of docstring as description
    description = doc.splitlines()[0] if doc else tool_name

    return ToolSpec(
        name=tool_name,
        description=description,
        parameters=params,
        required_params=required,
    )


class ToolExecutor:
    """
    Manages the tool-calling loop for a ToolCallingModel engine.

    Args:
        engine:      A ChatModel that also implements ToolCallingModel.
        max_steps:   Maximum number of tool-call rounds before stopping.
                     Prevents infinite loops. Default 10.
        system:      Optional system prompt prepended to every conversation.
    """

    def __init__(
        self,
        engine: Any,
        max_steps: int = 10,
        system: str | None = None,
    ) -> None:
        if not isinstance(engine, ToolCallingModel):
            raise TypeError(
                f"{type(engine).__name__} does not implement ToolCallingModel. "
                "Use AnthropicEngine or OpenAIEngine."
            )
        self.engine = engine
        self.max_steps = max_steps
        self.system = system

        self._tools: dict[str, Callable[..., Any]] = {}
        self._specs: dict[str, ToolSpec] = {}

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def register(
        self,
        fn: Callable[..., Any] | None = None,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Callable[..., Any]:
        """
        Register a callable as a tool. Use as a decorator or call directly.

        Examples:
            @executor.register
            def get_weather(city: str) -> str:
                "Get current weather for a city."
                return f"Sunny in {city}"

            executor.register(my_function, name="custom_name")
        """
        def _register(f: Callable[..., Any]) -> Callable[..., Any]:
            spec = _infer_tool_spec(f, name=name)
            if description:
                spec = spec.model_copy(update={"description": description})
            tool_name = spec.name
            self._tools[tool_name] = f
            self._specs[tool_name] = spec
            logger.debug("Registered tool: %s", tool_name)
            return f

        if fn is not None:
            return _register(fn)
        return _register

    def register_spec(self, spec: ToolSpec, fn: Callable[..., Any]) -> None:
        """Register a tool with an explicit ToolSpec (no auto-inference)."""
        self._tools[spec.name] = fn
        self._specs[spec.name] = spec

    @property
    def available_tools(self) -> list[ToolSpec]:
        return list(self._specs.values())

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run(
        self,
        messages: list[ChatMessage],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        thinking: bool | None = None,
        seed: int | None = None,
    ) -> GenerationResponse:
        """
        Run the tool-calling loop until the model produces a final response.

        The loop:
          1. Call engine.generate_with_tools() with current messages
          2. If response contains tool_calls: execute each, append results
          3. Repeat until finish_reason == "stop" or max_steps reached

        Returns the final GenerationResponse (finish_reason="stop").
        """
        if not self._tools:
            raise RuntimeError(
                "No tools registered. Use @executor.register before calling run()."
            )

        # Build message history, prepending system prompt if set
        history: list[ChatMessage] = []
        if self.system:
            history.append(ChatMessage(role="system", content=self.system))
        history.extend(messages)

        specs = self.available_tools
        last_response: GenerationResponse | None = None

        for step in range(self.max_steps):
            request = GenerationRequest(
                messages=history,
                max_tokens=max_tokens,
                temperature=temperature,
                thinking=thinking,
                seed=seed,
            )

            logger.debug("Step %d: calling engine with %d messages", step + 1, len(history))
            response = self.engine.generate_with_tools(request, specs)
            last_response = response

            # No tool calls — model is done
            if response.finish_reason != "tool_call" or not response.message.tool_calls:
                logger.debug("Step %d: done (finish_reason=%s)", step + 1, response.finish_reason)
                return response

            # Append assistant message with tool calls to history
            history.append(response.message)

            # Execute each tool call and collect results
            tool_results = self._execute_tool_calls(response.message.tool_calls)

            # Append tool results as tool messages
            for result in tool_results:
                content = self._format_result(result)
                history.append(ChatMessage(
                    role="tool",
                    content=content,
                    tool_call_id=result.call_id,
                    name=result.tool_name,
                ))

            logger.debug(
                "Step %d: executed %d tools, continuing", step + 1, len(tool_results)
            )

        logger.warning(
            "ToolExecutor reached max_steps=%d without a final response", self.max_steps
        )
        # Return the last response even if it still has tool calls
        return last_response or GenerationResponse(
            message=ChatMessage(role="assistant", content="[max steps reached]"),
            finish_reason="stop",
            usage=UsageStats(),
            model_name="unknown",
            backend="tool_executor",
        )

    def _execute_tool_calls(self, tool_calls: list[ToolCall]) -> list[ToolResult]:
        """Execute all tool calls and return results. Errors are captured, not raised."""
        results = []
        for call in tool_calls:
            t0 = time.perf_counter()
            if call.name not in self._tools:
                results.append(ToolResult(
                    call_id=call.call_id,
                    tool_name=call.name,
                    status="error",
                    error_message=f"Unknown tool '{call.name}'. Available: {list(self._tools)}",
                    execution_ms=0.0,
                ))
                continue

            fn = self._tools[call.name]
            try:
                output = fn(**call.arguments)
                elapsed = (time.perf_counter() - t0) * 1000
                results.append(ToolResult(
                    call_id=call.call_id,
                    tool_name=call.name,
                    status="success",
                    output=output,
                    execution_ms=round(elapsed, 3),
                ))
                logger.debug(
                    "Tool %s completed in %.1fms", call.name, elapsed
                )
            except Exception as e:
                elapsed = (time.perf_counter() - t0) * 1000
                logger.warning("Tool %s failed: %s", call.name, e)
                results.append(ToolResult(
                    call_id=call.call_id,
                    tool_name=call.name,
                    status="error",
                    error_message=str(e),
                    execution_ms=round(elapsed, 3),
                ))
        return results

    def _format_result(self, result: ToolResult) -> str:
        """Format a ToolResult as a string for the model to read."""
        if result.status == "error":
            return f"Error: {result.error_message}"
        if isinstance(result.output, str):
            return result.output
        try:
            return json.dumps(result.output, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(result.output)


# ---------------------------------------------------------------------------
# Convenience decorator (module-level, for use without an executor instance)
# ---------------------------------------------------------------------------

def tool(
    fn: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
) -> Callable[..., Any]:
    """
    Decorator that marks a function as a tool and attaches its ToolSpec.

    The ToolSpec is inferred from the function's signature and docstring.
    Use with ToolExecutor.register_spec() to register pre-decorated tools.

    Example:
        @tool
        def search_web(query: str) -> str:
            "Search the web for information."
            ...

        executor.register_spec(search_web._tool_spec, search_web)
    """
    def _wrap(f: Callable[..., Any]) -> Callable[..., Any]:
        spec = _infer_tool_spec(f, name=name)
        setattr(f, "_tool_spec", spec)
        return f

    if fn is not None:
        return _wrap(fn)
    return _wrap
