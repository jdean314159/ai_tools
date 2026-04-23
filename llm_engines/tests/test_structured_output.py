from __future__ import annotations

from pydantic import BaseModel
import pytest

from llm_engines import ParseResult, StructuredOutputError, StructuredOutputHandler


class Person(BaseModel):
    name: str
    age: int


class TestStructuredOutputParsing:
    def test_parse_plain_json(self) -> None:
        result = StructuredOutputHandler.parse('{"name": "Alice", "age": 30}', Person)
        assert result.name == "Alice"
        assert result.age == 30

    def test_parse_markdown_json_block(self) -> None:
        raw = "Here you go:\n```json\n{\"name\": \"Bob\", \"age\": 25}\n```"
        result = StructuredOutputHandler.parse(raw, Person)
        assert result.name == "Bob"
        assert result.age == 25

    def test_parse_json_with_preamble(self) -> None:
        raw = 'Answer follows. {"name": "Cara", "age": 41} Thanks.'
        result = StructuredOutputHandler.parse(raw, Person)
        assert result.name == "Cara"

    def test_parse_with_details_failure_no_json(self) -> None:
        details = StructuredOutputHandler.parse_with_details("not json at all", Person)
        assert isinstance(details, ParseResult)
        assert details.success is False
        assert details.error == "No JSON found in response"

    def test_strict_mode_reports_failure(self) -> None:
        details = StructuredOutputHandler.parse_with_details('{"name": "Alice", "age": "bad"}', Person, strict=True)
        assert details.success is False
        assert details.repair_attempted is False
        assert details.error is not None
        assert "Strict mode" in details.error

    def test_parse_raises_contextual_error(self) -> None:
        with pytest.raises(StructuredOutputError) as exc:
            StructuredOutputHandler.parse("not json", Person)
        message = str(exc.value)
        assert "Structured Output Parsing Failed" in message
        assert "Expected Model: Person" in message
        assert "Expected Schema:" in message

    def test_create_schema_prompt_contains_schema_and_example(self) -> None:
        prompt = StructuredOutputHandler.create_schema_prompt(Person)
        assert "Please format your response as valid JSON matching this schema" in prompt
        assert "Example format:" in prompt
        assert "name" in prompt
        assert "age" in prompt

    def test_parse_multiple_array(self) -> None:
        raw = '[{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]'
        results = StructuredOutputHandler.parse_multiple(raw, Person)
        assert [p.name for p in results] == ["Alice", "Bob"]

    def test_parse_multiple_single_object_returns_singleton(self) -> None:
        raw = '{"name": "Alice", "age": 30}'
        results = StructuredOutputHandler.parse_multiple(raw, Person)
        assert len(results) == 1
        assert results[0].name == "Alice"
