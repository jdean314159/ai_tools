# Memory contamination lab

This lab demonstrates a common memory failure mode: the model is shown a stale or over-strong memory string and reasons with the contaminant instead of the current-state fact.

The demo includes two scenarios:

- **docs policy** — the raw memory still contains `not in Google Docs`
- **model update** — the raw memory still contains `instead of qwen3:8b`

The repaired path does two things:

1. canonicalizes the memory into current-state wording
2. suppresses the stale alternative as an excluded evidence flow

## Run the example

```bash
PYTHONPATH=engram/src:llm_inspector/src:llm_harness_core/src:. python engram/examples/memory_contamination_lab.py
```

## What to inspect

- the `Memory` section for the broken and repaired paths
- the `Evidence flow:` section
- the included flow from raw memory to canonical current-state text
- the excluded stale alternative with `exclusion_reason=stale_alternative_suppressed`
- the evaluation summary showing the repaired path passes and the broken path fails

## Teaching goal

Students should learn that memory quality is not just about retrieving *a* relevant record. It is also about:

- whether the retrieved wording contains stale alternatives
- whether the memory is normalized into current-state prompt text
- whether contaminants are visibly suppressed rather than silently ignored

## Suggested exercise

Add a third scenario involving a transient instruction such as `For this message only, greet cheerfully.`
Then modify the lab so the repaired path excludes that note as ephemeral memory while the broken path lets it influence the answer.
