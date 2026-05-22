"""Tests for fact extraction patterns and LLM fallback."""
from __future__ import annotations
import json
import pytest
from engram.semantic.extractor import SemanticExtractor, ExtractedFact, ExtractionResult


# ---------------------------------------------------------------------------
# Pattern extraction
# ---------------------------------------------------------------------------

class PatternExtractor(SemanticExtractor):
    """Convenience: always pattern-only."""
    def __init__(self):
        super().__init__(pattern_only=True)


def extract(text):
    return PatternExtractor().extract(text).facts


# --- Preference patterns ---

def test_prefer_for():
    facts = extract("I prefer BeautifulSoup for HTML parsing.")
    prefs = [f for f in facts if f.fact_type == "preference"]
    assert len(prefs) >= 1
    pref = prefs[0]
    assert "beautifulsoup" in pref.value.lower() or "beautifulsoup" in pref.subject.lower()


def test_prefer_to():
    facts = extract("I prefer Python to JavaScript.")
    prefs = [f for f in facts if f.fact_type == "preference"]
    assert len(prefs) >= 1


def test_like_for():
    facts = extract("We like FastAPI for building REST APIs.")
    prefs = [f for f in facts if f.fact_type == "preference"]
    assert len(prefs) >= 1


def test_my_favorite():
    facts = extract("My favorite framework is Django.")
    prefs = [f for f in facts if f.fact_type == "preference"]
    assert len(prefs) >= 1


# --- Decision patterns ---

def test_decided_to_use():
    facts = extract("We decided to use PostgreSQL for the database.")
    decisions = [f for f in facts if f.fact_type == "decision"]
    assert len(decisions) >= 1
    assert "postgresql" in decisions[0].value.lower() or "postgresql" in decisions[0].subject.lower()


def test_going_with():
    facts = extract("We're going with Redis for caching.")
    decisions = [f for f in facts if f.fact_type == "decision"]
    assert len(decisions) >= 1


# --- Correction patterns ---

def test_actually_is():
    facts = extract("Actually, lxml is faster than BeautifulSoup.")
    corrections = [f for f in facts if f.fact_type == "correction"]
    assert len(corrections) >= 1


def test_correction_prefix():
    facts = extract("Correction: Python is the right language.")
    corrections = [f for f in facts if f.fact_type == "correction"]
    assert len(corrections) >= 1


# --- No match cases ---

def test_no_facts_generic_text():
    facts = extract("The weather is nice today.")
    assert len(facts) == 0


def test_no_facts_empty():
    facts = extract("")
    assert len(facts) == 0


def test_no_facts_greeting():
    facts = extract("Hello, how are you?")
    assert len(facts) == 0


# --- Confidence levels ---

def test_preference_confidence_level():
    """Preference patterns should have confidence ~0.7."""
    facts = extract("I prefer lxml for parsing.")
    prefs = [f for f in facts if f.fact_type == "preference"]
    if prefs:
        assert 0.5 <= prefs[0].confidence <= 0.95


def test_correction_higher_confidence():
    """Corrections should have higher confidence than preferences."""
    pref_facts = extract("I prefer lxml for parsing.")
    corr_facts = extract("Correction: lxml is the correct parser.")

    prefs = [f for f in pref_facts if f.fact_type == "preference"]
    corrs = [f for f in corr_facts if f.fact_type == "correction"]

    if prefs and corrs:
        assert corrs[0].confidence >= prefs[0].confidence


# --- ExtractionResult ---

def test_extraction_result_no_llm():
    extractor = PatternExtractor()
    result = extractor.extract("I prefer Python for scripting.")
    assert isinstance(result, ExtractionResult)
    assert result.llm_used is False
    assert isinstance(result.facts, list)


def test_extraction_result_llm_not_called_on_pattern_match():
    """LLM should not be called if patterns already found facts."""
    from unittest.mock import MagicMock

    llm = MagicMock()
    extractor = SemanticExtractor(llm_engine=llm, enable_llm_extraction=True)
    result = extractor.extract("I prefer lxml for HTML parsing.")

    # If patterns found something, LLM should not have been called
    if result.facts:
        llm.generate.assert_not_called()
        assert result.llm_used is False


# ---------------------------------------------------------------------------
# LLM fallback
# ---------------------------------------------------------------------------

