from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from random import choice
from typing import Any

from .profiles import get_content, get_profile
from .store import TutorStore


@dataclass(frozen=True)
class DrillQuestion:
    question_id: str
    drill_type: str
    prompt: str
    correct_answer: str
    context: str = ""
    hint: str = ""
    auto_play_tts: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DrillResult:
    correct: bool
    accuracy: float
    user_answer: str
    correct_answer: str
    feedback: str
    drill_type: str
    question_id: str


class DrillSystem:
    def __init__(self, language: str, store: TutorStore) -> None:
        self.profile = get_profile(language)
        self.content = get_content(language)
        self.store = store
        self.attempts = 0
        self.correct = 0
        self.mistakes: list[dict[str, Any]] = []

    def types(self) -> list[dict[str, str]]:
        if self.profile.code == "la":
            ids = [
                "auto",
                "mixed_review",
                "vocabulary_review",
                "translation",
                "pronunciation",
                "irregular_verbs_present",
                "noun_declensions",
                "prepositions",
                "sentence_dictation",
                "listening_comprehension",
            ]
        else:
            ids = [
                "auto",
                "mixed_review",
                "vocabulary_review",
                "translation",
                "pronunciation",
                "irregular_verbs_preterite",
                "irregular_verbs_imperfect",
                "reflexive_verbs",
                "prepositions",
                "sentence_dictation",
                "listening_comprehension",
            ]
        return [{"id": item, "label": item.replace("_", " ").title()} for item in ids]

    def recommend_type(self) -> str:
        stats = self.store.stats(self.profile.code)
        weaknesses = stats.get("weaknesses") or []
        if weaknesses:
            error_type = str(weaknesses[0].get("error_type", "")).lower()
            if "prep" in error_type:
                return "prepositions"
            if "vocab" in error_type:
                return "vocabulary_review"
            if "pronunciation" in error_type:
                return "pronunciation"
        return "mixed_review"

    def question(self, drill_type: str = "auto") -> DrillQuestion:
        drill_type = self.recommend_type() if drill_type in {"", "auto"} else drill_type
        if drill_type == "mixed_review":
            drill_type = choice(
                ["vocabulary_review", "translation", "prepositions", "sentence_dictation"]
            )
        if drill_type == "vocabulary_review":
            return self._vocabulary()
        if drill_type == "translation":
            return self._translation()
        if drill_type == "prepositions":
            return self._preposition()
        if drill_type in {"sentence_dictation", "listening_comprehension", "pronunciation"}:
            return self._listening(drill_type)
        return self._verb(drill_type)

    def check(self, question: DrillQuestion, answer: str) -> DrillResult:
        self.attempts += 1
        accuracy = self._similarity(question.correct_answer, answer)
        correct = accuracy >= (
            0.8
            if question.drill_type
            in {"translation", "pronunciation", "sentence_dictation", "listening_comprehension"}
            else 0.98
        )
        if correct:
            self.correct += 1
            feedback = "Correct."
        else:
            feedback = f"Review this answer: {question.correct_answer}"
            self.mistakes.append(
                {
                    "drill_type": question.drill_type,
                    "answer": answer,
                    "correct_answer": question.correct_answer,
                }
            )
        if question.drill_type == "vocabulary_review":
            self.store.record_vocab_result(
                self.profile.code,
                question.metadata.get("word", question.correct_answer),
                question.metadata.get("translation", question.context),
                correct,
            )
        return DrillResult(
            correct,
            accuracy,
            answer,
            question.correct_answer,
            feedback,
            question.drill_type,
            question.question_id,
        )

    def stats(self) -> dict[str, Any]:
        return {
            "attempts": self.attempts,
            "correct": self.correct,
            "accuracy": round(self.correct / self.attempts, 3) if self.attempts else 0.0,
            "mistakes": self.mistakes,
        }

    def _vocabulary(self) -> DrillQuestion:
        due = self.store.due_vocab(self.profile.code, limit=10)
        if due:
            item = choice(due)
            return DrillQuestion(
                f"vocab_{item['word']}",
                "vocabulary_review",
                f"Translate: {item['translation']}",
                item["word"],
                metadata={"word": item["word"], "translation": item["translation"]},
            )
        word, translation = choice(list(self.content["vocabulary"].items()))
        return DrillQuestion(
            f"vocab_{word}",
            "vocabulary_review",
            f"Translate: {translation}",
            word,
            metadata={"word": word, "translation": translation},
        )

    def _translation(self) -> DrillQuestion:
        target, english = choice(self.content["sentences"])
        return DrillQuestion(
            f"trans_{abs(hash(english))}",
            "translation",
            f"Translate into {self.profile.name}:",
            target,
            context=english,
        )

    def _preposition(self) -> DrillQuestion:
        item = choice(self.content["prepositions"])
        if self.profile.code == "la":
            prep, case, meaning = item
            return DrillQuestion(
                f"prep_{prep}",
                "prepositions",
                f"What case does '{prep}' take for '{meaning}'?",
                case,
            )
        verb, prep, meaning = item
        return DrillQuestion(f"prep_{verb}", "prepositions", f"{verb} ___", prep, context=meaning)

    def _listening(self, drill_type: str) -> DrillQuestion:
        target, english = choice(self.content["sentences"])
        prompt = (
            "Repeat aloud:" if drill_type == "pronunciation" else "Listen and type what you hear:"
        )
        return DrillQuestion(
            f"{drill_type}_{abs(hash(target))}",
            drill_type,
            prompt,
            target,
            context=english,
            auto_play_tts=True,
        )

    def _verb(self, drill_type: str) -> DrillQuestion:
        verb, forms = choice(list(self.content["verbs"].items()))
        person, answer = choice(list(forms.items()))
        return DrillQuestion(
            f"verb_{verb}_{person}", "irregular_verb", f"Conjugate '{verb}' for {person}:", answer
        )

    @staticmethod
    def _similarity(expected: str, answer: str) -> float:
        a = expected.lower().strip()
        b = answer.lower().strip()
        if not a:
            return 0.0
        if a == b:
            return 1.0
        return round(SequenceMatcher(None, a, b).ratio(), 3)
