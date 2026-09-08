# Qwen3-Coder Q4_0 versus Q8_0 KV-cache comparison — 2026-09-07

## Result

The Q8_0 block had different investigation trajectories but did not improve
the objectively graded result. Q4_0 and Q8_0 both scored 0/3 known-defect
recall in all three paired seeds. Q8_0 produced three false positives versus
two under Q4_0. The preregistered prediction of unchanged median 0/3 recall is
supported; the material-improvement threshold was not met.

The visible behavioral change was strong: every Q8_0 run concentrated on
Engram, whereas Q4_0 seeds concentrated on RAG, Engram, and Inspector. Q8_0
repeatedly read `project_memory.py` and `concurrency.py`, which contain two
graded defects, but it still did not identify either affected behavior.
The observed Q8_0 block searched elsewhere without improving what the model
concluded in this experiment.

## Paired outcomes

| Seed | Q4 → Q8 focus | Recall | Findings / false positives | Corrected coverage | Turns | Shell calls | Elapsed seconds | Uncertainty |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 17 | RAG → Engram | 0/3 → 0/3 | 1/1 → 1/1 | 1/9 → 1/9 | 24 → 34 | 23 → 33 | 60.1 → 75.2 | low → low |
| 31 | Engram → Engram | 0/3 → 0/3 | 1/1 → 1/1 | 1/9 → 1/9 | 44 → 38 | 43 → 37 | 156.1 → 120.3 | medium → low |
| 47 | Inspector → Engram | 0/3 → 0/3 | 0/0 → 1/1 | 1/9 → 1/9 | 30 → 36 | 29 → 35 | 107.1 → 106.2 | low → medium |

All six runs submitted naturally and none bound the 45-turn cap. Median turns
increased from 30 to 36 and median shell calls from 29 to 35. Median cumulative
input tokens increased from 391,057 to 435,435 and median output tokens from
4,213 to 4,347. Median whole-run elapsed time was effectively unchanged at
107.1 seconds for Q4_0 and 106.2 seconds for Q8_0. These are not controlled
throughput measurements because the trajectories and cumulative prompt volumes
differed.

Median maximum package concentration increased from 44.8% to 59.5%. Both
conditions had median corrected coverage 1/9 and two low-uncertainty reports
below 8/9 coverage.

## Independent adjudication

No Q8_0 report identified redundant batch indexing in
`ProjectMemory.store_episodes_batch`, dead-PID inode replacement in
`WriterLock`, or same-count stale-cache reuse in
`HybridRetriever._get_bm25_index`.

Each Q8_0 report instead asserted one false positive:

1. Seed 17 claimed `delete_episode` continues after trust-policy rejection.
   The method returns `False` before changing memory, JSONL, or ChromaDB.
2. Seed 31 claimed temporal predecessor metadata assignment creates concurrent
   corruption. The persistent instance holds its writer lock, the code first
   copies the metadata dictionary, and the report supplied no failing
   reproducer while admitting the manifestation was unconfirmed.
3. Seed 47 claimed `_load_episodes` drops additional valid rows while repairing
   malformed JSONL. The loader retains every parseable dictionary it can
   normalize and rewrites those accepted rows; no omitted valid row was shown.

Q4_0 aggregate precision was 0/2 and Q8_0 aggregate precision was 0/3. The
additional Q8_0 false positive is a precision regression in count, although
both measured precision values are 0%.

The full normalized scoring record is retained at
`runs/2026-09-07-qwen3-coder-30b-a3b-kv-cache-comparison/independent-adjudication.json`.

## Coverage correction

The unchanged harness records only package-local tests, README files, and
`pyproject.toml` as corroboration. The preregistration also counts relevant
root-level tests or callers whose captured content imports the package or names
the inspected call path. Q8_0 seeds 17 and 47 read Engram production code plus
`/workspace/tests/test_engram_memory_security_policy_probe.py`, so their
recorded 0/9 values are independently corrected to 1/9. Seed 31 already
recorded 1/9 using `engram/tests/test_temporal_memory.py`.

## Boundary and limitations

The comparison held constant the model file, frozen target and archive digest,
prompt, baseline harness, temperature, thinking setting, seeds, turn budget,
tool contracts, sandbox, llama.cpp build, four 262,144-token slots, flash
attention, Jinja, and absence of speculative decoding. The only intended
launch change was Q4_0 to Q8_0 for both K and V caches.

The HTTP endpoint does not expose cache precision, so Q8_0 is established by
the user-reported restart command rather than an endpoint field. The model and
server executable digests remain unavailable. All Q4_0 runs preceded all Q8_0
runs, and changing cache required a restart. The trajectory shift is therefore
compatible with a cache effect but remains confounded with block order and
restart state. It should not be presented as proof that Q8_0 caused the Engram
concentration.

The clean conclusion is narrower: for three matched seeds in this experiment,
Q8_0 changed every transcript but did not improve known-defect recall,
coverage, termination, calibration, precision, or whole-run median latency.

## Durable evidence

The preregistration, pinned Q4_0 control selection, Q8_0 server fingerprint,
three raw Q8_0 reports, complete transcripts, run metadata, independent
adjudication, and SHA-256 manifest are retained under
`docs/projects/repository_assessment/`.

The run configuration does not retain the endpoint URL or credentials. All
three exact transcripts contain the bare endpoint-address string inside source
captured from existing privacy tests, where that string is itself a forbidden
negative-test fixture. This incidental source excerpt is disclosed rather than
silently altering raw evidence.

These remain temporary experiment records and do not implement the deferred
production `repository-assessment/v1` profile.
