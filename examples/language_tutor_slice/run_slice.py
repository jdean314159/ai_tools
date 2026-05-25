"""
Run the tutor slice.

Real (your machine, Ollama running):
    python -m language_tutor_slice.run_slice --model qwen3:8b

Offline (no model; uses the stub — what CI/sandbox runs):
    python -m language_tutor_slice.run_slice --stub

The only difference between the two is which ChatModel is constructed. The
turn logic in tutor_turn.run_turn is identical, which is the point: the engine
is injected through the public ``ChatModel`` protocol.
"""
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from engram import ProjectMemory

from .stub_engine import StubTutorEngine
from .tutor_turn import run_turn
from .vocab import SYSTEM_PROMPT, vocab_seed_text


def build_engine(args: argparse.Namespace):
    if args.stub:
        return StubTutorEngine()
    # Real path: public llm_engines entry point.
    from llm_engines import get_engine

    return get_engine(args.backend, args.model)


def main() -> None:
    parser = argparse.ArgumentParser(description="Language tutor acceptance slice")
    parser.add_argument("--stub", action="store_true", help="use the offline stub engine")
    parser.add_argument("--backend", default="ollama")
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--base-dir", default=None, help="memory dir (default: temp)")
    args = parser.parse_args()

    base_dir = Path(args.base_dir) if args.base_dir else Path(tempfile.mkdtemp(prefix="tutor_slice_"))
    session_id = "slice-session"

    # Public engram entry point. embedder=None -> lexical retrieval, no model needed.
    memory = ProjectMemory(
        base_dir=base_dir,
        project_id="spanish_tutor_slice",
        session_id=session_id,
        system_prompt=SYSTEM_PROMPT,
    )
    memory.new_session(session_id)

    # Seed a little vocabulary so memory has something to retrieve.
    memory.index_text(vocab_seed_text())

    engine = build_engine(args)

    print(f"Engine: {engine.backend}/{engine.model_name}   Memory: {base_dir}\n")

    for user_input in [
        "Hola, ¿cómo se dice 'I am a student'?",
        "¿Cuándo uso 'ser' y cuándo 'estar'?",
    ]:
        result = run_turn(
            memory=memory,
            engine=engine,
            session_id=session_id,
            user_input=user_input,
        )
        print(f"You:   {result.user_input}")
        print(f"Tutor: {result.response_text}")
        print(
            f"       [prompt_tokens={result.prompt_tokens} "
            f"memory_tokens={result.memory_tokens} compressed={result.compressed}]\n"
        )

    print("Stats:", memory.get_stats())
    memory.close()


if __name__ == "__main__":
    main()
