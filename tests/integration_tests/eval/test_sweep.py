from pathlib import Path

import pytest

from integration_tests.eval.sweep import _run_args, main


def test_run_args_include_current_eval_controls():
    args = _run_args(
        backend="neural_on",
        run_name="candidate",
        output_root=Path("runs"),
        trials=["baseline"],
        limit=3,
        model="judge-model",
        ollama_url="http://localhost:11434",
        embed_model="embed-model",
        affinity_weight=0.2,
        judge_cache=Path("judge-cache.json"),
        mode="generation",
        answer_model="answer-model",
        warmup_replays=2,
        neural_min_warmup_steps=12,
    )

    assert args.mode == "generation"
    assert args.answer_model == "answer-model"
    assert args.warmup_replays == 2
    assert args.neural_min_warmup_steps == 12
    assert args.surprise_threshold == 0.001
    assert args.neural_initialization_seed == 42


def test_affinity_cli_refuses_inactive_parameter():
    with pytest.raises(SystemExit, match="affinity_weight is inactive"):
        main()
