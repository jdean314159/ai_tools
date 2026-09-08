# Qwen3-Coder 30B-A3B known-defect baseline — 2026-09-06

## Question and frozen boundary

Can the Spark-hosted Qwen3-Coder endpoint find real defects in a read-only
snapshot of `ai_tools` when neither the prompt nor the model is told which
defects are present?

The target was commit
`83e1d09c5a39bc7a9b27e97dfdf39bd1cf694532`, exported with `git archive` into
an isolated directory. The harness exposed that snapshot as read-only
`/workspace` through bubblewrap, provided a private writable `/tmp`, unshared
the network namespace, and disabled host fallback. The model received the
archived assessment prompt, the `shell` and `submit_report` tools, temperature
zero, thinking off, seed 7, and a 45-turn investigation budget.

The served label was
`Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL.gguf`. Its digest and the llama.cpp
build commit were not captured. The endpoint URL was deliberately omitted.

## Why this baseline is different

This is the first repository-assessment campaign in this project with an
external, deterministic grader for defects that existed independently of the
assessment. Previous model campaigns used synthetic cases authored for the
campaign. Here, three regression tests fail on the frozen target and pass on
the corrected checkout, so known-defect recall does not depend on judging the
persuasiveness of the model's prose.

The grader covers these defects:

1. `ProjectMemory.store_episodes_batch()` performs redundant batch embedding
   and Chroma insertion after per-episode storage, including rejected input in
   its positional batch. This was fixed by commit `6edcd06`.
2. `WriterLock` treats dead PID text as authority and unlinks a pathname whose
   inode may still be protected by an active `flock`. This was fixed by commit
   `799f89d`.
3. `HybridRetriever._get_bm25_index()` accepts a persisted same-count BM25
   cache without comparing its build time with the collection mutation marker.
   This was fixed by commit `4fa226d`.

The fourth issue from the earlier Qwen3.8 assessment is intentionally absent:
`scripts/clean_review_bundle.py` did not enter Git history until its fix commit,
so it is not present at `83e1d09` and cannot be scored on this target.

## Objective grader result

The durable grader is
[test_known_defects_at_83e1d09.py](tools/test_known_defects_at_83e1d09.py).
With imports resolved from the frozen snapshot it produced three failures. The
failures directly showed a batch embedding call, successful acquisition after
unlinking an actively locked inode, and reuse of the stale ID `old`. With the
same grader resolved against current HEAD `61a63fc`, all three tests passed.

| Code under test | Grader outcome |
|---|---:|
| Frozen target `83e1d09` | 0 passed, 3 failed |
| Corrected HEAD `61a63fc` | 3 passed, 0 failed |

This target/HEAD contrast establishes that all three scored defects are present
at the target and absent after their fixes. It does not prove that the list is
complete or that the grader covers every consequence of each defect.

For either run, supply an explicit `PYTHONPATH` containing the selected
checkout's package `src` directories and invoke pytest with `-c /dev/null`,
`--noconftest`, `--import-mode=importlib`, and `--rootdir=/tmp`. These flags are
load-bearing: without them, pytest can discover the live checkout's root
configuration from the grader's durable path and redirect imports to HEAD.

## Model outcome

The model used the full investigation budget and did not submit naturally. The
harness then requested a report-only continuation, retained the report in the
same run, and recorded `lifecycle="aborted"` with
`completion_mode="forced"`. The complete run took approximately 4 minutes 19
seconds and recorded 45 shell calls, 775,164 cumulative input tokens, 9,130
output tokens, and no rejected tool calls.

The first three shell calls inventoried the repository and read its root
README. The remaining 42 of 45 calls, or 93.3%, concentrated on
`llm_inspector`; none inspected implementation or tests in the other six core
package scopes mounted on the harness import path, or in the two additional
top-level packages listed by the root README. The model did not read
`AGENTS.md`, `docs/design/VISION.md`, or
`docs/internal/STATUS.md` despite the user prompt asking it to begin with those
documents. It ran eight narrow Inspector test commands and repeatedly explored
one duplicate-section-key hypothesis.

At forced termination, after spending 42 of 45 shell calls in one package and
recalling 0 of 3 independently reproducible defects, the model reported no
validated findings and stated that there was "No significant remaining
uncertainty." Because it reported no findings, the false-positive count is
zero; precision is undefined, not 100%.

## Interpretation and limits

The clean result is: in one run against a frozen target with an objective
three-defect grader, this model scored 0/3 known-defect recall.

This is not a controlled comparison with the earlier GLM-4.7-Flash or
Qwen3.8-27B assessments. Those runs used a different working tree, their exact
dirty-tree fingerprints and prompts were not durably retained, and their
reported findings were not scored against this frozen target. The result must
not be described as this model outperforming or underperforming either model.

The sample size is one and the 45-turn cap bound. It is unknown whether a
larger budget would change recall. The failure nevertheless exposes a concrete
calibration problem: the run had inspected only one of seven core package
scopes on the harness import path—and one of nine top-level packages listed by
the root README—when its forced report claimed no significant remaining
uncertainty.
Forced reporting, rather than a natural stop, must remain visible in any future
comparison.

## Durable evidence

The exact original bytes are under
[runs/2026-09-06-qwen3-coder-30b-a3b](runs/2026-09-06-qwen3-coder-30b-a3b/):

| File | SHA-256 |
|---|---|
| `assessment-harness.py.raw` | `01920495a40681b321440b05dfeba81c0148b25fe5ce416e3a740d8a779ec7c2` |
| `independent-adjudication.json` | `4c48300ef3201f90f778bb4fbbd54d9b2dcd43197a16e7a1a4982a212704838c` |
| `raw-model-report.md` | `d8ff2e4cf594a4a600fc3198fa4ad163e621a89ea2f5d1201bd3b6b20cefecac` |
| `run-metadata.json` | `6b74146a8b828effb68fad14c23b0455149607f581a2465c41fb0bec13c9ef46` |
| `transcript.jsonl` | `a83dc4ee98211b9b0c6613afc7da528c5d837ae07eee33ad28c1d6ccf3eca92c` |

The metadata's randomized `/tmp` target path is retained as part of the exact
original bytes. It is ephemeral and is not required to reproduce the target;
the full target commit is the durable identity. The temporary metadata schema
is evidence from this run, not an implementation of the selected
`repository-assessment/v1` production profile.

Future profile work must retain at least the frozen commit, target and HEAD
grader outcomes, turn cap and whether it bound, shell-call count, per-package
call distribution, the known-defect list and recall, completion mode, and the
model's stated uncertainty. Raw model claims, model-gathered evidence, and
independent adjudication remain separate layers. Production schema work is
still deferred pending an explicit profile draft.
