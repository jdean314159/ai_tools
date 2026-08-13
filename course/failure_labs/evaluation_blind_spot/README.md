# Failure lab — when the green check is wrong

This offline lab uses a privacy-safe recorded bundle from a real local-model
campaign. You do not need a GPU, Ollama, or network access.

## Question

The campaign dashboard looks healthy. Is that enough evidence that the system
and its evaluation were reliable? Use the experiment's `aggregate_signals` and
the three recorded child runs to identify:

1. which run is a genuine both-check success;
2. which run is rejected by the visible check despite passing the held-out
   check;
3. which run passes the visible check but fails the held-out check; and
4. why neither a completed status nor the headline rate establishes task
   correctness.

Do not infer model intent from a classification label. Diagnose only what the
recorded evidence supports.

## Inspect the bundle

From the course repository root after installing `llm_inspector`:

```bash
llm-inspect artifact show \
  failure_labs/evaluation_blind_spot/fixture \
  --format json
```

Look under `common.child_artifacts`. For each child, compare:

- `status`;
- `evaluation_signals.visible_pass`; and
- `evaluation_signals.held_out_pass`.

Then compare those item-level facts with the experiment-level headline stated
in `body_summary.aggregate_signals`. Write a short diagnosis before reading
`SOLUTION.md`.

The `source_headline_scope_*` fields state which tier and mode feed that rate;
do not infer scope from task names. An empty `capabilities` list means the
artifact makes no executable replay or re-invocation claim. It is not a claim
that replay was attempted and failed.

## Optional verification

Check that all attached child records are present and unchanged:

```bash
python -m llm_harness_core.run_artifacts_cli \
  course/failure_labs/evaluation_blind_spot/fixture/record.json
```

The Inspector command performs the stronger bundle-aware check and reports
each attachment as `resolved`.

## Fixture provenance and privacy

The builder selects three seed-0 records from the committed ASC worker-only
campaign and allowlists scalar outcome facts. It omits workspace paths, source
code, prompts, final output, reasoning traces, tool payloads, free-text test
details, and timing. The source SHA-256 is frozen in `build_fixture.py`.

Students do not need the private provenance input to use the committed bundle.
Maintainers with the frozen ASC campaign source can rebuild into a new empty
directory by supplying it explicitly:

```bash
python failure_labs/evaluation_blind_spot/build_fixture.py \
  --source /path/to/asc02_worker_only/live_probe_results.json \
  --output /tmp/evaluation-blind-spot-fixture
```
