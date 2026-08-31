from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from engram import ProjectMemory
from llm_engines import ChatMessage, ChatModel, GenerationRequest, StructuredOutputHandler
from llm_harness_core import (
    CapabilityDescriptor,
    CapabilityKind,
    MemoryRecord,
    OperationResult,
    TraceEvent,
)

from .drills import DrillQuestion, DrillSystem
from .profiles import get_profile
from .store import TutorStore


# --- Structured-output schemas -------------------------------------------------
# Parsed from model output via the public llm_engines.StructuredOutputHandler,
# replacing hand-rolled JSON regex parsing. Each schema also drives its own
# prompt instructions via StructuredOutputHandler.create_schema_prompt().


class LessonPlan(BaseModel):
    warmup_topic: str = ""
    focus_areas: list[str] = Field(default_factory=list)
    drill_type: str = "mixed_review"
    new_content: list[str] = Field(default_factory=list)
    estimated_minutes: dict[str, int] = Field(default_factory=dict)


class Correction(BaseModel):
    error: str = ""
    correction: str = ""
    explanation: str = ""


class VocabItem(BaseModel):
    word: str = ""
    translation: str = ""
    part_of_speech: str = ""


class TurnAnalysis(BaseModel):
    """Merged per-turn extraction: corrections + new vocabulary in one call."""

    corrections: list[Correction] = Field(default_factory=list)
    new_vocabulary: list[VocabItem] = Field(default_factory=list)


class WordLookup(BaseModel):
    translation: str = ""
    alternatives: list[str] = Field(default_factory=list)
    part_of_speech: str = ""
    notes: str = ""
    example: str = ""


class TextError(BaseModel):
    start: int = 0
    end: int = 0
    error: str = ""
    suggestion: str = ""
    type: str = ""
    hint: str = ""


class TextCheck(BaseModel):
    errors: list[TextError] = Field(default_factory=list)


