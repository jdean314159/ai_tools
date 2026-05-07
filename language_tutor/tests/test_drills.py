"""
test_drills.py

Unit tests for DrillSystem logic that requires no LLM, memory, or network.

Coverage:
  - check_dictation():   word-level accuracy + feedback thresholds
  - _check_exact():      accent-tolerant matching (ñ, á, é, í, ó, ú, ü)
  - check_answer():      stat tracking (_attempts, _correct, _mistake_log)
  - get_session_accuracy() / get_session_stats()
  - get_question() returns well-formed DrillQuestion for all types
  - _check_translation() falls back gracefully without engine
  - recommend_drill_type() falls back to day-of-week schedule
  - language dispatch: spanish vs latin
"""
from __future__ import annotations

import pytest

from language_tutor.drills.drill_system import DrillQuestion, DrillResult, DrillSystem


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def spanish_drills() -> DrillSystem:
    return DrillSystem(language="spanish")


@pytest.fixture
def latin_drills() -> DrillSystem:
    return DrillSystem(language="latin")


def _make_question(
    drill_type: str = "irregular_verb",
    correct_answer: str = "fui",
    context: str = "",
) -> DrillQuestion:
    return DrillQuestion(
        question_id=f"test_{drill_type}",
        drill_type=drill_type,
        prompt="Conjugate:",
        correct_answer=correct_answer,
        context=context,
    )


# ---------------------------------------------------------------------------
# check_dictation()
# ---------------------------------------------------------------------------

class TestCheckDictation:
    def test_exact_match_is_correct(self, spanish_drills):
        r = spanish_drills.check_dictation(
            "Ayer fui al mercado", "Ayer fui al mercado"
        )
        assert r.correct is True
        assert r.accuracy == 1.0
        assert "Perfecto" in r.feedback

    def test_case_insensitive(self, spanish_drills):
        r = spanish_drills.check_dictation("Hola mundo", "hola mundo")
        assert r.correct is True

    def test_partial_match_scoring(self, spanish_drills):
        # 3 correct of 4 expected words = 0.75
        r = spanish_drills.check_dictation(
            "ayer fui al mercado", "ayer fui al parque"
        )
        assert r.correct is False
        assert abs(r.accuracy - 0.75) < 0.01

    def test_zero_correct_gives_zero_accuracy(self, spanish_drills):
        r = spanish_drills.check_dictation("uno dos tres", "a b c")
        assert r.accuracy == 0.0
        assert r.correct is False

    def test_high_partial_feedback_muy_bien(self, spanish_drills):
        # 4/4 words correct → Perfecto; 3/4 is 0.75, between 0.5 and 0.8
        r = spanish_drills.check_dictation("a b c d", "a b c x")
        assert "bien" in r.feedback.lower() or "intento" in r.feedback.lower()

    def test_empty_expected_returns_zero(self, spanish_drills):
        r = spanish_drills.check_dictation("", "anything")
        assert r.accuracy == 0.0

    def test_extra_words_do_not_boost_accuracy(self, spanish_drills):
        # 2 expected words, user provides 5 — score based on expected length
        r = spanish_drills.check_dictation("hola mundo", "hola mundo extra words here")
        assert r.accuracy == 1.0  # first 2 words still match

    def test_result_fields_populated(self, spanish_drills):
        r = spanish_drills.check_dictation("test sentence", "test answer")
        assert r.user_answer == "test answer"
        assert r.correct_answer == "test sentence"
        assert r.drill_type == "dictation"
        assert r.question_id == ""


# ---------------------------------------------------------------------------
# _check_exact() — accent tolerance
# ---------------------------------------------------------------------------

