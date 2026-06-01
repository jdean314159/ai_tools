from __future__ import annotations

import json

from llm_engines import ChatMessage, GenerationRequest, GenerationResponse


class StubTutorEngine:
    """Deterministic public ChatModel-compatible engine for offline runs."""

    def __init__(self, model_name: str = "language-tutor-stub", backend: str = "stub") -> None:
        self.model_name = model_name
        self.backend = backend
        self.calls: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.calls.append(request)
        prompt = request.messages[-1].content if request.messages else ""
        text = self._reply(prompt or "")
        return GenerationResponse(
            message=ChatMessage(role="assistant", content=text),
            finish_reason="stop",
            model_name=self.model_name,
            backend=self.backend,
        )

    def _reply(self, prompt: str) -> str:
        lower = prompt.lower()
        # Match on instruction phrases that appear before the schema block,
        # not on schema field names (which are present in every structured call).
        if "tutoring lesson" in lower:
            return json.dumps(
                {
                    "warmup_topic": "daily routine",
                    "focus_areas": ["verb agreement", "useful travel vocabulary"],
                    "drill_type": "mixed_review",
                    "new_content": ["aprender", "viajar"],
                    "estimated_minutes": {"warmup": 5, "conversation": 15, "drill": 10},
                }
            )
        if "analyze this" in lower and "exchange" in lower:
            corrections = (
                [{"error": "yo es", "correction": "yo soy", "explanation": "Use soy with yo."}]
                if "yo es" in lower
                else []
            )
            return json.dumps(
                {
                    "corrections": corrections,
                    "new_vocabulary": [
                        {"word": "aprender", "translation": "to learn", "part_of_speech": "verb"}
                    ],
                }
            )
        if "word/phrase:" in lower:
            return json.dumps(
                {
                    "translation": "to learn",
                    "alternatives": ["to study"],
                    "part_of_speech": "verb",
                    "notes": "Common regular -er verb.",
                    "example": "Quiero aprender espanol.",
                }
            )
        if "text for errors" in lower:
            errors = (
                [{"start": 0, "end": 5, "error": "yo es", "suggestion": "yo soy", "type": "conjugation", "hint": "Use soy with yo."}]
                if "yo es" in lower
                else []
            )
            return json.dumps({"errors": errors})
        if "summarize this" in lower:
            return "Practiced conversation, corrections, vocabulary, and drills. Review verb agreement next time."
        if "grammar question" in lower:
            return "Use 'soy' with 'yo' because ser is conjugated by subject. 'Yo soy estudiante' is correct."
        return "Muy bien. Yo diria: 'yo soy estudiante'. Sigamos practicando la conversacion."
