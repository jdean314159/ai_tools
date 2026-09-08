# Ornith 1.5 35B known-defect baseline — 2026-09-07

## Result

Ornith did not improve the objective repository-defect score. All three
preregistered seeds recalled 0/3 frozen grader defects, matching the
Qwen3-Coder Q4_0 baseline median of 0/3. All three Ornith runs also bound the
45-turn cap and required forced reports, compared with natural submission in
3/3 matched Qwen baseline runs.

The useful positive result is narrower. Seeds 17 and 47 read an internal
handoff that explicitly named two OPEN Engram trust-policy defects, then ran
reproducers. Independent execution confirms both behaviors on the frozen target
and current HEAD. Ornith therefore demonstrated useful verification of supplied
leads, but neither hidden-defect recall nor independent discovery.

## Frozen boundary

- Preregistration:
  [Ornith known-defect preregistration](ORNITH-1.5-35B-KNOWN-DEFECT-PREREGISTRATION-2026-09-07.md).
- Target commit:
  `83e1d09c5a39bc7a9b27e97dfdf39bd1cf694532`.
- Target archive SHA-256:
  `e4bac3a08e16a0d4644e658b93d1bcd5ce5a77d7af4c49e0a63a3a07e52206d2`.
- Model endpoint label: `Ornith-1.5-35B-Q4_K_M.gguf`.
- llama.cpp build: `b10679-50f068fff`; four 262,144-token slots.
- User-reported Q4_0 key/value caches, flash attention, Jinja templates,
  draft MTP, and maximum three draft tokens.
- Slot-level endpoint records confirmed `speculative: true` and
  `speculative.types: none,draft-mtp`.
- Baseline condition, seeds 17/31/47, temperature zero, thinking off, and 45
  investigation turns.
- Read-only bubblewrap target, private temporary directory, isolated network,
  and no host fallback.

The prior Qwen Q4_0 baseline had speculative decoding disabled. Any comparison
is therefore between endpoint configurations and cannot isolate model weights
from MTP or their interaction. Model-file and server-executable digests remain
unavailable.

## Per-run outcomes

Coverage applies the preregistered rule after independently normalizing the
relative paths in each transcript. Concentration is the largest
package-specific share of all shell calls.

| Seed | Completion | Turns / shell | Coverage | Max concentration | Uncertainty | Frozen recall | Report claims |
|---:|---|---:|---:|---:|---|---:|---|
| 17 | forced | 45 / 45 | 1/9 | Engram 36/45 (80.0%) | medium | 0/3 | 2 confirmed disclosed defects; 1 non-defect test gap |
| 31 | forced | 45 / 45 | 2/9 | Engram 14/45 (31.1%) | low | 0/3 | none |
| 47 | forced | 45 / 45 | 1/9 | Engram 28/45 (62.2%) | medium | 0/3 | 1 repeated confirmed disclosed defect |

Medians were 1/9 coverage, 45 turns, 45 shell calls, 1,648,791 cumulative input
tokens, 7,632 output tokens, 201.0 elapsed seconds, and 62.2% maximum package
concentration. Seed 31's low uncertainty at only 2/9 substantive coverage is
an overconfidence event under the existing 8/9 threshold.

The harness recorded 0/9 coverage for each run because its passive path parser
recognizes literal `/workspace/package` paths but these model commands mostly
used paths relative to `/workspace`. Independent scoring finds Engram covered
in all three runs and `llm_engines` additionally covered in seed 31. The raw
metadata is preserved unchanged; the correction is explicit in
`independent-adjudication.json`.

## Objective defect adjudication

The external grader was rerun after the campaign. A first target invocation is
retained in the adjudication as infrastructure-invalid because current
checkout `conftest.py` put HEAD packages ahead of the requested target
`PYTHONPATH`; import-provenance enforcement exposed the mismatch. The corrected
isolated invocation failed 3/3 on the target, while current HEAD
`61a63fc1eb09c655cfee53aefb96b2045f1ca9bf` passed 3/3.

