# Engram prompt hygiene remediation

## What was fixed

This pass targeted the `engram` failure mode exposed by the user's local diagnostic run:
correct canonical facts were present in semantic memory, but stale values still leaked into the final prompt through raw episodic text and verbose semantic metadata.

### Changes

- Canonical prompt rendering for semantic memory
  - `ContextResult.to_prompt_sections()` now renders semantic rows as concise canonical content/value text.
  - Verbose fields like `surface_text`, `old_value`, `match_score`, ids, and metadata blobs are no longer injected into the prompt.

- Canonical prompt rendering for episodic update/correction items
  - Episodic `Preference:`, `Decision:`, `Correction:`, and `Update:` forms are rewritten into positive canonical prompt text.
  - Raw stale alternatives like `not Tuesday`, `instead of qwen3:8b`, and `not in Google Docs` are suppressed in the final prompt.

- Stronger transient-note filtering
  - `Transient note:` turns and similar "only asking about ... because I was mistaken" notes are now treated as ephemeral by the ingestion policy and are no longer written into durable memory.

- Lower irrelevant episodic carryover
  - Episodic retrieval now skips low-importance candidates that have zero lexical and density overlap with the active query.
  - This reduces the tendency for unrelated durable preferences to appear in arbitrary probes.

- Stats quality-of-life fix
  - episodic stats now include a `count` alias alongside `total_episodes`, matching the rest of the evaluation tooling more closely.

## Validation

- `python -m compileall -q engram integration_tests`
- `pytest -q engram/tests/test_prompt_canonicalization.py`
- `PYTHONPATH=. python integration_tests/memory_eval.py --suite`

## Result

The deterministic shared memory harness is green again after the prompt-hygiene cleanup:

- `engram_lite`
  - `probe_pass_rate: 1.0`
  - `prompt_pass_rate: 1.0`

- `engram`
  - `probe_pass_rate: 1.0`
  - `prompt_pass_rate: 1.0`

## Most important takeaway

The earlier local diagnostic was accurate: `engram` already had the right canonical facts.
The main weakness was prompt assembly hygiene, not total memory failure.
This pass fixes that by ensuring canonical facts go in and canonical facts come out.
