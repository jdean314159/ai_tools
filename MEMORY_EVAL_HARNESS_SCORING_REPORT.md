# Memory Eval Harness Scoring Update

This pass updates the shared memory evaluation harness so that:

- `probe_pass_rate` reflects **prompt-effective memory quality** when a probe has a question and therefore a built prompt.
- `raw_probe_pass_rate` reflects the older **raw retrieved evidence** scoring behavior.
- `failed_probes` lists probes that fail on the model-facing prompt path.
- `failed_raw_probes` lists probes that still fail only at the raw retrieval layer.

Rationale:

The prior harness could penalize `engram` for stale terms that were present in raw retrieved evidence but were successfully canonicalized away before prompt assembly. That made the benchmark conflate two different questions:

1. Was the raw retrieved evidence perfectly clean?
2. Did the correct, canonical memory actually reach the model?

The updated harness keeps both views, but treats the second question as the primary pass/fail signal for prompt-bearing probes.

Validation completed:

- `python -m compileall -q integration_tests`
- `PYTHONPATH=. pytest -q integration_tests/test_memory_eval.py`
- `PYTHONPATH=. python integration_tests/memory_eval.py --suite`

The generated sample suite report now includes both `probe_pass_rate` and `raw_probe_pass_rate`.
