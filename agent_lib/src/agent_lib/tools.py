from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .contracts import ToolCall, ToolResult, ToolSpec
from .interop import describe_tool_runtime, tool_result_to_operation_result


@dataclass
class LocalTool:
    name: str
    description: str
    handler: Callable[..., Any]
    input_schema: dict[str, Any] = field(default_factory=dict)

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema=dict(self.input_schema),
        )


class LocalToolRuntime:
    def __init__(self, tools: list[LocalTool] | None = None) -> None:
        self._tools = {tool.name: tool for tool in tools or []}

    def describe_component(self):
        return describe_tool_runtime(self)

    def get_capability_descriptor(self):
        return describe_tool_runtime(self)

    def register(self, tool: LocalTool) -> None:
        self._tools[tool.name] = tool

    def list_tools(self) -> list[ToolSpec]:
        return [tool.spec() for tool in self._tools.values()]

    def invoke(self, call: ToolCall) -> ToolResult:
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(
                name=call.name,
                output=f"Unknown tool: {call.name}",
                success=False,
                meta={"error": "unknown_tool"},
            )
        try:
            output = tool.handler(**call.arguments)
        except Exception as exc:
            return ToolResult(
                name=call.name,
                output=str(exc),
                success=False,
                meta={"error": type(exc).__name__},
            )
        if isinstance(output, ToolResult):
            return output
        return ToolResult(name=call.name, output=output, success=True)

    def invoke_interop(self, call: ToolCall):
        result = self.invoke(call)
        op = tool_result_to_operation_result(result, call=call)
        diagnostics = dict(op.diagnostics)
        diagnostics["capability"] = describe_tool_runtime(self)
        return type(op).success(op.value, warnings=op.warnings, diagnostics=diagnostics)