@dataclass
class TutorResponse:
    text: str
    corrections: list[dict[str, Any]] = field(default_factory=list)
    new_vocabulary: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class LanguageTutor:
    """Language tutor rebuilt as a public ai_tools API consumer."""

    def __init__(
        self,
        *,
        language: str,
        engine: ChatModel,
        planner: ChatModel | None = None,
        base_dir: str | Path = ".language_tutor_example",
        session_id: str | None = None,
        analyze: bool = True,
    ) -> None:
        self.profile = get_profile(language)
        self.language = self.profile.code
        self.engine = engine
        self.planner = planner or engine
        self.analyze = analyze
        self.base_dir = Path(base_dir)
        self.session_id = session_id or f"session_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S_%f')}"
        self.memory = ProjectMemory(
            base_dir=self.base_dir / "memory",
            project_id=f"{self.language}_tutor_example",
            session_id=self.session_id,
            system_prompt=self.profile.system_prompt,
        )
        self.store = TutorStore(self.base_dir / "sessions.sqlite")
        self.store.start_session(self.session_id, self.language)
        self.drills = DrillSystem(self.language, self.store)
        self.plan: dict[str, Any] = {}
        self.state = "idle"
        self.exchange_count = 0
        self.corrections_count = 0
        self.vocabulary: list[dict[str, Any]] = []
        self.active_drill: DrillQuestion | None = None
        self.events: list[TraceEvent] = []

    def start_session(self, duration_minutes: int = 30) -> dict[str, Any]:
        history = self.store.history(self.language, limit=3)
        instruction = (
            f"Plan a {duration_minutes}-minute {self.profile.name} tutoring lesson.\n"
            f"Starter: {self.profile.starter()}\n"
            f"Prior sessions: {json.dumps(history)}"
        )
        plan = self._generate_structured(self.planner, instruction, LessonPlan, max_tokens=500)
        parsed = (
            plan.model_dump()
            if plan
            else {
                "warmup_topic": self.profile.starter(),
                "focus_areas": ["conversation", "useful vocabulary"],
                "drill_type": "mixed_review",
                "new_content": [],
                "estimated_minutes": {"conversation": duration_minutes},
            }
        )
        self.plan = parsed
        self.state = "warmup"
        self._event(
            "language_tutor.session.started", {"duration_minutes": duration_minutes, "plan": parsed}
        )
        return {
            "session_id": self.session_id,
            "language": self.language,
            "plan": parsed,
            "greeting": self.profile.greeting,
        }

    def send_message(self, message: str) -> TutorResponse:
        self.exchange_count += 1
        self.state = "conversation"
        self.memory.add_turn("user", message, self.session_id)
        prompt_result = self.memory.build_prompt(message)
        focus = self.plan.get("focus_areas") if isinstance(self.plan, dict) else None
        focus_prefix = f"Session focus: {', '.join(focus)}\n\n" if focus else ""
        response_text = self._generate(
            self.engine, focus_prefix + prompt_result["prompt"], max_tokens=900
        )
        self.memory.add_turn("assistant", response_text, self.session_id)
        try:
            self.memory.index_text(f"User: {message}\nAssistant: {response_text}")
        except Exception:
            pass
        # One merged analysis call (corrections + vocabulary) instead of two,
        # and skipped entirely when analyze=False for a 1-call low-latency turn.
        corrections, vocab = self._analyze_turn(message, response_text)
        self.corrections_count += len(corrections)
        self.vocabulary.extend(vocab)
        for correction in corrections:
            self.store.log_mistake(
                self.session_id,
                self.language,
                correction.get("error", ""),
                correction.get("correction", ""),
                correction.get("explanation", "grammar"),
            )
        for item in vocab:
            self.store.add_vocab(self.language, item.get("word", ""), item.get("translation", ""))
        result = TutorResponse(
            text=response_text,
            corrections=corrections,
            new_vocabulary=vocab,
            metadata={
                "prompt_tokens": prompt_result.get("prompt_tokens", 0),
                "memory_tokens": prompt_result.get("memory_tokens", 0),
                "compressed": prompt_result.get("compressed", False),
                "state": self.state,
            },
        )
        self._event(
            "language_tutor.turn.completed",
            {
                "message": message,
                "response": response_text,
                "corrections": len(corrections),
                "vocabulary": len(vocab),
            },
        )
        return result

    def explain(self, text: str, question: str | None = None) -> str:
        prompt = (
            f"A student learning {self.profile.name} has a grammar question.\n"
            f"Text: {text}\nQuestion: {question or 'Explain the grammar.'}\n"
            "Give a concise explanation with a corrected example if relevant."
        )
        explanation = self._generate(self.planner, prompt, max_tokens=400)
        self._event("language_tutor.explanation.completed", {"text": text, "question": question})
        return explanation

    def lookup(self, word: str, context: str | None = None) -> dict[str, Any]:
        instruction = (
            f"A student is learning {self.profile.name}. Word/phrase: {word}\n"
            f"Context: {context or ''}"
        )
        parsed = self._generate_structured(self.engine, instruction, WordLookup, max_tokens=250)
        result = (
            parsed.model_dump() if parsed else {"translation": "", "alternatives": [], "notes": ""}
        )
        if result.get("translation"):
            self.store.add_vocab(self.language, word, str(result["translation"]))
        return {"word": word, **result}

    def check_text(self, text: str) -> dict[str, Any]:
        instruction = f"Check this {self.profile.name} text for errors.\nText: {text}"
        parsed = self._generate_structured(self.engine, instruction, TextCheck, max_tokens=300)
        errors = [error.model_dump() for error in parsed.errors] if parsed else []
        return {"text": text, "errors": errors}

    def import_vocabulary(self, text: str) -> dict[str, Any]:
        pairs: list[tuple[str, str]] = []
        for block in re.split(r"\n\s*\n", text.strip()):
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            if len(lines) >= 2:
                pairs.append((lines[0], lines[1]))
        seen: set[str] = set()
        imported: list[dict[str, Any]] = []
        for word, translation in pairs:
            key = word.lower()
            if key in seen:
                continue
            seen.add(key)
            self.store.add_vocab(self.language, word, translation)
            imported.append({"word": word, "translation": translation})
        return {"imported": len(imported), "skipped": len(pairs) - len(imported), "words": imported}

    def get_drill(self, drill_type: str = "auto") -> dict[str, Any]:
        self.active_drill = self.drills.question(drill_type)
        self.state = "drill"
        return asdict(self.active_drill)

    def check_drill(self, answer: str) -> dict[str, Any]:
        if self.active_drill is None:
            return {"error": "No active drill question. Call get_drill first.", "correct": False}
        result = self.drills.check(self.active_drill, answer)
        if not result.correct:
            self.store.log_mistake(
                self.session_id,
                self.language,
                answer,
                result.correct_answer,
                f"drill:{result.drill_type}",
            )
        self.active_drill = None
        self.state = "conversation"
        return {**asdict(result), "drill_stats": self.drills.stats()}

    def drill_types(self) -> dict[str, Any]:
        return {"language": self.language, "types": self.drills.types()}

    def handle_audio_transcript(self, transcript: str) -> dict[str, Any]:
        response = self.send_message(transcript)
        return {
            "session_id": self.session_id,
            "transcription": transcript,
            "message": response.text,
            "audio_response": None,
            "metadata": response.metadata,
        }

    def score_pronunciation(self, expected_text: str, detected_text: str) -> dict[str, Any]:
        score = int(self.drills._similarity(expected_text, detected_text) * 100)
        if score < 60:
            self.store.log_mistake(
                self.session_id, self.language, detected_text, expected_text, "pronunciation"
            )
        return {
            "score": score,
            "detected_text": detected_text,
            "expected_text": expected_text,
            "feedback": "Clear pronunciation."
            if score >= 80
            else "Slow down and repeat the target sentence.",
        }

    def end_session(self) -> dict[str, Any]:
        turns = self.memory.get_recent_turns(self.session_id, limit=100)
        prompt = f"Summarize this {self.profile.name} session.\nTurns: {json.dumps(turns)}"
        summary = self._generate(self.planner, prompt, max_tokens=500)
        try:
            self.memory.store_episode(
                summary,
                metadata={
                    "type": "session_summary",
                    "session_id": self.session_id,
                    "language": self.language,
                },
                importance=0.95,
                bypass_filter=True,
            )
        except Exception:
            pass
        accuracy = self.drills.stats()["accuracy"]
        self.store.complete_session(
            self.session_id,
            exchanges=self.exchange_count,
            corrections=self.corrections_count,
            vocab_count=len(self.vocabulary),
            drill_accuracy=accuracy,
            summary=summary,
        )
        self.state = "completed"
        self._event("language_tutor.session.completed", {"summary": summary})
        return {"session_id": self.session_id, "summary": summary, "statistics": self.metrics()}

    def history(self, limit: int = 10) -> dict[str, Any]:
        return {"language": self.language, "sessions": self.store.history(self.language, limit)}

    def stats(self) -> dict[str, Any]:
        return {"language": self.language, "stats": self.store.stats(self.language)}

    def metrics(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "language": self.language,
            "exchanges": self.exchange_count,
            "corrections_made": self.corrections_count,
            "vocab_learned": len(self.vocabulary),
            "drill_accuracy": self.drills.stats()["accuracy"],
        }

    def memory_snapshot(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turns": self.memory.get_recent_turns(self.session_id, limit=50),
            "episodes": [
                self._plain(item)
                for item in self.memory.search_episodes("session", n=5, min_relevance=0.0)
            ],
            "memory_stats": self.memory.get_stats(),
        }

    def capability_descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            kind=CapabilityKind.OTHER,
            provider="examples.language_tutor",
            component="LanguageTutor",
            summary="Language tutor example built only on public ai_tools APIs.",
            features=(
                "conversation",
                "memory_augmented_prompting",
                "session_planning",
                "drills",
                "spaced_repetition",
                "lookup",
                "grammar_check",
                "voice_transcript_flow",
                "pronunciation_scoring",
                "session_history",
            ),
            input_types=("user_message", "language_profile", "drill_answer"),
            output_types=("tutor_response", "session_plan", "trace_events", "memory_records"),
            metadata={"language": self.language, "session_id": self.session_id},
        )

    def interop_result(self, value: dict[str, Any]) -> OperationResult[dict[str, Any]]:
        return OperationResult.success(
            value,
            diagnostics={
                "capability": self.capability_descriptor(),
                "trace_events": tuple(self.events),
                "memory_records": self.memory_records(),
            },
        )

    def memory_records(self) -> tuple[MemoryRecord, ...]:
        records = []
        for idx, turn in enumerate(self.memory.get_recent_turns(self.session_id, limit=20)):
            records.append(
                MemoryRecord(
                    text=str(turn.get("text", "")),
                    source="examples.language_tutor.working_memory",
                    metadata={
                        "role": turn.get("role"),
                        "turn_index": idx,
                        "session_id": self.session_id,
                    },
                )
            )
        return tuple(records)

    def close(self) -> None:
        self.memory.close()

    def _generate(self, engine: ChatModel, prompt: str, *, max_tokens: int) -> str:
        response = engine.generate(
            GenerationRequest(
                messages=[ChatMessage(role="user", content=prompt)],
                max_tokens=max_tokens,
                temperature=0.4,
            )
        )
        return response.text

    def _generate_structured(
        self, engine: ChatModel, instruction: str, model_class: type[BaseModel], *, max_tokens: int
    ):
        """
        Generate and parse a structured response via the public
        StructuredOutputHandler. The schema prompt is derived from the model,
        and parsing is non-raising (a malformed turn returns None, never crashes).
        """
        schema_prompt = StructuredOutputHandler.create_schema_prompt(model_class)
        raw = self._generate(engine, f"{instruction}\n\n{schema_prompt}", max_tokens=max_tokens)
        result = StructuredOutputHandler.parse_with_details(raw, model_class)
        return result.data if result.success else None

    def _analyze_turn(
        self, user_message: str, response_text: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        One merged extraction call: corrections + new vocabulary together.
        Returns ([], []) when analysis is disabled or parsing fails, so a turn
        never depends on it succeeding.
        """
        if not self.analyze:
            return [], []
        instruction = (
            f"Analyze this {self.profile.name} exchange.\n"
            f"User said: {user_message}\nTutor responded: {response_text}\n"
            "List explicit corrections made and any new vocabulary the tutor introduced."
        )
        analysis = self._generate_structured(self.engine, instruction, TurnAnalysis, max_tokens=400)
        if analysis is None:
            return [], []
        corrections = [c.model_dump() for c in analysis.corrections]
        vocab = [v.model_dump() for v in analysis.new_vocabulary]
        return corrections, vocab

    def _event(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.append(
            TraceEvent(
                event_type=event_type,
                source_package="examples.language_tutor",
                source_component="LanguageTutor",
                payload={
                    "session_id": self.session_id,
                    "language": self.language,
                    "state": self.state,
                    **payload,
                },
                tags=("language_tutor",),
            )
        )

    @classmethod
    def _plain(cls, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(k): cls._plain(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._plain(v) for v in value]
        if is_dataclass(value):
            return cls._plain(asdict(value))
        if hasattr(value, "__dict__"):
            return {k: cls._plain(v) for k, v in vars(value).items() if not k.startswith("_")}
        return str(value)
