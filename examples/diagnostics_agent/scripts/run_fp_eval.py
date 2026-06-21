from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import logging
from pathlib import Path
from typing import Sequence

from diagnostics_agent import InterpreterError, LogInterpreter, LogTriage
from diagnostics_agent.eval import CaseScore, aggregate, render_report, score_case
from llm_engines import get_engine


DEFAULT_CORPUS = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "eval"


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.getLogger("diagnostics_agent.interpret").setLevel(logging.ERROR)
    engine_kwargs = {"base_url": args.base_url} if args.base_url else {}
    engine = get_engine(args.backend, args.model, **engine_kwargs)
    interpreter = LogInterpreter(engine, allow_remote=args.allow_remote)
    triage = LogTriage()

    case_scores: list[CaseScore] = []
    errors: dict[str, str] = {}
    for labels_path in sorted(args.corpus.glob("*.labels.json")):
        labels = json.loads(labels_path.read_text(encoding="utf-8"))
        log_path = labels_path.with_name(labels_path.name.removesuffix(".labels.json") + ".log")
        if not log_path.is_file():
            raise FileNotFoundError(f"missing log fixture for {labels_path.name}: {log_path}")

        summary = triage.triage(log_path.read_text(encoding="utf-8"))
        interpretation = None
        try:
            interpretation = interpreter.interpret(summary, system_facts=None)
        except InterpreterError as exc:
            errors[labels["case"]] = str(exc)
        case_scores.append(score_case(interpretation, summary, labels))

    report = aggregate(case_scores)
    print(render_report(report, errors))
    if args.json_path:
        payload = asdict(report)
        payload["errors"] = errors
        args.json_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure diagnostics_agent interpretation false positives and recall."
    )
    parser.add_argument("--backend", default="ollama")
    parser.add_argument("--model", default="qwen3.6:27b")
    parser.add_argument("--base-url")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--json", dest="json_path", type=Path)
    parser.add_argument("--allow-remote", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
