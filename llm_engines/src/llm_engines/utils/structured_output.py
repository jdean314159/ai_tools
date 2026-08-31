"""Robust structured-output parsing helpers for LLM responses.

This module is adapted from mature Engram utility code, but kept as a
standalone helper for the ``llm_engines`` package. It does not change the
engine contracts; it simply makes it easier for callers to recover typed data
from model text output.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

_json_repair: Any = None
try:  # optional dependency
    import json_repair

    _json_repair = json_repair

    _HAS_JSON_REPAIR = True
except ImportError:  # pragma: no cover - exercised via behavior tests
    _HAS_JSON_REPAIR = False


@dataclass(frozen=True)
class ParseResult:
    """Result of a structured-output parsing attempt."""

    success: bool
    data: BaseModel | None
    raw_output: str
    extracted_json: str | None
    error: str | None
    repair_attempted: bool


class StructuredOutputError(Exception):
    """Raised when structured output parsing fails.

    Includes the raw output, extracted JSON (if any), and the expected schema
    in the rendered exception text to simplify debugging.
    """

    def __init__(
        self,
        message: str,
        raw_output: str,
        extracted_json: str | None,
        model_class: type[BaseModel],
    ) -> None:
        self.message = message
        self.raw_output = raw_output
        self.extracted_json = extracted_json
        self.model_class = model_class

        details = [
            f"Structured Output Parsing Failed: {message}",
            "",
            f"Expected Model: {model_class.__name__}",
            "",
        ]

        if len(raw_output) > 500:
            details.extend(
                [
                    "Raw Output (first 500 chars):",
                    raw_output[:500] + "...",
                    "",
                ]
            )
        else:
            details.extend(["Raw Output:", raw_output, ""])

        if extracted_json:
            if len(extracted_json) > 500:
                details.extend(
                    [
                        "Extracted JSON (first 500 chars):",
                        extracted_json[:500] + "...",
                        "",
                    ]
                )
            else:
                details.extend(["Extracted JSON:", extracted_json, ""])

        details.extend(
            [
                "Expected Schema:",
                json.dumps(model_class.model_json_schema(), indent=2),
            ]
        )
        super().__init__("\n".join(details))


def _strip_think_blocks(raw_output: str) -> str:
    stripped = re.sub(r"<think>.*?</think>\s*", "", raw_output, flags=re.DOTALL | re.IGNORECASE)
    open_match = re.search(r"<think>", stripped, flags=re.IGNORECASE)
    if open_match and not re.search(r"</think>", stripped, flags=re.IGNORECASE):
        stripped = stripped[: open_match.start()]
    return stripped


class StructuredOutputHandler:
    """Parse JSON-like model output into typed Pydantic objects."""

    @staticmethod
    def parse(
        raw_output: str,
        model_class: type[T],
        strict: bool = False,
        allow_repair: bool = True,
    ) -> T:
        """Parse LLM output into a Pydantic model or raise with context."""
        result = StructuredOutputHandler.parse_with_details(
            raw_output=raw_output,
            model_class=model_class,
            strict=strict,
            allow_repair=allow_repair,
        )
        if not result.success:
            raise StructuredOutputError(
                message=result.error or "Unknown structured-output parse error",
                raw_output=raw_output,
                extracted_json=result.extracted_json,
                model_class=model_class,
            )
        data = result.data
        assert data is not None
        return data  # type: ignore[return-value]

    @staticmethod
    def parse_with_details(
        raw_output: str,
        model_class: type[T],
        strict: bool = False,
        allow_repair: bool = True,
    ) -> ParseResult:
        """Parse with full success/failure metadata instead of raising."""
        extracted = StructuredOutputHandler._extract_json(raw_output)
        if not extracted:
            return ParseResult(
                success=False,
                data=None,
                raw_output=raw_output,
                extracted_json=None,
                error="No JSON found in response",
                repair_attempted=False,
            )

        try:
            data = model_class.model_validate_json(extracted)
            return ParseResult(
                success=True,
                data=data,
                raw_output=raw_output,
                extracted_json=extracted,
                error=None,
                repair_attempted=False,
            )
        except (json.JSONDecodeError, ValidationError) as exc:
            if strict:
                return ParseResult(
                    success=False,
                    data=None,
                    raw_output=raw_output,
                    extracted_json=extracted,
                    error=f"Strict mode: {exc}",
                    repair_attempted=False,
                )
            if allow_repair:
                try:
                    if not _HAS_JSON_REPAIR or _json_repair is None:
                        raise ImportError("json_repair not installed")
                    repaired = _json_repair.loads(extracted)
                    data = model_class.model_validate(repaired)
                    return ParseResult(
                        success=True,
                        data=data,
                        raw_output=raw_output,
                        extracted_json=extracted,
                        error=None,
                        repair_attempted=True,
                    )
                except Exception as repair_error:
                    return ParseResult(
                        success=False,
                        data=None,
                        raw_output=raw_output,
                        extracted_json=extracted,
                        error=f"Parse failed: {exc}\nRepair failed: {repair_error}",
                        repair_attempted=True,
                    )
            return ParseResult(
                success=False,
                data=None,
                raw_output=raw_output,
                extracted_json=extracted,
                error=str(exc),
                repair_attempted=False,
            )

    @staticmethod
    def _extract_json(raw_output: str) -> str | None:
        """Extract the first JSON object/array from common LLM output formats."""
        if not raw_output or not raw_output.strip():
            return None

        raw_output = _strip_think_blocks(raw_output)

        json_block = re.search(
            r"```(?:json)?\s*\n?(.*?)\n?```", raw_output, re.DOTALL | re.IGNORECASE
        )
        if json_block:
            return json_block.group(1).strip()

        text = raw_output.strip()
        decoder = json.JSONDecoder()
        for i, char in enumerate(text):
            if char in "[{":
                try:
                    _obj, end_idx = decoder.raw_decode(text, i)
                    return text[i:end_idx]
                except json.JSONDecodeError:
                    continue

        try:
            json.loads(text)
            return text
        except (json.JSONDecodeError, ValueError):
            return None

    @staticmethod
    def create_schema_prompt(model_class: type[BaseModel], include_examples: bool = True) -> str:
        """Generate prompt instructions that ask a model for JSON matching a schema."""
        schema = model_class.model_json_schema()
        prompt_parts = [
            "Please format your response as valid JSON matching this schema:",
            "",
            "```json",
            json.dumps(schema, indent=2),
            "```",
            "",
            "IMPORTANT:",
            "- Return ONLY the JSON object, no other text",
            "- Use double quotes for strings",
            "- Do not include comments in the JSON",
            "- Ensure all required fields are present",
            "- Follow the exact field names shown in the schema",
        ]
        if include_examples and "properties" in schema:
            example = StructuredOutputHandler._generate_example(model_class)
            if example:
                prompt_parts.extend(
                    [
                        "",
                        "Example format:",
                        "```json",
                        json.dumps(example, indent=2),
                        "```",
                    ]
                )
        return "\n".join(prompt_parts)

    @staticmethod
    def _generate_example(model_class: type[BaseModel]) -> dict[str, object] | None:
        """Generate a simple example object from a model schema."""
        try:
            schema = model_class.model_json_schema()
            example: dict[str, object] = {}
            for field_name, field_info in schema.get("properties", {}).items():
                field_type = field_info.get("type", "string")
                if field_type == "string":
                    example[field_name] = f"example_{field_name}"
                elif field_type == "integer":
                    example[field_name] = 42
                elif field_type == "number":
                    example[field_name] = 3.14
                elif field_type == "boolean":
                    example[field_name] = True
                elif field_type == "array":
                    example[field_name] = ["item1", "item2"]
                elif field_type == "object":
                    example[field_name] = {"key": "value"}
            return example
        except Exception:
            return None

    @staticmethod
    def parse_multiple(
        raw_output: str,
        model_class: type[T],
        allow_repair: bool = True,
    ) -> list[T]:
        """Parse an array of objects, or a single object, into model instances."""
        extracted = StructuredOutputHandler._extract_json(raw_output)
        if not extracted:
            return []
        try:
            data = json.loads(extracted)
            if isinstance(data, list):
                results: list[T] = []
                for item in data:
                    try:
                        results.append(model_class.model_validate(item))
                    except ValidationError:
                        if allow_repair:
                            if not _HAS_JSON_REPAIR or _json_repair is None:
                                raise ImportError("json_repair not installed")
                            repaired = _json_repair.loads(json.dumps(item))
                            results.append(model_class.model_validate(repaired))
                        else:
                            raise
                return results
            return [model_class.model_validate(data)]
        except Exception as exc:
            raise StructuredOutputError(
                message=f"Failed to parse multiple objects: {exc}",
                raw_output=raw_output,
                extracted_json=extracted,
                model_class=model_class,
            )