No Ornith report identified any frozen behavior-and-symbol pair:

1. redundant embedding and Chroma insertion in
   `ProjectMemory.store_episodes_batch`;
2. dead-PID inode replacement in `WriterLock`; or
3. acceptance of a stale same-count disk cache in
   `HybridRetriever._get_bm25_index`.

Recall was therefore 0/3 for seeds 17, 31, and 47. The preregistered material
improvement threshold was not met.

## Separately confirmed disclosed defects

Seeds 17 and 47 both read
`docs/internal/CLAUDE_VERIFICATION_HANDOFF_2026-09-01.md`, whose OPEN section
states the following two defects explicitly. They then inspected the named
symbols and ran focused reproducers:

1. `ProjectMemory.get_facts()` calls the semantic graph without applying its
   configured `MemoryTrustPolicy`, allowing a cross-tenant fact through the
   public fact API.
2. `_extract_and_store_facts()` retains only `role` and `session_id`, omitting
   trust, tenant, source, and writer metadata; policy-enabled prompt composition
   consequently drops extracted facts fail-closed.

An independent reproducer confirmed both behaviors on the frozen target and
current HEAD. The first contradicts the documented claim that an external
retriever cannot bypass the policy. The second behavior is real, but its fix
must decide whether extraction inherits source trust or receives a distinct
derived-fact classification. These are actionable existing issues, not newly
discovered issues, and they do not increase recall against the frozen grader.

Seed 17 labeled the missing `get_facts` trust-policy test as a third validated
finding. Independent adjudication treats that as a useful coverage gap, not a
separate implementation defect. Across repeated reports, Ornith made four
validated-finding claims: three true claim instances and one non-defect, for
aggregate precision 3/4 (75%). There are two unique confirmed defects and zero
unique newly discovered defects.

## Comparison with Qwen3-Coder

| Boundary | Qwen3-Coder Q4_0 | Ornith with MTP |
|---|---:|---:|
| Basic capabilities | 20/20 | 20/20 |
| Single-turn tool decisions | 12/12 | 12/12 |
| Multi-turn recovery | 6/12 | 12/12 |
| Median frozen-defect recall | 0/3 | 0/3 |
| Median substantive coverage | 1/9 | 1/9 |
| Natural completions | 3/3 | 0/3 |
| Median shell calls | 29 | 45 |
| Median cumulative input tokens | 391,057 | 1,648,791 |
| Median output tokens | 4,213 | 7,632 |
| Median maximum package concentration | 44.8% | 62.2% |

Ornith used about 4.2 times the median cumulative input tokens and exhausted
every investigation budget. The differing trajectories and active MTP make
this unsuitable as a throughput benchmark. The decision-quality result is
still exact: perfect synthetic recovery did not transfer to hidden-defect
recall, coverage, or autonomous stopping on this task.

## Preregistered decisions

| Prediction | Decision | Evidence |
|---|---|---|
| Median known-defect recall remains 0/3 | supported | All three scores were 0/3. |
| All three runs submit naturally | contradicted | All three bound 45 turns and required forced reports. |
| Median substantive coverage remains 1/9 | supported | Corrected coverage scores were 1/9, 2/9, and 1/9. |

## Durable evidence and limits

The campaign directory retains the server fingerprint, all three exact JSONL
transcripts, raw reports, run metadata, independent adjudication, independent
trust reproducer and results, and a SHA-256 manifest. The endpoint URL and
credentials are not retained. The files use temporary experiment schemas and
do not implement the deferred production `repository-assessment/v1` profile.

This is three seeds on one historical target. The target documentation supplied
the two non-grader leads, every run hit the fixed turn cap, and the server
configuration differed from Qwen by model and active MTP. The result does not
establish general coding quality, that Ornith cannot find undisclosed defects
elsewhere, or whether a different turn budget would change recall.
