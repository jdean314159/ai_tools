"""Cross-package tests for Engram semantic extraction with llm_engines engines."""
from __future__ import annotations

import json

from engram.semantic.extractor import SemanticExtractor
from llm_engines.backends.mock import MockEngine


def test_semantic_extractor_can_use_llm_engines_chat_model() -> None:
    payload = json.dumps([
        {
            "type": "preference",
            "subject": "parsing",
            "value": "lxml",
            "confidence": 0.82,
        }
    ])
    captured = {}

    def respond(request):
        captured["temperature"] = request.temperature
        captured["messages"] = request.messages
        return payload

    extractor = SemanticExtractor(
        llm_engine=MockEngine(response_fn=respond),
        enable_llm_extraction=True,
    )

    result = extractor.extract("Parsing libraries came up in review.")

    assert result.llm_used is True
    assert len(result.facts) == 1
    assert result.facts[0].fact_type == "preference"
    assert result.facts[0].subject == "parsing"
    assert result.facts[0].value == "lxml"
    assert captured["temperature"] == 0.0
    assert captured["messages"][0].role == "system"


def test_semantic_extractor_falls_back_to_empty_on_bad_llm_json() -> None:
    extractor = SemanticExtractor(
        llm_engine=MockEngine(response_fn=lambda request: "not json"),
        enable_llm_extraction=True,
    )

    result = extractor.extract("No pattern should match this sentence.")

    assert result.facts == []
    assert result.llm_used is False
