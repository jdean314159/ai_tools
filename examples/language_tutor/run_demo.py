from __future__ import annotations

import argparse
from pathlib import Path

from ._bootstrap import install_repo_source_paths

install_repo_source_paths()

from llm_engines import get_engine  # noqa: E402

from .session import LanguageTutor  # noqa: E402
from .stub_engine import StubTutorEngine  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the public-API language tutor example.")
    parser.add_argument("--language", default="spanish", choices=["spanish", "latin", "es", "la"])
    parser.add_argument("--base-dir", default=".language_tutor_example")
    parser.add_argument("--backend", default="stub")
    parser.add_argument("--model", default="qwen3:8b")
    args = parser.parse_args()

    engine = StubTutorEngine() if args.backend == "stub" else get_engine(args.backend, args.model)
    tutor = LanguageTutor(language=args.language, engine=engine, base_dir=Path(args.base_dir))
    try:
        print(tutor.start_session())
        print(tutor.send_message("yo es estudiante").text)
        drill = tutor.get_drill("translation")
        print(drill)
        print(tutor.check_drill(drill["correct_answer"]))
        print(tutor.end_session())
    finally:
        tutor.close()


if __name__ == "__main__":
    main()
