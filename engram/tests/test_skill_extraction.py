"""
tests/test_skill_extraction.py

Tests for the extended SynthesisExtractor — dual-output (rules + skills).

All tests are offline: no LLM, no Ollama.  The extractor is constructed with
engine_config=None (disabled) and we call _parse_response / _build_skill_records
directly, or we inject a fake engine via the standard adapter contract.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from engram.memory.synthesis import (
    SynthesisExtractor,
    SynthesisResult,
    SynthesisRule,
    _SYNTHESIS_PROMPT,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extractor(min_support=2, min_confidence=0.5) -> SynthesisExtractor:
    return SynthesisExtractor(
        engine_config=None,
        min_support=min_support,
        min_confidence=min_confidence,
    )


def _episodes(n=4) -> List[Dict[str, Any]]:
    return [{"id": f"ep_{i}", "text": f"Episode {i} content.", "role": "user"}
            for i in range(n)]


def _fake_engine(response: str) -> Any:
    eng = MagicMock()
    eng.generate.return_value = response
    return eng


def _extractor_with_engine(response: str, min_support=2, min_confidence=0.5):
    """Build an enabled extractor that returns a fixed LLM response."""
    ex = SynthesisExtractor(
        engine_config={"max_tokens": 512, "temperature": 0.2},
        min_support=min_support,
        min_confidence=min_confidence,
    )
    ex._engine = _fake_engine(response)
    return ex


# ---------------------------------------------------------------------------
# Prompt structure
# ---------------------------------------------------------------------------

class TestPromptStructure:

    def test_prompt_mentions_rules(self):
        assert "RULES" in _SYNTHESIS_PROMPT

    def test_prompt_mentions_skills(self):
        assert "SKILLS" in _SYNTHESIS_PROMPT

    def test_prompt_has_steps_schema(self):
        assert "steps" in _SYNTHESIS_PROMPT

    def test_prompt_has_trigger_schema(self):
        assert "trigger" in _SYNTHESIS_PROMPT

    def test_prompt_has_dual_output_schema(self):
        assert '"rules"' in _SYNTHESIS_PROMPT
        assert '"skills"' in _SYNTHESIS_PROMPT

    def test_prompt_formats_min_support(self):
        rendered = _SYNTHESIS_PROMPT.format(min_support=3, episodes="[0] test")
        assert "3" in rendered


# ---------------------------------------------------------------------------
# _parse_response — new object format
# ---------------------------------------------------------------------------

class TestParseResponseNewFormat:

    def test_parses_rules_and_skills(self):
        ex = _extractor()
        payload = json.dumps({
            "rules": [{"rule": "Use WAL pragma", "support_indices": [0, 1], "confidence": 0.9}],
            "skills": [{"name": "Setup WAL", "trigger": "when setting up SQLite",
                        "steps": ["Enable WAL", "Set sync=NORMAL"],
                        "support_indices": [0, 1], "confidence": 0.8}],
        })
        rules, skills = ex._parse_response(payload)
        assert len(rules) == 1
        assert len(skills) == 1

    def test_empty_arrays_ok(self):
        ex = _extractor()
        payload = json.dumps({"rules": [], "skills": []})
        rules, skills = ex._parse_response(payload)
        assert rules == [] and skills == []

    def test_missing_skills_key(self):
        ex = _extractor()
        payload = json.dumps({"rules": [{"rule": "X", "support_indices": [0], "confidence": 0.8}]})
        rules, skills = ex._parse_response(payload)
        assert len(rules) == 1
        assert skills == []

    def test_strips_markdown_fences(self):
        ex = _extractor()
        payload = '```json\n{"rules": [], "skills": []}\n```'
        rules, skills = ex._parse_response(payload)
        assert rules == [] and skills == []

    def test_fallback_bracket_search(self):
        ex = _extractor()
        payload = 'Here is the output: {"rules": [], "skills": []}'
        rules, skills = ex._parse_response(payload)
        assert rules == [] and skills == []

    def test_unparseable_returns_empty(self):
        ex = _extractor()
        rules, skills = ex._parse_response("this is not json at all")
        assert rules == [] and skills == []


# ---------------------------------------------------------------------------
# _parse_response — legacy array format (backward compat)
# ---------------------------------------------------------------------------

class TestParseResponseLegacyFormat:

    def test_legacy_array_treated_as_rules_only(self):
        ex = _extractor()
        payload = json.dumps([
            {"rule": "Old rule", "support_indices": [0, 1], "confidence": 0.9}
        ])
        rules, skills = ex._parse_response(payload)
        assert len(rules) == 1
        assert skills == []

    def test_legacy_empty_array(self):
        ex = _extractor()
        rules, skills = ex._parse_response("[]")
        assert rules == [] and skills == []


# ---------------------------------------------------------------------------
# _build_skill_records — validation
# ---------------------------------------------------------------------------

class TestBuildSkillRecords:

    def _raw_skill(self, **overrides) -> Dict[str, Any]:
        base = {
            "name": "Setup SQLite WAL",
            "trigger": "when creating a new SQLite table",
            "when_to_use": "Use when initialising any persistent store.",
            "steps": ["Add WAL pragma", "Set sync=NORMAL", "Test with PRAGMA integrity_check"],
            "examples": [{"input": "new DB", "output": "WAL enabled"}],
            "support_indices": [0, 1, 2],
            "confidence": 0.85,
        }
        base.update(overrides)
        return base

    def test_valid_skill_accepted(self):
        ex = _extractor(min_support=2)
        episodes = _episodes(5)
        skills = ex._build_skill_records([self._raw_skill()], episodes, "proj")
        assert len(skills) == 1

    def test_skill_fields_populated(self):
        ex = _extractor(min_support=2)
        skills = ex._build_skill_records([self._raw_skill()], _episodes(5), "proj")
        s = skills[0]
        assert s.name == "Setup SQLite WAL"
        assert s.trigger == "when creating a new SQLite table"
        assert len(s.steps) == 3
        assert s.confidence == pytest.approx(0.85)
        assert s.project_id == "proj"

    def test_source_metadata_set(self):
        ex = _extractor(min_support=2)
        skills = ex._build_skill_records([self._raw_skill()], _episodes(5), "")
        assert skills[0].metadata.get("source") == "synthesis"

    def test_support_episode_ids_resolved(self):
        ex = _extractor(min_support=2)
        episodes = _episodes(5)
        skills = ex._build_skill_records([self._raw_skill(support_indices=[0, 2])], episodes, "")
        assert "ep_0" in skills[0].support_episode_ids
        assert "ep_2" in skills[0].support_episode_ids

    def test_missing_name_dropped(self):
        ex = _extractor(min_support=2)
        raw = self._raw_skill(name="")
        skills = ex._build_skill_records([raw], _episodes(5), "")
        assert skills == []
        assert ex._skills_dropped_bad_format == 1

    def test_missing_trigger_dropped(self):
        ex = _extractor(min_support=2)
        raw = self._raw_skill(trigger="")
        skills = ex._build_skill_records([raw], _episodes(5), "")
        assert skills == []

    def test_single_step_dropped(self):
        """Single-step skills should be rules, not skills."""
        ex = _extractor(min_support=2)
        raw = self._raw_skill(steps=["Only one step"])
        skills = ex._build_skill_records([raw], _episodes(5), "")
        assert skills == []
        assert ex._skills_dropped_bad_format >= 1

    def test_zero_steps_dropped(self):
        ex = _extractor(min_support=2)
        skills = ex._build_skill_records([self._raw_skill(steps=[])], _episodes(5), "")
        assert skills == []

    def test_low_support_dropped(self):
        ex = _extractor(min_support=3)
        raw = self._raw_skill(support_indices=[0, 1])  # only 2 episodes
        skills = ex._build_skill_records([raw], _episodes(5), "")
        assert skills == []
        assert ex._skills_dropped_low_support == 1

    def test_support_indices_out_of_range_ignored(self):
        ex = _extractor(min_support=2)
        raw = self._raw_skill(support_indices=[0, 99, 1])  # 99 is OOB
        skills = ex._build_skill_records([raw], _episodes(5), "")
        # 0 and 1 are valid → 2 valid → meets min_support=2
        assert len(skills) == 1
        assert len(skills[0].support_episode_ids) == 2

    def test_low_confidence_dropped(self):
        ex = _extractor(min_confidence=0.7)
        raw = self._raw_skill(confidence=0.5)
        skills = ex._build_skill_records([raw], _episodes(5), "")
        assert skills == []
        assert ex._skills_dropped_low_confidence == 1

    def test_steps_capped_at_max(self):
        from engram.memory.synthesis import _MAX_SKILL_STEPS
        ex = _extractor(min_support=2)
        long_steps = [f"Step {i}" for i in range(_MAX_SKILL_STEPS + 5)]
        raw = self._raw_skill(steps=long_steps)
        skills = ex._build_skill_records([raw], _episodes(5), "")
        assert len(skills[0].steps) == _MAX_SKILL_STEPS

    def test_examples_capped_at_three(self):
        ex = _extractor(min_support=2)
        many_examples = [{"input": f"q{i}", "output": f"a{i}"} for i in range(10)]
        raw = self._raw_skill(examples=many_examples)
        skills = ex._build_skill_records([raw], _episodes(5), "")
        assert len(skills[0].examples) <= 3

    def test_non_dict_examples_filtered(self):
        ex = _extractor(min_support=2)
        raw = self._raw_skill(examples=["not a dict", {"input": "ok", "output": "good"}, 42])
        skills = ex._build_skill_records([raw], _episodes(5), "")
        assert len(skills[0].examples) == 1

    def test_trigger_truncated_to_max(self):
        from engram.memory.synthesis import _MAX_TRIGGER_LEN
        ex = _extractor(min_support=2)
        long_trigger = "x" * (_MAX_TRIGGER_LEN + 100)
        raw = self._raw_skill(trigger=long_trigger)
        skills = ex._build_skill_records([raw], _episodes(5), "")
        assert len(skills[0].trigger) == _MAX_TRIGGER_LEN

    def test_multiple_skills_all_accepted(self):
        ex = _extractor(min_support=2)
        raws = [
            self._raw_skill(name="Skill A", trigger="trigger A"),
            self._raw_skill(name="Skill B", trigger="trigger B"),
        ]
        skills = ex._build_skill_records(raws, _episodes(5), "")
        assert len(skills) == 2

    def test_empty_raw_list_returns_empty(self):
        ex = _extractor()
        assert ex._build_skill_records([], _episodes(5), "") == []


# ---------------------------------------------------------------------------
# SynthesisResult
# ---------------------------------------------------------------------------

class TestSynthesisResult:

    def test_empty_with_no_rules_skills_relations(self):
        r = SynthesisResult()
        assert r.empty is True

    def test_not_empty_when_skills_present(self):
        from engram.memory.procedural import Skill
        r = SynthesisResult()
        r.skills = [Skill(name="X", trigger="Y", steps=["a", "b"])]
        assert r.empty is False

    def test_not_empty_when_rules_present(self):
        r = SynthesisResult()
        r.rules = [SynthesisRule(rule_text="Do X")]
        assert r.empty is False

    def test_skills_field_defaults_to_empty_list(self):
        r = SynthesisResult()
        assert r.skills == []


# ---------------------------------------------------------------------------
# Full extract() integration with fake engine
# ---------------------------------------------------------------------------

class TestExtractIntegration:

    def _good_response(self) -> str:
        return json.dumps({
            "rules": [
                {"rule": "Always use WAL", "support_indices": [0, 1, 2], "confidence": 0.9}
            ],
            "skills": [
                {
                    "name": "Enable WAL on SQLite",
                    "trigger": "when creating a SQLite store",
                    "when_to_use": "Any time you initialise a new SQLite database.",
                    "steps": ["Execute PRAGMA journal_mode=WAL", "Set synchronous=NORMAL",
                              "Verify with PRAGMA integrity_check"],
                    "examples": [{"input": "new db", "output": "WAL active"}],
                    "support_indices": [0, 1, 2],
                    "confidence": 0.85,
                }
            ],
        })

    def test_extract_returns_rules_and_skills(self):
        ex = _extractor_with_engine(self._good_response(), min_support=2)
        result = ex.extract(_episodes(5), project_id="test")
        assert len(result.rules) == 1
        assert len(result.skills) == 1

    def test_extract_skill_name_correct(self):
        ex = _extractor_with_engine(self._good_response(), min_support=2)
        result = ex.extract(_episodes(5), project_id="test")
        assert result.skills[0].name == "Enable WAL on SQLite"

    def test_extract_skill_steps_correct(self):
        ex = _extractor_with_engine(self._good_response(), min_support=2)
        result = ex.extract(_episodes(5), project_id="test")
        assert len(result.skills[0].steps) == 3

    def test_extract_stats_updated(self):
        ex = _extractor_with_engine(self._good_response(), min_support=2)
        ex.extract(_episodes(5), project_id="test")
        assert ex.stats["extractions"] == 1
        assert ex.stats["rules_emitted"] == 1
        assert ex.stats["skills_emitted"] == 1

    def test_extract_legacy_array_response(self):
        """Old array-format response: rules populated, skills empty."""
        legacy = json.dumps([
            {"rule": "Old style rule", "support_indices": [0, 1, 2], "confidence": 0.9}
        ])
        ex = _extractor_with_engine(legacy, min_support=2)
        result = ex.extract(_episodes(5), project_id="test")
        assert len(result.rules) == 1
        assert result.skills == []

    def test_extract_disabled_returns_skipped(self):
        ex = _extractor()
        result = ex.extract(_episodes(5))
        assert result.skipped_reason == "extractor_disabled"
        assert result.skills == []

    def test_extract_window_too_small(self):
        ex = _extractor_with_engine("{}", min_support=5)
        result = ex.extract(_episodes(3))
        assert result.skipped_reason is not None
        assert "window_too_small" in result.skipped_reason

    def test_extract_empty_skills_in_response(self):
        payload = json.dumps({"rules": [], "skills": []})
        ex = _extractor_with_engine(payload, min_support=2)
        result = ex.extract(_episodes(5))
        assert result.rules == [] and result.skills == []

    def test_extract_skill_without_embedding(self):
        """Skills extracted from synthesis have no embedding — Phase C adds it."""
        ex = _extractor_with_engine(self._good_response(), min_support=2)
        result = ex.extract(_episodes(5), project_id="proj")
        assert result.skills[0].embedding is None