class TestCheckExact:
    def test_exact_match_correct(self, spanish_drills):
        q = _make_question(correct_answer="fui")
        r = spanish_drills._check_exact(q, "fui")
        assert r.correct is True
        assert r.accuracy == 1.0

    def test_case_insensitive(self, spanish_drills):
        q = _make_question(correct_answer="Fui")
        r = spanish_drills._check_exact(q, "fui")
        assert r.correct is True

    def test_accent_stripped_match(self, spanish_drills):
        q = _make_question(correct_answer="está")
        r = spanish_drills._check_exact(q, "esta")
        assert r.correct is True

    @pytest.mark.parametrize("accented,plain", [
        ("fútbol", "futbol"),
        ("niño",   "nino"),
        ("über",   "uber"),
        ("señor",  "senor"),
        ("año",    "ano"),
    ])
    def test_accent_variants(self, spanish_drills, accented, plain):
        q = _make_question(correct_answer=accented)
        r = spanish_drills._check_exact(q, plain)
        assert r.correct is True

    def test_wrong_answer_not_correct(self, spanish_drills):
        q = _make_question(correct_answer="fui")
        r = spanish_drills._check_exact(q, "iba")
        assert r.correct is False
        assert r.accuracy == 0.0

    def test_wrong_feedback_includes_correct_answer(self, spanish_drills):
        q = _make_question(correct_answer="fui")
        r = spanish_drills._check_exact(q, "iba")
        assert "fui" in r.feedback

    def test_correct_feedback_is_positive(self, spanish_drills):
        q = _make_question(correct_answer="fui")
        r = spanish_drills._check_exact(q, "fui")
        positive = ("Correcto", "Exacto", "Muy bien", "Perfecto")
        assert any(p in r.feedback for p in positive)


# ---------------------------------------------------------------------------
# check_answer() — stat tracking
# ---------------------------------------------------------------------------

class TestCheckAnswerStats:
    def test_attempts_increments(self, spanish_drills):
        q = _make_question(correct_answer="fui")
        assert spanish_drills._attempts == 0
        spanish_drills.check_answer(q, "fui")
        assert spanish_drills._attempts == 1

    def test_correct_counter_increments_on_correct(self, spanish_drills):
        q = _make_question(correct_answer="fui")
        spanish_drills.check_answer(q, "fui")
        assert spanish_drills._correct == 1

    def test_correct_counter_not_incremented_on_wrong(self, spanish_drills):
        q = _make_question(correct_answer="fui")
        spanish_drills.check_answer(q, "iba")
        assert spanish_drills._correct == 0

    def test_mistake_logged_on_wrong_answer(self, spanish_drills):
        q = _make_question(drill_type="irregular_verb", correct_answer="fui")
        spanish_drills.check_answer(q, "iba")
        assert len(spanish_drills._mistake_log) == 1
        log = spanish_drills._mistake_log[0]
        assert log["correct_answer"] == "fui"
        assert log["user_answer"] == "iba"
        assert log["drill_type"] == "irregular_verb"

    def test_correct_answer_not_logged_as_mistake(self, spanish_drills):
        q = _make_question(correct_answer="fui")
        spanish_drills.check_answer(q, "fui")
        assert len(spanish_drills._mistake_log) == 0

    def test_multiple_rounds(self, spanish_drills):
        q = _make_question(correct_answer="fui")
        spanish_drills.check_answer(q, "fui")   # correct
        spanish_drills.check_answer(q, "iba")   # wrong
        spanish_drills.check_answer(q, "fui")   # correct
        assert spanish_drills._attempts == 3
        assert spanish_drills._correct == 2
        assert len(spanish_drills._mistake_log) == 1


# ---------------------------------------------------------------------------
# Session accuracy / stats
# ---------------------------------------------------------------------------

class TestSessionStats:
    def test_accuracy_zero_before_any_attempt(self, spanish_drills):
        assert spanish_drills.get_session_accuracy() == 0.0

    def test_accuracy_100_percent(self, spanish_drills):
        q = _make_question(correct_answer="fui")
        spanish_drills.check_answer(q, "fui")
        assert spanish_drills.get_session_accuracy() == 1.0

    def test_accuracy_50_percent(self, spanish_drills):
        q = _make_question(correct_answer="fui")
        spanish_drills.check_answer(q, "fui")
        spanish_drills.check_answer(q, "iba")
        assert abs(spanish_drills.get_session_accuracy() - 0.5) < 0.01

    def test_get_session_stats_shape(self, spanish_drills):
        q = _make_question(correct_answer="fui")
        spanish_drills.check_answer(q, "fui")
        stats = spanish_drills.get_session_stats()
        assert stats["attempts"] == 1
        assert stats["correct"] == 1
        assert stats["accuracy"] == 1.0
        assert isinstance(stats["mistakes"], list)


# ---------------------------------------------------------------------------
# get_question() — Spanish drill types return well-formed DrillQuestion
# ---------------------------------------------------------------------------

SPANISH_DRILL_TYPES = [
    "irregular_verbs_preterite",
    "irregular_verbs_imperfect",
    "reflexive_verbs",
    "prepositions",
    "sentence_dictation",
    "listening_comprehension",
    "mixed_review",
    "pronunciation",
]

