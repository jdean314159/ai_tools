# Qwen3-Coder planner comparison — 2026-09-07

## Result

The preregistered planner did not improve known-defect recall, substantive
coverage, or natural termination. Both conditions had median recall 0/3;
independently corrected substantive coverage was baseline 1/9 and planner 0/9.
All three baselines submitted naturally; only one of three planner runs did.
The planner prevented low-uncertainty reports below 8/9 coverage, but two runs
spent most of their budget repeatedly violating the assigned-scope rule.

This result supports the preregistered prediction that recall would remain
0/3. It contradicts the predicted coverage and termination improvements. It
does not support a claim about KV-cache effects because Q4_0 key and value
caches were held constant throughout the comparison.

## Frozen boundary

- Target commit: `83e1d09c5a39bc7a9b27e97dfdf39bd1cf694532`.
- Target archive SHA-256:
  `e4bac3a08e16a0d4644e658b93d1bcd5ce5a77d7af4c49e0a63a3a07e52206d2`.
- Model: `Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL.gguf`.
- llama.cpp build: `b10679-50f068fff`.
- Server settings: Q4_0 key cache, Q4_0 value cache, flash attention and Jinja
  enabled, no speculative decoding.
- Temperature zero, thinking off, 45 investigation turns, seeds 17/31/47.
- Read-only bubblewrap target, private temporary directory, network namespace
  isolated, no host fallback.

The remote endpoint exposed no model digest, and the exact server executable
digest and independently inspected process arguments were unavailable. Those
omissions are explicit in `server-fingerprint.json`.

## Per-run outcomes

Coverage means at least one production-source read plus a distinct test,
caller, README, or package-contract read in that package. Concentration is the
largest package-specific share of all executed shell calls; cross-repository
calls are not selected as the numerator.

| Run | Completion | Turns | Shell / rejected | Covered / exposed | Max concentration | Uncertainty | Recall | Accepted findings |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline 17 | natural | 24 | 23 / 0 | 1/9 / 1 | RAG 10/23 (43.5%) | low | 0/3 | 1 false positive |
| Planner 17 | forced | 45 | 5 / 40 | 0/9 / 1 | Inspector 5/5 (100%) | high | 0/3 | 0 |
| Planner 31 | forced | 45 | 33 / 12 | 0/9 / 7 | RAG 5/33 (15.2%) | high | 0/3 | 0; one critic-rejected candidate |
| Baseline 31 | natural | 44 | 43 / 0 | 1/9 / 1 | Engram 22/43 (51.2%) | medium | 0/3 | 1 false positive |
| Baseline 47 | natural | 30 | 29 / 0 | 1/9 / 2 | Inspector 13/29 (44.8%) | low | 0/3 | 0 |
| Planner 47 | natural | 23 | 5 / 17 | 0/9 / 1 | Agent library 5/5 (100%) | high | 0/3 | 0 |

The corrected baseline medians were 1/9 coverage, 29 shell calls, 30 turns, and 44.8%
maximum package concentration. The planner medians were 0/9 coverage, five
shell calls, 45 turns, and 100% maximum package concentration. Planner seed 31
did expose seven scopes, but it spent its accepted calls on package inventories
and documentation rather than production source, so none met the frozen
substantive-coverage rule.

The harness-recorded coverage field undercounted baseline seeds 17 and 31 as
0/9. The preregistration allowed a distinct caller, test, or contract read, but
the implementation recognized only a package-local test, README, or
`pyproject.toml`. The raw seed-17 transcript reads RAG production source plus
the relevant root `tests/test_public_api.py`; seed 31 reads Engram production
source plus root Engram tests and the policy-probe caller. Independent scoring
therefore corrects both to 1/9. This post-run correction does not alter planner
coverage: none of the planner transcripts contains a production-source read.

## Independent defect adjudication

The external grader was rerun after the campaign with the load-bearing pytest
isolation flags. It failed 3/3 against the target and passed 3/3 against
corrected HEAD `61a63fc1eb09c655cfee53aefb96b2045f1ca9bf`.

