"""
contracts/tools.py

Tool specification and execution contracts.
Resolves the ToolSpec forward reference in engine.py.

ADR: ADR-003 (deferred to Phase 2, but ToolSpec needed now to unblock engine contracts)
Status: Minimal definition; full ADR pending
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Tool specification (what the model sees)
# ---------------------------------------------------------------------------

class ToolParameterSchema(BaseModel):
    """JSON Schema fragment describing a single tool parameter."""
    type: str                           # e.g. "string", "integer", "boolean"
    description: str
    enum: list[str] | None = None       # Allowed values, if constrained
    required: bool = False


class ToolSpec(BaseModel):
    """
    Description of a callable tool provided to the model.
    Serialises to the format expected by OpenAI-compatible tool APIs.
    """
    name: str
    description: str
    parameters: dict[str, ToolParameterSchema] = Field(default_factory=dict)
    required_params: list[str] = Field(default_factory=list)

    def to_openai_schema(self) -> dict[str, Any]:
        """Render as OpenAI-compatible function schema."""
        props = {
            name: {
                "type": param.type,
                "description": param.description,
                **({"enum": param.enum} if param.enum else {}),
            }
            for name, param in self.parameters.items()
        }
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": self.required_params,
                },
            },
        }


# ---------------------------------------------------------------------------
# Tool invocation and result (what the executor sees)
# ---------------------------------------------------------------------------

class ToolInvocation(BaseModel):
    """
    A validated tool call ready for execution.
    Created from a ToolCall (engine.py) after the model responds.
    """
    call_id: str                    # Matches ToolCall.call_id
    tool_name: str
    arguments: dict[str, Any]


ToolStatus = Literal["success", "error", "timeout"]


class ToolResult(BaseModel):
    """Result returned by a tool executor."""
    call_id: str                    # Matches ToolInvocation.call_id
    tool_name: str
    status: ToolStatus
    output: Any | None = None       # Structured output on success
    error_message: str | None = None
    execution_ms: float | None = None
