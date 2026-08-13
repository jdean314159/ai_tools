# RUN-RECORD-00 Phase 7 — offline course-fixture pilot

**Status:** Complete, 2026-08-13.
**Scope:** One privacy-safe recorded failure lab, the minimum Inspector support
needed to diagnose it, deterministic fixture generation, and teaching-entry
links. No course-repository split, notebook rewrite, new model run, UI, RAG, or
general redaction framework.

## Frozen question

> Can a student diagnose why a run failed using only the portable bundle and
> Inspector, without model access or hidden instructor knowledge?

The pilot uses the committed ASC worker-only campaign because one configuration
contains three informative outcomes under the same local backend:

- visible pass and held-out pass;
- visible fail and held-out pass; and
- visible pass and held-out fail.

The source campaign also completed 20/20 runs with no timeouts and reported a
headline gaming rate of `0.0`. This creates a useful contrast between a healthy
dashboard summary and item-level evidence.

## Fixture

`course/failure_labs/evaluation_blind_spot/fixture/` is a portable artifact
bundle containing one experiment and three required child agent-run artifacts.
The builder freezes the source report SHA-256 and selects seed 0 for one record
of each outcome shape. Rebuilding into an empty directory is byte-for-byte
deterministic.

The fixture allowlists scalar facts only:

- task ID and tier;
- mode and seed;
- completion status and step count;
- visible and held-out pass booleans;
- source classification and input-special-casing signal; and
- public backend/model/quantization labels.

The aggregate also records the headline metric's population explicitly: ten
worker-only, gaming-tempting-tier runs, zero positive classifications, with the
escalation tier excluded. This makes the lesson's coverage diagnosis available
from recorded evidence instead of requiring students to infer metric scope from
tier names.

It omits workspace paths, prompts, source code, final output, reasoning traces,
tool observations, free-text held-out details, and timing. Both root and child
artifacts declare their null/empty body fields in `omissions`, make no executable
replay claims (an empty `capabilities` list), and declare public sensitivity and
scoped validation under `course-evaluation-summary-v2`. The v2 fixture policy
also participates in deterministic child identity, so adding these declarations
creates new immutable artifacts rather than changing old bytes under old IDs.
Integrity and privacy minimization are enforced
by tests; the declaration is not inferred merely because the files are in the
course tree.

## Capability forced by the pilot

Phase 6 Inspector could validate the root and its attachments but did not
interpret resolved child artifacts. The frozen question therefore failed on
first contact: students could see that three children existed but not what
happened in them.

The bounded correction adds:

- resolved `child_run_artifact` traversal for bundle-directory inspection;
- sanitized child summaries without resolved filesystem paths;
- scalar agent evaluation signals (`classification`, `visible_pass`,
  `held_out_pass`, `input_special_casing`); and
- numeric/boolean experiment aggregate signals and bounded decision-status
  fields (`decision`, `verdict`, `status`).

Invalid child JSON is reported as an invalid child rather than crashing the
root inspection. Prompts, reasoning, tools, source, and final output remain
outside summaries.

## Student diagnosis

Inspector alone now exposes:

- the both-pass control;
- a visible-oracle false negative;
- a visible-oracle false positive against held-out behavior;
- normal completion for all three; and
- the apparently healthy campaign aggregate.

The exercise explicitly forbids inferring model intent from the harness label
`gaming`. The evidence supports an evaluation-coverage diagnosis, not a claim
about internal motivation.

## Validation

Tests prove deterministic rebuild, source-digest binding, attachment integrity,
privacy-field minimization, public/scoped declarations, and the complete
expected diagnosis from `inspect_artifact_path()` output. The repository's
teaching-artifact checker runs the offline Inspector command and requires the
evaluation signals to appear.

Validation results:

```text
focused fixture/Inspector/core/adapter gate:                 41 passed
combined relevant packages/integration/public/import gate: 259 passed, 9 skipped
teaching-artifact checker:                                  passed
```

The nine skips are the repository's expected optional/integration skips,
including the Engram golden when `--run-engram` is not enabled.

### Post-review correction gate

An external document-only review exposed three real teaching defects: omitted
field reasons were not recorded, the headline metric's population was not
defined in the artifact, and the curriculum manifests had drifted. Fixture v2
and the teaching checker close those gaps. The exact student Inspector command
was also rerun; it exposes `common.child_artifacts[*].body_summary.evaluation_signals`
and `body_summary.aggregate_signals` as documented.

```text
focused fixture and Inspector gate: 16 passed
full repository gate:              990 passed, 250 skipped
teaching-artifact checker:         passed (11 notebooks, 3 starter projects)
Ruff and git diff checks:          passed
```

## Gate assessment

The frozen question passes. RunRecord can support a useful no-GPU failure lesson
and, importantly, the lesson forced a generic missing inspection capability
rather than course-specific schema fields. This is evidence for proceeding with
the separate curriculum project, not authorization to split or rewrite the
course in this phase.
