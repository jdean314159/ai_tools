# Canonical Evaluation Walkthrough

This guide is the default teaching path for **measuring whether an LLM application actually improved**.

It is intentionally simple:
- start with a baseline answer
- compare it with an augmented answer
- score both with a shared evaluator
- inspect the evidence and rationale before claiming improvement

## Where this fits in the course

Use this after:
- Stage 3 for memory comparisons
- Stage 4 for retrieval comparisons
- Stage 5 when studying the reference application
- Stage 6 when evaluating agent runs

The point is not to add a giant benchmarking framework early. The point is to teach a durable habit:

> **Do not add memory, retrieval, or agents without a way to compare baseline and augmented behavior.**

## Minimal evaluation loop

1. Define a question or probe.
2. Capture a baseline answer.
3. Capture an augmented answer.
4. Choose an evaluator.
5. Record the score, rationale, and evidence.
6. Inspect failures before drawing conclusions.

## Evaluators in `llm_harness_core`

The shared teaching defaults are:
- `SubstringMatchEvaluator` for deterministic probes and policy checks
- `SimilarityEvaluator` for fuzzy text comparison against a reference answer
- `RubricEvaluator` for structured custom scoring
- `LLMJudgeEvaluator` for judge-model scoring when the simpler evaluators are insufficient

Prefer the cheapest evaluator that answers the question honestly.

## Recommended teaching order

### 1. Start with deterministic checks

Use substring matching when you want to verify things like:
- a preference was retained
- a stale fact was replaced by an update
- forbidden or contaminated content stayed out of the answer
- required evidence or citations appeared

### 2. Add similarity when wording varies

Use similarity only when a deterministic matcher would be too brittle.

### 3. Add rubric or LLM-as-judge last

Use these only when you need judgment across multiple dimensions such as:
- factual correctness
- evidence use
- completeness
- safety or policy adherence

## Memory walkthrough

The canonical memory harness is:
- `integration_tests/memory_eval.py`

The convenience runner is:
- `run_answer_uplift_eval.py`

The summary helper is:
- `summarize_answer_uplift.py`

This harness compares `engram` and `engram` on:
- signal retention
- paraphrase recall
- decoy rejection
- update resolution
- noise rejection
- optional answer uplift when a real model is configured

## Retrieval walkthrough

A retrieval evaluation should use this small but important pattern:
- score the answer itself
- score whether required evidence is present
- compare baseline vs grounded output separately

## Agent walkthrough

For agent work, treat evaluation as two layers:
- task success
- process quality

That means you should score not only the final answer, but also whether the agent:
- used the right tools
- exposed reasoning artifacts appropriately
- stayed inside safety boundaries
- degraded cleanly when a capability was unavailable

## What to log every time

At minimum, save:
- the prompt or probe
- the baseline answer
- the augmented answer
- evaluator name
- score and pass/fail
- rationale
- evidence snippets

## Common teaching mistakes

Avoid these failure modes:
- comparing only one augmented run with no baseline
- using an LLM judge where a deterministic evaluator would suffice
- claiming improvement from a single anecdote
- checking correctness without checking evidence contamination
- scoring final answers without recording the context that produced them

## Concrete next steps

1. Run the memory harness locally for a baseline/augmentation comparison.
2. Preserve the prompts, retrieved evidence, evaluator outputs, and runtime
   metadata as one versioned experiment artifact.
3. Compare answer quality and evidence presence separately.
