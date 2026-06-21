# Neural Memory A/B Evaluation

This explicitly-run integration harness compares current Engram with neural
memory disabled and enabled. It always captures a fresh current-architecture
baseline; historical recovered results are not bundled or read.

The decision rule is fixed before evaluation: neural memory must improve decoy
rejection and contradiction resistance, lose no more than five percentage
points on direct or paraphrase recall, and introduce no other regression beyond
that five-point noise threshold.

Smoke runs:

```bash
python integration_tests/eval/run_eval.py \
  --backend baseline --trials baseline --limit 3 \
  --mode generation --warmup-replays 1 \
  --neural-min-warmup-steps 3 \
  --judge ollama --model qwen3:8b \
  --run-name neural06-smoke-baseline --fresh

python integration_tests/eval/run_eval.py \
  --backend neural_on --trials baseline --limit 3 \
  --mode generation --warmup-replays 1 \
  --neural-min-warmup-steps 3 \
  --judge ollama --model qwen3:8b \
  --run-name neural06-smoke-neural --fresh
```

The smoke-only threshold override ensures three facts exercise context
synthesis. Confirm baseline reports `n_neural_hints: 0` and neural-on reports
`n_neural_hints: 9`. Full decision runs retain the default threshold of 50.

Full runs omit `--trials` and `--limit`. Results are written under
`integration_tests/eval/runs/<backend>/results/`. Compare them with:

```bash
python -m integration_tests.eval.compare_backends \
  --baseline integration_tests/eval/runs/baseline/results/metrics.json \
  --neural-on integration_tests/eval/runs/neural_on/results/metrics.json \
  --output integration_tests/eval/runs/comparison.md
```

The harness uses local Ollama only. It does not restart services, generate the
corpus, or expose neural novelty through private state.

Use `--fresh` for the decision run so both sides capture current results from
empty, backend-specific stores. Judge and retrieval failures are reported and
excluded from metric denominators rather than treated as memory outcomes.

The judge defaults to `qwen3:8b`, four concurrent requests, deterministic
temperature, persistent model residency, and a disk-backed judgment cache.
For local Ollama, set `OLLAMA_NUM_PARALLEL=4` when the host has enough memory.

Run the fast affinity sweep with:

```bash
python integration_tests/eval/sweep.py \
  --trials baseline contradict --limit 30 \
  --affinity-weight-list 0.05,0.1,0.15,0.2,0.3,0.5
```

The sweep captures baseline once and reports the direct/paraphrase recall,
decoy rejection, and contradiction-bleed tradeoff for each weight. A passing
weight is only a finalist; it still requires the full six-trial confirmation.
