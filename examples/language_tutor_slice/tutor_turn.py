"""
Tutor turn — the acceptance-test slice.

One memory-augmented tutoring turn, built against ONLY the public APIs of
``engram`` and ``llm_engines``. Every import below is from a package's public
surface (its ``__all__``); nothing reaches into a private module. If this file
can be written and run using only those symbols, the public API passes the
acceptance test for this slice.

Public symbols used:
    engram:      ProjectMemory
    llm_engines: ChatMessage, GenerationRequest, GenerationResponse, ChatModel

The turn flow is harvested from ``language_tutor/tutor_session.handle_text``,
rewritten against the public API (the original called a wrapped
``executor.generate(prompt=, system_prompt=, max_tokens=)`` convenience and a
``memory_backend`` adapter; here we use the public types directly).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from engram import ProjectMemory
from llm_engines import ChatMessage, ChatModel, GenerationRequest


@dataclass
class TurnResult:
    """Everything a caller needs to render and inspect one turn."""
    user_input: str
    response_text: str
    prompt: str
    prompt_tokens: int
    memory_tokens: int
    compressed: bool
    backend: str
    model_name: str
    metadata: dict[str, Any] = field(default_factory=dict)


def run_turn(
    *,
    memory: ProjectMemory,
    engine: ChatModel,
    session_id: str,
    user_input: str,
    max_tokens: int = 300,
    temperature: float = 0.5,
) -> TurnResult:
    """
    Execute one tutoring turn:

      1. record the user turn in memory
      2. build a memory-augmented prompt (engram does retrieval + budgeting)
      3. call the engine with that prompt
      4. record the assistant turn
      5. index the exchange for future retrieval

    Uses only public engram + llm_engines symbols.
    """
    # 1. Record the user's turn. (Public: ProjectMemory.add_turn)
    memory.add_turn("user", user_input, session_id)

    # 2. Memory-augmented prompt. engram assembles working/episodic/semantic
    #    context with token budgeting; the system prompt is already folded in
    #    via ProjectMemory(system_prompt=...). (Public: ProjectMemory.build_prompt)
    prompt_result = memory.build_prompt(user_input)
    prompt = prompt_result["prompt"]

    # 3. Engine call. The assembled prompt already contains the system prompt,
    #    so we send it as a single user message rather than re-applying a system
    #    role (avoids double-applying the persona).
    #    (Public: GenerationRequest, ChatMessage, ChatModel.generate)
    request = GenerationRequest(
        messages=[ChatMessage(role="user", content=prompt)],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    response = engine.generate(request)
    response_text = response.text  # convenience accessor (added during this slice)

    # 4. Record the assistant turn. (Public: ProjectMemory.add_turn)
    memory.add_turn("assistant", response_text, session_id)

    # 5. Index the exchange for future retrieval. (Public: ProjectMemory.index_text)
    #    Best-effort, exactly as the original tutor treated it.
    try:
        memory.index_text(f"User: {user_input}\nAssistant: {response_text}")
    except Exception:
        pass

    return TurnResult(
        user_input=user_input,
        response_text=response_text,
        prompt=prompt,
        prompt_tokens=int(prompt_result.get("prompt_tokens", 0)),
        memory_tokens=int(prompt_result.get("memory_tokens", 0)),
        compressed=bool(prompt_result.get("compressed", False)),
        backend=response.backend,
        model_name=response.model_name,
    )