def test_llm_fallback_on_no_pattern_match():
    """LLM is called when patterns find nothing."""
    from unittest.mock import MagicMock

    llm_response = json.dumps([
        {"type": "preference", "subject": "deployment", "value": "docker", "confidence": 0.8}
    ])
    mock_llm = MagicMock()
    mock_llm.generate.return_value.message.content = llm_response

    extractor = SemanticExtractor(llm_engine=mock_llm, enable_llm_extraction=True)
    result = extractor.extract("We ship everything in containers these days.")

    assert result.llm_used is True
    assert len(result.facts) == 1
    assert result.facts[0].fact_type == "preference"
    assert result.facts[0].subject == "deployment"
    assert result.facts[0].value == "docker"


def test_llm_fallback_handles_empty_response():
    """LLM returning empty list is handled gracefully."""
    from unittest.mock import MagicMock

    mock_llm = MagicMock()
    mock_llm.generate.return_value.message.content = "[]"

    extractor = SemanticExtractor(llm_engine=mock_llm, enable_llm_extraction=True)
    result = extractor.extract("The sky is blue today.")

    assert result.facts == []


def test_llm_fallback_handles_malformed_response():
    """LLM returning malformed JSON returns empty facts without crashing."""
    from unittest.mock import MagicMock

    mock_llm = MagicMock()
    mock_llm.generate.return_value.message.content = "not json {{{}"

    extractor = SemanticExtractor(llm_engine=mock_llm, enable_llm_extraction=True)
    result = extractor.extract("Some text that has no patterns.")

    assert result.facts == []
    assert result.llm_used is False  # LLM tried but parsing failed


def test_llm_fallback_handles_markdown_fences():
    """LLM response wrapped in markdown fences is parsed correctly."""
    from unittest.mock import MagicMock

    llm_response = '```json\n[{"type": "decision", "subject": "database", "value": "postgres", "confidence": 0.9}]\n```'
    mock_llm = MagicMock()
    mock_llm.generate.return_value.message.content = llm_response

    extractor = SemanticExtractor(llm_engine=mock_llm, enable_llm_extraction=True)
    result = extractor.extract("Thinking about which database to adopt.")

    assert result.llm_used is True
    assert len(result.facts) == 1
    assert result.facts[0].value == "postgres"


def test_llm_not_called_when_disabled():
    """LLM is never called when enable_llm_extraction=False."""
    from unittest.mock import MagicMock

    mock_llm = MagicMock()
    extractor = SemanticExtractor(llm_engine=mock_llm, enable_llm_extraction=False)
    result = extractor.extract("We should probably containerize our services soon.")

    mock_llm.generate.assert_not_called()


def test_llm_not_called_when_pattern_only():
    """pattern_only=True disables LLM even if llm_engine is provided."""
    from unittest.mock import MagicMock

    mock_llm = MagicMock()
    extractor = SemanticExtractor(llm_engine=mock_llm, pattern_only=True)
    extractor.extract("Some generic text without patterns.")

    mock_llm.generate.assert_not_called()


def test_llm_fallback_skips_facts_with_no_subject_or_value():
    """Facts missing subject or value are dropped."""
    from unittest.mock import MagicMock

    llm_response = json.dumps([
        {"type": "preference", "subject": "db", "value": "mysql", "confidence": 0.8},
        {"type": "preference", "subject": "", "value": "postgres"},  # No subject
        {"type": "decision", "subject": "cache"},                    # No value
    ])
    mock_llm = MagicMock()
    mock_llm.generate.return_value.message.content = llm_response

    extractor = SemanticExtractor(llm_engine=mock_llm, enable_llm_extraction=True)
    result = extractor.extract("Some text.")

    # Only first fact should be kept
    assert len(result.facts) == 1
    assert result.facts[0].value == "mysql"


def test_llm_failure_returns_empty():
    """LLM engine raising an exception returns empty facts."""
    from unittest.mock import MagicMock

    mock_llm = MagicMock()
    mock_llm.generate.side_effect = RuntimeError("LLM service unavailable")

    extractor = SemanticExtractor(llm_engine=mock_llm, enable_llm_extraction=True)
    result = extractor.extract("Some text without patterns.")

    assert result.facts == []
    assert result.llm_used is False


# ---------------------------------------------------------------------------
# Role filtering
# ---------------------------------------------------------------------------

def test_extract_from_user_role():
    extractor = PatternExtractor()
    result = extractor.extract("I prefer async Python for IO-bound tasks.", role="user")
    assert isinstance(result.facts, list)


def test_extract_from_assistant_role():
    extractor = PatternExtractor()
    result = extractor.extract("I recommend lxml for parsing.", role="assistant")
    assert isinstance(result.facts, list)
