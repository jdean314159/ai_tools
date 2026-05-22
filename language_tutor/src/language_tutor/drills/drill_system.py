"""
Drill System for Language Tutor

Implements vocabulary, conjugation, preposition, dictation, and listening
comprehension drills. Ported and adapted from the standalone spanish_tutor
project; state is managed through Engram ProjectMemory rather than a local
SessionService.

Author: Jeff
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from engram import ProjectMemory
    from llm_engines.contracts.engine import ChatModel as LLMEngine


@dataclass
class DrillQuestion:
    """A single drill question returned to the caller."""
    question_id: str
    drill_type: str
    prompt: str
    correct_answer: str
    context: str = ""
    hint: str = ""
    auto_play_tts: bool = False   # For listening drills
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DrillResult:
    """Result of checking a drill answer."""
    correct: bool
    accuracy: float           # 0.0–1.0
    user_answer: str
    correct_answer: str
    feedback: str
    drill_type: str
    question_id: str


class DrillSystem:
    """
    Manages all drill types for the language tutor.

    Drill types:
      - irregular_verbs_preterite   — conjugate in preterite
      - irregular_verbs_imperfect   — conjugate in imperfect
      - reflexive_verbs             — present tense reflexive
      - prepositions                — verb + preposition patterns
      - sentence_dictation          — type what you hear
      - listening_comprehension     — Duolingo-style sentence recall
      - mixed_review                — random selection

    State (mistake history, mastery) is written to Engram's semantic
    layer via the ProjectMemory helpers/semantic interfaces already
    wired in TutorSession._update_semantic_memory().
    """

    def __init__(
        self,
        language: str,
        memory: Optional["ProjectMemory"] = None,
        engine: Optional["LLMEngine"] = None,
        store=None,   # SessionStore — for spaced-repetition mastery tracking
    ):
        self.language = language.lower()
        self.memory = memory
        self.engine = engine
        self.store = store   # may be None; vocabulary_review degrades gracefully

        # Load content
        if self.language in ("spanish", "es"):
            from language_tutor.content.spanish import get_content
        else:
            # Latin content placeholder — fall back to empty dicts
            try:
                from language_tutor.content.latin import get_content
            except ImportError:
                def get_content():
                    return {
                        "irregular_verbs": {}, "reflexive_verbs": {},
                        "reflexive_conjugations": {}, "preposition_drills": [],
                        "practice_sentences": [], "listening_sentences": [],
                        "conversation_starters": [], "conversation_prompts": [],
                    }

        self.content = get_content()

        # Session-level drill stats
        self._attempts: int = 0
        self._correct: int = 0
        self._mistake_log: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get_question(self, drill_type: str = "mixed_review") -> DrillQuestion:
        """Return a drill question for the given type."""
        # vocabulary_review and translation are available to both languages
        common = {
            "vocabulary_review": self._vocabulary_review,
            "translation":       self._translation,
            "pronunciation":     self._pronunciation,
        }

        if self.language in ("latin", "la"):
            dispatch = {
                "irregular_verbs_present":    lambda: self._irregular_verb("present"),
                "irregular_verbs_imperfect":  lambda: self._irregular_verb("imperfect"),
                "irregular_verbs_perfect":    lambda: self._irregular_verb("perfect"),
                "noun_declensions":           self._noun_declension,
                "prepositions":               self._preposition,
                "sentence_dictation":         self._sentence_dictation,
                "listening_comprehension":    self._listening_comprehension,
                "mixed_review":               self._mixed_review,
                **common,
            }
        else:
            dispatch = {
                "irregular_verbs_preterite":  lambda: self._irregular_verb("preterite"),
                "irregular_verbs_imperfect":  lambda: self._irregular_verb("imperfect"),
                "reflexive_verbs":            self._reflexive_verb,
                "prepositions":               self._preposition,
                "sentence_dictation":         self._sentence_dictation,
                "listening_comprehension":    self._listening_comprehension,
                "mixed_review":               self._mixed_review,
                **common,
            }
        handler = dispatch.get(drill_type, self._mixed_review)
        return handler()

    def check_answer(self, question: DrillQuestion, user_answer: str) -> DrillResult:
        """Check user answer against the correct answer for a drill question."""
        self._attempts += 1

        checker = {
            "irregular_verb":          self._check_exact,
            "reflexive_verb":          self._check_exact,
            "prepositions":            self._check_exact,
            "noun_declension":         self._check_exact,
            "vocabulary_review":       self._check_exact,
            "translation":             self._check_translation,
            "pronunciation":           self._check_pronunciation,
            "sentence_dictation":      self._check_dictation,
            "listening_comprehension": self._check_dictation,
        }.get(question.drill_type, self._check_exact)

        result = checker(question, user_answer)

        if result.correct:
            self._correct += 1
        else:
            self._mistake_log.append({
                "drill_type":     question.drill_type,
                "question_id":    question.question_id,
                "correct_answer": question.correct_answer,
                "user_answer":    user_answer,
            })

        # Update spaced-repetition mastery for vocabulary review drills
        if question.drill_type == "vocabulary_review" and self.store is not None:
            meta = question.metadata or {}
            word = meta.get("word", "")
            translation = meta.get("translation", "")
            if word:
                try:
                    self.store.record_vocab_result(
                        self.language, word, translation, result.correct
                    )
                except Exception:
                    pass

        return result

    def check_dictation(self, expected: str, user_input: str) -> DrillResult:
        """
        Standalone dictation checker (word-level accuracy).
        Ported from spanish_tutor DrillService.check_dictation().
        """
        expected_words = expected.lower().strip().split()
        user_words = user_input.lower().strip().split()

        correct_words = sum(
            1 for i, w in enumerate(user_words)
            if i < len(expected_words) and w == expected_words[i]
        )
        accuracy = correct_words / len(expected_words) if expected_words else 0.0

        if accuracy == 1.0:
            feedback = "¡Perfecto! Every word correct."
        elif accuracy >= 0.8:
            feedback = f"¡Muy bien! {correct_words}/{len(expected_words)} words correct."
        elif accuracy >= 0.5:
            feedback = (
                f"Buen intento. {correct_words}/{len(expected_words)} correct. "
                f"Expected: {expected}"
            )
        else:
            feedback = f"Keep practicing. The sentence was: {expected}"

        return DrillResult(
            correct=accuracy == 1.0,
            accuracy=round(accuracy, 3),
            user_answer=user_input,
            correct_answer=expected,
            feedback=feedback,
            drill_type="dictation",
            question_id="",
        )

    def get_session_accuracy(self) -> float:
        """Return overall accuracy for this drill session (0.0–1.0)."""
        if self._attempts == 0:
            return 0.0
        return round(self._correct / self._attempts, 3)

    def get_session_stats(self) -> Dict[str, Any]:
        return {
            "attempts":  self._attempts,
            "correct":   self._correct,
            "accuracy":  self.get_session_accuracy(),
            "mistakes":  self._mistake_log,
        }

    def recommend_drill_type(self) -> str:
        """
        Recommend a drill type based on recent mistakes.

        If Engram semantic helpers are available, query the Mistake nodes
        to weight toward the student's weakest area. Falls back to a
        day-of-week schedule.
        """
        if self.memory is not None and self.memory.semantic is not None:
            try:
                rows = self.memory.semantic.query(
                    """
                    MATCH (u:User)-[:MADE_MISTAKE]->(m:Mistake)
                    WHERE u.id = 'default'
                    RETURN m.error_type AS error_type, count(m) AS cnt
                    ORDER BY cnt DESC
                    LIMIT 1
                    """
                )
                if rows:
                    error_type = rows[0].get("error_type", "").lower()
                    # Map error_type strings → drill types (both languages)
                    mapping = {
                        "reflexive":   "reflexive_verbs",
                        "preposition": "prepositions",
                        "preterite":   "irregular_verbs_preterite",
                        "imperfect":   "irregular_verbs_imperfect",
                        "present":     "irregular_verbs_present",
                        "perfect":     "irregular_verbs_perfect",
                        "declension":  "noun_declensions",
                        "case":        "noun_declensions",
                        "vocab":       "vocabulary_review",
                        "translation": "translation",
                        "grammar":     "translation",
                        "drill:irreg": "irregular_verbs_preterite",
                        "drill:refl":  "reflexive_verbs",
                        "drill:prep":  "prepositions",
                        "drill:trans": "translation",
                        "drill:noun":  "noun_declensions",
                    }
                    for key, drill_type in mapping.items():
                        if key in error_type:
                            return drill_type
            except Exception:
                pass

        # Day-of-week schedule fallback — language-specific
        from datetime import datetime
        weekday = datetime.now().weekday()
        if self.language in ("latin", "la"):
            schedule = {
                0: "irregular_verbs_present",
                1: "noun_declensions",
                2: "prepositions",
                3: "irregular_verbs_imperfect",
                4: "sentence_dictation",
                5: "pronunciation",
                6: "listening_comprehension",
            }
        else:
            schedule = {
                0: "irregular_verbs_preterite",
                1: "reflexive_verbs",
                2: "prepositions",
                3: "irregular_verbs_imperfect",
                4: "sentence_dictation",
                5: "pronunciation",
                6: "listening_comprehension",
            }
        return schedule[weekday]

    # ------------------------------------------------------------------
    # Question generators
    # ------------------------------------------------------------------

    def _irregular_verb(self, tense: str) -> DrillQuestion:
        verbs = self.content.get("irregular_verbs", {})
        if not verbs:
            return self._fallback_question("irregular_verb")

        verb = random.choice(list(verbs.keys()))

        # Latin uses grammatical person labels; Spanish uses pronoun labels
        if self.language in ("latin", "la"):
            persons = ["1s", "2s", "3s", "1pl", "2pl", "3pl"]
            person_label = {"1s": "ego (1sg)", "2s": "tu (2sg)", "3s": "is/ea (3sg)",
                            "1pl": "nos (1pl)", "2pl": "vos (2pl)", "3pl": "ei (3pl)"}
        else:
            persons = ["yo", "tú", "él", "nosotros", "ellos"]
            person_label = {p: p for p in persons}

        # Pick a person that exists in this verb's tense table
        available = [p for p in persons if p in verbs[verb].get(tense, {})]
        if not available:
            return self._fallback_question("irregular_verb")
        person = random.choice(available)
        correct = verbs[verb][tense][person]
        label = person_label.get(person, person)

        return DrillQuestion(
            question_id=f"irr_{verb}_{tense}_{person}",
            drill_type="irregular_verb",
            prompt=f"Conjugate '{verb}' — {tense}, {label}:",
            correct_answer=correct,
            context=f"Fill in: {label} _____ ({verb}, {tense})",
            hint=f"Think about the {tense} stem of '{verb}'.",
        )

    def _reflexive_verb(self) -> DrillQuestion:
        verbs = self.content.get("reflexive_verbs", {})
        conjs = self.content.get("reflexive_conjugations", {})
        if not verbs:
            return self._fallback_question("reflexive_verb")

        verb = random.choice(list(verbs.keys()))
        meaning = verbs[verb]
        person = random.choice(["yo", "tú", "él"])

        if verb in conjs:
            correct = conjs[verb][person]
        else:
            root = verb[:-4]
            fallback = {"yo": f"me {root}o", "tú": f"te {root}as", "él": f"se {root}a"}
            correct = fallback[person]

        return DrillQuestion(
            question_id=f"refl_{verb}_{person}",
            drill_type="reflexive_verb",
            prompt=f"{person} _____ ({verb} — {meaning}):",
            correct_answer=correct,
            context="Present tense reflexive",
            hint=f"Remember the reflexive pronoun for {person}.",
        )

    def _preposition(self) -> DrillQuestion:
        drills = self.content.get("preposition_drills", [])
        if not drills:
            return self._fallback_question("prepositions")

        drill = random.choice(drills)

        # Latin preposition drills use prep/case/example; Spanish use verb/prep/infinitive
        if self.language in ("latin", "la"):
            return DrillQuestion(
                question_id=f"prep_{drill['prep']}_{drill['case'][:3]}",
                drill_type="prepositions",
                prompt=f"What case does '{drill['prep']}' take when meaning '{drill['meaning']}'?",
                correct_answer=drill["case"],
                context=f"Example: {drill['example']} — {drill['english']}",
                hint=f"'{drill['prep']}' can take different cases with different meanings.",
            )
        return DrillQuestion(
            question_id=f"prep_{drill['verb']}_{drill['prep']}",
            drill_type="prepositions",
            prompt=f"{drill['verb']} ___ {drill['infinitive']}",
            correct_answer=drill["prep"],
            context=f"English: {drill['english']}",
            hint="What preposition connects these verbs?",
        )

    def _sentence_dictation(self) -> DrillQuestion:
        sentences = self.content.get("practice_sentences", [])
        if not sentences:
            return self._fallback_question("sentence_dictation")

        spanish, english = random.choice(sentences)
        return DrillQuestion(
            question_id=f"dict_{abs(hash(spanish)) % 100000}",
            drill_type="sentence_dictation",
            prompt="Type the Spanish sentence:",
            correct_answer=spanish,
            context=f"English: {english}",
            hint="Listen carefully to each word.",
            auto_play_tts=True,
        )

    def _listening_comprehension(self) -> DrillQuestion:
        sentences = self.content.get("listening_sentences", [])
        if not sentences:
            return self._fallback_question("listening_comprehension")

        spanish, english = random.choice(sentences)
        return DrillQuestion(
            question_id=f"listen_{abs(hash(spanish)) % 100000}",
            drill_type="listening_comprehension",
            prompt="Listen and type what you hear:",
            correct_answer=spanish,
            context=f"Hint: {english}",
            hint="Click 🔊 to hear the audio again.",
            auto_play_tts=True,
        )

    def _vocabulary_review(self) -> DrillQuestion:
        """Spaced-repetition vocabulary review — words due for practice."""
        if self.store is None:
            return self._fallback_question("vocabulary_review")

        # Seed any untracked vocab from conversation logs, then get due words
        try:
            self.store.seed_vocab_from_log(self.language)
            due = self.store.get_vocab_due(self.language, limit=20)
        except Exception:
            due = []

        if not due:
            # Nothing due — fall back to a content word
            sentences = self.content.get("practice_sentences", [])
            if sentences:
                spanish, english = random.choice(sentences)
                return DrillQuestion(
                    question_id="vocab_no_due",
                    drill_type="vocabulary_review",
                    prompt="Translate this sentence:",
                    correct_answer=spanish,
                    context=f"English: {english}",
                    hint="No words are due for review right now.",
                )
            return self._fallback_question("vocabulary_review")

        item = random.choice(due)
        word = item["word"]
        translation = item["translation"]
        mastery = item["mastery_level"]
        overdue = item.get("days_overdue", 0)

        level_label = ["new", "learning", "familiar", "practiced", "strong", "mastered"][
            min(mastery, 5)
        ]

        return DrillQuestion(
            question_id=f"vocab_{word[:30].replace(' ', '_')}",
            drill_type="vocabulary_review",
            prompt=f"Translate: \"{translation}\"",
            correct_answer=word,
            context=f"Level: {level_label}" + (f" · {overdue}d overdue" if overdue > 0 else ""),
            hint=f"This is a {level_label}-level word.",
            metadata={"word": word, "translation": translation, "mastery_level": mastery},
        )

    def _translation(self) -> DrillQuestion:
        """Translate English → target language. LLM-graded (accepts paraphrases)."""
        sentences = self.content.get("practice_sentences", [])
        if not sentences:
            return self._fallback_question("translation")

        target, english = random.choice(sentences)
        return DrillQuestion(
            question_id=f"trans_{abs(hash(english)) % 100000}",
            drill_type="translation",
            prompt=f"Translate into {self.language.title()}:",
            correct_answer=target,
            context=english,
            hint="Focus on meaning — minor word-order differences are fine.",
        )

    def _mixed_review(self) -> DrillQuestion:
        if self.language in ("latin", "la"):
            types = [
                "irregular_verbs_present",
                "irregular_verbs_imperfect",
                "noun_declensions",
                "prepositions",
                "sentence_dictation",
                "translation",
                "vocabulary_review",
                "pronunciation",
            ]
        else:
            types = [
                "irregular_verbs_preterite",
                "reflexive_verbs",
                "prepositions",
                "sentence_dictation",
                "translation",
                "vocabulary_review",
                "pronunciation",
            ]
        # Weight vocabulary_review higher if words are due
        if self.store is not None:
            try:
                due = self.store.get_vocab_due(self.language, limit=1)
                if due:
                    types = types + ["vocabulary_review"] * 2  # 3x weight when due
            except Exception:
                pass
        return self.get_question(random.choice(types))

    def _noun_declension(self) -> DrillQuestion:
        """Latin noun declension drill — pick a noun, number, and case."""
        nouns = self.content.get("noun_declensions", {})
        if not nouns:
            return self._fallback_question("noun_declension")

        noun = random.choice(list(nouns.keys()))
        data = nouns[noun]
        number = random.choice(["singular", "plural"])
        case = random.choice(["nominative", "genitive", "dative", "accusative", "ablative"])
        correct = data[number][case]
        meaning = data.get("meaning", "")
        decl = data.get("declension", "")

        return DrillQuestion(
            question_id=f"decl_{noun}_{number}_{case}",
            drill_type="noun_declension",
            prompt=f"Give the {case} {number} of '{noun}' ({meaning}):",
            correct_answer=correct,
            context=f"{decl} declension noun",
            hint=f"Remember the {decl} declension endings.",
        )

    def _fallback_question(self, drill_type: str) -> DrillQuestion:
        if self.language in ("latin", "la"):
            return DrillQuestion(
                question_id="fallback",
                drill_type=drill_type,
                prompt="Translate: 'The girl carries water.'",
                correct_answer="Puella aquam portat.",
                context="Basic Latin sentence",
            )
        return DrillQuestion(
            question_id="fallback",
            drill_type=drill_type,
            prompt="¿Cómo se dice 'I am learning Spanish'?",
            correct_answer="Estoy aprendiendo español",
            context="Basic translation",
        )

    # ------------------------------------------------------------------
    # Answer checkers
    # ------------------------------------------------------------------

    def _pronunciation(self) -> DrillQuestion:
        """Pronunciation drill — say a sentence aloud.

        Returns a question with auto_play_tts=True so the frontend plays
        the sentence first, then records the user's attempt via the mic.
        The answer field is the user's audio (handled by /audio route);
        for text-only sessions it falls back to dictation.
        """
        sentences = self.content.get("practice_sentences", [])
        if not sentences:
            return self._fallback_question("pronunciation")
        target, english = random.choice(sentences)
        return DrillQuestion(
            question_id=f"pron_{abs(hash(target)) % 100000}",
            drill_type="pronunciation",
            prompt="Listen, then repeat aloud:",
            correct_answer=target,
            context=f"English: {english}",
            hint="Focus on natural rhythm and clear vowels.",
            auto_play_tts=True,
        )

    def _check_pronunciation(self, question: DrillQuestion, user_answer: str) -> DrillResult:
        """Text-mode pronunciation check (dictation fallback).

        In voice mode the /audio route scores pronunciation directly via
        PronunciationScorer. Here we receive the Whisper transcription as
        user_answer and score it against expected text.
        """
        return self._check_dictation(question, user_answer)

    def _extract_json_list(self, raw: str):
        """Extract a JSON array or object from an LLM response string."""
        import json, re
        raw = raw.strip()
        raw = re.sub(r'^```[a-z]*\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'```\s*$', '', raw, flags=re.MULTILINE).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        m = re.search(r'[\[{].*[\]}]', raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        return []

    def _check_exact(self, question: DrillQuestion, user_answer: str) -> DrillResult:
        """Case-insensitive exact match, accent-tolerant."""
        expected = question.correct_answer.lower().strip()
        given = user_answer.lower().strip()

        # Allow accent-free responses (common for keyboard without accents)
        def strip_accents(s: str) -> str:
            replacements = {
                "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
                "ü": "u", "ñ": "n",
            }
            return "".join(replacements.get(c, c) for c in s)

        correct = (given == expected) or (strip_accents(given) == strip_accents(expected))
        accuracy = 1.0 if correct else 0.0

        if correct:
            feedback = random.choice([
                "¡Correcto!", "¡Exacto!", "¡Muy bien!", "¡Perfecto!",
            ])
        else:
            feedback = f"Not quite. The answer is: {question.correct_answer}"

        return DrillResult(
            correct=correct,
            accuracy=accuracy,
            user_answer=user_answer,
            correct_answer=question.correct_answer,
            feedback=feedback,
            drill_type=question.drill_type,
            question_id=question.question_id,
        )

    def _check_dictation(self, question: DrillQuestion, user_answer: str) -> DrillResult:
        """Word-level accuracy for dictation/listening drills."""
        return self.check_dictation(question.correct_answer, user_answer)

    def _check_translation(self, question: DrillQuestion, user_answer: str) -> DrillResult:
        """LLM-graded translation check — accepts semantically equivalent answers.

        Falls back to exact/dictation matching if no engine is available.
        """
        if not user_answer.strip():
            return DrillResult(
                correct=False, accuracy=0.0,
                user_answer=user_answer,
                correct_answer=question.correct_answer,
                feedback="Please enter a translation.",
                drill_type=question.drill_type,
                question_id=question.question_id,
            )

        if self.engine is None:
            # No LLM — fall back to fuzzy dictation check
            return self._check_dictation(question, user_answer)

        english = question.context     # English phrase
        reference = question.correct_answer

        grading_prompt = (
            f"Grade this translation exercise.\n\n"
            f"English: {english}\n"
            f"Reference {self.language} translation: {reference}\n"
            f"Student answer: {user_answer}\n\n"
            f"Is the student's answer an acceptable translation? "
            f"Minor differences in word choice, word order, or accent marks are fine "
            f"if the meaning is correct. Do NOT penalise for missing accents.\n\n"
            f"Respond with JSON only — no other text:\n"
            f'{{\"correct\": true/false, \"feedback\": \"one short sentence\"}}'
        )

        try:
            raw = self.engine.generate(
                grading_prompt,
                system_prompt="You are a language teacher grading translations. Respond only with JSON.",
                max_tokens=120,
            )
            parsed = self._extract_json_list(raw)
            # _extract_json_list returns a list; grader returns an object
            if isinstance(parsed, list) and parsed:
                parsed = parsed[0]
            if not isinstance(parsed, dict):
                # Try direct object parse
                import json, re
                m = re.search(r'\{[^}]+\}', raw, re.DOTALL)
                parsed = json.loads(m.group()) if m else {}

            correct = bool(parsed.get("correct", False))
            feedback = parsed.get("feedback", "")
            if not feedback:
                feedback = "¡Correcto!" if correct else f"Reference: {reference}"

        except Exception:
            # LLM grading failed — use fuzzy fallback
            return self._check_dictation(question, user_answer)

        accuracy = 1.0 if correct else 0.0
        return DrillResult(
            correct=correct,
            accuracy=accuracy,
            user_answer=user_answer,
            correct_answer=reference,
            feedback=feedback,
            drill_type=question.drill_type,
            question_id=question.question_id,
        )