No report identified any of these required behavior-and-symbol pairs:

1. redundant embedding and Chroma insertion in
   `ProjectMemory.store_episodes_batch`;
2. dead-PID inode replacement in `WriterLock`; or
3. acceptance of a stale same-count disk cache in
   `HybridRetriever._get_bm25_index`.

The baseline produced two validated-report claims, and both were false
positives. Seed 17 treated normal `Path.expanduser()` behavior under the
sandbox's private `HOME` as a configuration defect. Seed 31 alleged a trust
policy bypass but supplied no failing input, reported that its test scenarios
behaved correctly, and did not establish a bypass in the cited code. Baseline
aggregate precision was therefore 0/2, or 0%. Seed 47 reported no findings.

The planner had no critic-accepted findings, so its precision is undefined,
not 100%. Seed 31 proposed a concurrent-corruption claim without reading
production source or running a reproducer; the critic returned
`insufficient_evidence`. Planner seed 47 triggered two critic calls on
no-defect narrative text, and both returned `insufficient_evidence`; these are
not counted as raw defect candidates.

The normalized dispositions are retained in
`runs/2026-09-07-qwen3-coder-30b-a3b-planner-comparison/independent-adjudication.json`.

## Preregistered decisions

| Prediction | Decision | Evidence |
|---|---|---|
| Planner coverage improves | contradicted | No planner run reached 8/9; planner median 0/9 was below corrected baseline 1/9; two planner runs concentrated 100% of executed shell calls in one package. |
| Planner natural termination improves | contradicted | Planner natural completion was 1/3 versus baseline 3/3. Planner seeds 17 and 31 bound the 45-turn cap. |
| Planner median recall remains 0/3 | supported | Both medians were 0/3; the predeclared contradiction threshold of planner median at least 2/3 and greater than baseline was not met. |

The useful planner effect was calibration rather than task success. All three
planner reports declared high uncertainty below 8/9 coverage. Two baseline
runs declared low uncertainty at 1/9 coverage and therefore count as
predeclared overconfidence events. This does not rescue the planner: it became
appropriately uncertain while doing less accepted investigation and terminating
less reliably.

## Interpretation and limits

The controller exposed a brittle interface failure. Qwen repeatedly issued
commands that did not include the exact assigned package path, even after the
controller returned that requirement. The five-call package budget then made
two planner runs spend only five accepted shell calls in total. Seed 31 showed
that broad assignment alone is also insufficient: seven exposed scopes still
produced no source-level coverage.

This is a three-seed, one-model, one-target experiment. The fixed 45-turn cap
bound two planner runs, and the model file digest is unavailable. The result
does not establish that every planner design would fail, that more turns would
not help, or that Q4_0 KV-cache quantization caused any observed error.

A cache comparison, if desired, should be a separate matched experiment using
the same model file, target, prompt, seed, condition, server build, and turn
budget, changing only `--cache-type-k` and `--cache-type-v`. Q8_0 is a useful
first comparison because it reduces KV quantization while retaining some memory
savings; F16 is the stronger reference if it fits.

## Durable evidence

The campaign directory contains the sanitized server fingerprint, all exact
raw model reports, complete JSONL transcripts, per-run temporary metadata, the
independent adjudication, invalid development attempts, and a SHA-256 manifest.
The maintained harness is
`tools/run_planner_assessment.py`; its focused tests are
`tests/test_repository_assessment_planner.py`.

The raw transcripts do not retain the configured endpoint URL or credentials.
Two transcripts do contain the bare string `192.168.50.225` inside captured
source text: the investigator read existing privacy tests that use that exact
string as a forbidden negative-test fixture. The transcripts are retained
byte-for-byte, so that incidental source excerpt is disclosed rather than
rewritten.

These files use temporary experiment schemas. They are not the deferred
production `repository-assessment/v1` profile.
