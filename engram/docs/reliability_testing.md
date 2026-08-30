# Reliability testing

Memory tests should distinguish storage, retrieval, prompt composition,
inference, and scoring. A correct final answer alone does not prove that memory
was safe: a model may answer correctly despite obsolete evidence in its prompt.

## Inspect an Engram prompt

```python
result = memory.build_prompt(
    "What is the current deployment region?",
    reserve_output_tokens=128,
    return_trace=True,
)

print(result["budget_diagnostics"])
print(result["retrieval_diagnostics"])
for evidence in result["trace"].evidence:
    print(evidence.source, evidence.meta.get("episode_id"), evidence.meta)
```

Important budget fields include:

- `candidate_item_counts`
- `included_item_counts`
- `excluded_item_counts`
- `memory_candidate_count`
- `memory_included_count`
- `memory_starved`

Important retrieval fields include:

- `used_vector_search`
- `vector_filtered_count`
- `relevance_filtered_count`
- `include_historical`
- `temporal_filtered_count`
- `unresolved_conflict_topic_count`

## Deterministic stage attribution

```python
from engram import observation_from_engram
from llm_harness_core import MemoryCaseSpec, evaluate_memory_case

retrieved = memory.search_episodes("current deployment region")
prompt_result = memory.build_prompt(
    "What is the current deployment region?",
    query="current deployment region",
    return_trace=True,
)

observation = observation_from_engram(
    stored_count=2,
    retrieved_items=retrieved,
    prompt_result=prompt_result,
    observed_output={"value": "eu-central-1", "evidence_id": "current"},
)

evaluation = evaluate_memory_case(
    MemoryCaseSpec(
        case_id="region",
        expected_storage_count=2,
        required_evidence_ids=("current",),
        forbidden_prompt_ids=("obsolete",),
        expected_output={
            "value": "eu-central-1",
            "evidence_id": "current",
        },
    ),
    observation,
)

print(evaluation.primary_failure_stage)
print(evaluation.issue_codes)
```

Evidence IDs should be stored in structured metadata using `evidence_id`,
`ledger_event_id`, `memory_id`, or the native `episode_id`. The Engram adapter
extracts these IDs from retrieval results and prompt evidence traces.

Use `forbidden_retrieval_ids` when an item must not be retrieved at all. Use
`forbidden_prompt_ids` when retrieval may inspect an item but composition must
exclude it. `forbidden_evidence_ids` applies to both stages.

## Artifact safety

`llm_harness_core.build_memory_experiment_body(...)` produces a summary without
raw prompts, memory text, or model outputs. `prepare_new_artifact_path(...)`
creates the parent directory and refuses overwrite. Applications remain
responsible for reviewing arbitrary values placed in custom diagnostics.

## Interpretation

- Storage failure: the expected record was not persisted.
- Retrieval failure: required evidence was absent from candidates.
- Composition failure: retrieval succeeded, but prompt evidence was missing,
  forbidden, or starved by the token budget.
- Inference failure: the model request did not complete.
- Scoring failure: inference completed but exact registered fields differed.

Freeze cases and expectations before live execution. Do not repair a failed
score with an after-the-fact semantic judge; create a new profile when the
original contract was invalid.
