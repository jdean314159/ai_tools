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
  --neural-prompt-advisory \
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

The historical affinity sweep is disabled because neural recall re-ranking is
inactive. `affinity_weight` cannot change current retrieval results.

Neural episode-list prompt advisory is also default-off. Inspection of the
full evaluation state found that its selected episodes were unrelated for all
180 queries. Explicit advisory experiments must pass
`--neural-prompt-advisory`; ordinary neural runs do not emit these hints.
Surprise-based episode-importance adjustment is likewise default-off because
it changes retrieval indirectly without a usefulness label. Experiments must
opt in with `--neural-importance-advisory`.

Calibrate and evaluate the active RTRL/TITANS write gate with:

```bash
python integration_tests/eval/surprise_threshold_sweep.py \
  --trials baseline contradict --limit 30 --mode generation \
  --percentiles 25,50,75
```

The sweep first runs an ungated calibration, derives thresholds from measured
surprise percentiles, and reports write ratio alongside direct/paraphrase
recall, decoy rejection, and contradiction bleed. Fresh RTRL initialization is
seeded so candidates begin from identical weights. A passing threshold is only
a finalist; it still requires the full six-trial confirmation. “Write ratio”
means RTRL parameter updates, not Engram episode admission.

Advisory inspection and candidate-utility experiments are implemented in
`inspect_advisory.py` and `candidate_utility_eval.py`. Their completed NEURAL-07
results are summarized in
`docs/projects/engram/NEURAL-07-RTRL-OUTPUT-EVALUATION.md`; neither experiment
earned a production output path.