LATIN_DRILL_TYPES = [
    "irregular_verbs_present",
    "irregular_verbs_imperfect",
    "noun_declensions",
    "prepositions",
    "sentence_dictation",
    "mixed_review",
]


@pytest.mark.parametrize("drill_type", SPANISH_DRILL_TYPES)
def test_spanish_drill_types_return_well_formed_question(drill_type):
    drills = DrillSystem(language="spanish")
    q = drills.get_question(drill_type)
    assert isinstance(q, DrillQuestion)
    assert q.prompt
    assert q.correct_answer
    assert q.question_id
    assert q.drill_type


@pytest.mark.parametrize("drill_type", LATIN_DRILL_TYPES)
def test_latin_drill_types_return_well_formed_question(drill_type):
    drills = DrillSystem(language="latin")
    q = drills.get_question(drill_type)
    assert isinstance(q, DrillQuestion)
    assert q.prompt
    assert q.correct_answer


def test_unknown_drill_type_falls_back_to_mixed(spanish_drills):
    q = spanish_drills.get_question("nonexistent_type")
    assert isinstance(q, DrillQuestion)


# ---------------------------------------------------------------------------
# _check_translation() without engine falls back to fuzzy dictation
# ---------------------------------------------------------------------------

def test_translation_check_falls_back_to_dictation_without_engine(spanish_drills):
    assert spanish_drills.engine is None
    q = _make_question(
        drill_type="translation",
        correct_answer="Voy al mercado",
        context="I go to the market",
    )
    r = spanish_drills.check_answer(q, "Voy al mercado")
    # With no engine, falls back to dictation — exact match should pass
    assert r.correct is True


def test_translation_empty_answer_returns_false(spanish_drills):
    q = _make_question(drill_type="translation", correct_answer="algo")
    r = spanish_drills._check_translation(q, "")
    assert r.correct is False
    assert "Please enter" in r.feedback


def test_translation_with_engine_calls_engine(spanish_drills):
    """Engine returns JSON; _check_translation should parse it correctly."""
    import json

    class FakeTranslationEngine:
        def generate(self, prompt: str, **kwargs) -> str:
            return json.dumps({"correct": True, "feedback": "Bien hecho."})

    drills = DrillSystem(language="spanish", engine=FakeTranslationEngine())
    q = _make_question(
        drill_type="translation",
        correct_answer="Voy al mercado",
        context="I go to the market",
    )
    r = drills._check_translation(q, "Voy al mercado")
    assert r.correct is True
    assert "Bien hecho" in r.feedback


# ---------------------------------------------------------------------------
# recommend_drill_type() — falls back to day-of-week schedule
# ---------------------------------------------------------------------------

def test_recommend_drill_type_returns_string(spanish_drills):
    result = spanish_drills.recommend_drill_type()
    assert isinstance(result, str)
    assert result  # non-empty


def test_recommend_drill_type_returns_valid_type(spanish_drills):
    valid = {
        "irregular_verbs_preterite", "irregular_verbs_imperfect",
        "reflexive_verbs", "prepositions", "sentence_dictation",
        "pronunciation", "listening_comprehension", "vocabulary_review",
        "translation", "mixed_review",
    }
    result = spanish_drills.recommend_drill_type()
    assert result in valid


def test_latin_recommend_drill_type_returns_valid_type(latin_drills):
    valid = {
        "irregular_verbs_present", "irregular_verbs_imperfect", "irregular_verbs_perfect",
        "noun_declensions", "prepositions", "sentence_dictation", "pronunciation",
        "listening_comprehension", "vocabulary_review", "translation", "mixed_review",
    }
    result = latin_drills.recommend_drill_type()
    assert result in valid


# ---------------------------------------------------------------------------
# vocabulary_review — degrades gracefully without SessionStore
# ---------------------------------------------------------------------------

def test_vocabulary_review_without_store_returns_fallback(spanish_drills):
    assert spanish_drills.store is None
    q = spanish_drills.get_question("vocabulary_review")
    assert isinstance(q, DrillQuestion)


# ---------------------------------------------------------------------------
# _extract_json_list() helper
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ('{"correct": true}', {"correct": True}),
    ('```json\n[{"a": 1}]\n```', [{"a": 1}]),
    ('Some preamble {"x": 2}', {"x": 2}),
    ('not json at all', []),
])
def test_extract_json_list(raw, expected, spanish_drills):
    result = spanish_drills._extract_json_list(raw)
    assert result == expected
