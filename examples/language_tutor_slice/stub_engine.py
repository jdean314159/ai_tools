"""
A stub engine implementing the public ``ChatModel`` protocol.

Lets the slice run and be tested without a live model (no Ollama, no network),
which is how the acceptance test executes in CI / a sandbox. It also documents
exactly what surface a real engine must satisfy — the same surface
``llm_engines.get_engine("ollama", ...)`` provides.

The stub returns a canned response built from the last user message so tests
can assert the wiring end to end.
"""
from __future__ import annotations

from llm_engines import ChatMessage, GenerationRequest, GenerationResponse


class StubTutorEngine:
    """Minimal ChatModel-conforming stub. Deterministic, offline."""

    def __init__(self, model_name: str = "stub-tutor", backend: str = "stub") -> None:
        self.model_name = model_name
        self.backend = backend
        self.calls: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.calls.append(request)
        last_user = ""
        for msg in reversed(request.messages):
            if msg.role == "user" and msg.content:
                last_user = msg.content
                break
        # A canned bilingual reply; enough to verify the turn round-trips.
        reply = "Muy bien. (Very good.) " + (
            "Recuerda usar 'ser' para cosas permanentes."
            if "ser" in last_user.lower()
            else "Sigamos practicando."
        )
        return GenerationResponse(
            message=ChatMessage(role="assistant", content=reply),
            finish_reason="stop",
            model_name=self.model_name,
            backend=self.backend,
        )
