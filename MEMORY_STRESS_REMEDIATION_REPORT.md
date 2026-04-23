# Memory Stress Remediation Report

This pass targeted the stress-suite failures exposed by the shared `integration_tests/memory_eval.py` harness.

## Code changes

- Broadened `engram_lite` canonical memory handling for decision/preference prefixes, location preferences, region updates, and `prefer ... instead of ...` updates.
- Fixed `engram_lite` auto-ingestion metadata so canonical decision/preference kinds survive scoring instead of being overwritten by a generic auto-ingest marker.
- Added search-term expansion and lightweight token aliasing in `engram_lite` retrieval for pairs like docs/documentation, repo/repository, sandbox/sandboxed, and tool/utility/script.
- Broadened `engram` semantic ingestion with canonical handling for the same update families, plus direct `Preference:` and `Decision:` extraction.
- Added token aliasing to `engram` semantic search so semantically equivalent query wording is less likely to miss durable facts.

## Validation

- `python -m compileall -q engram engram_lite integration_tests language_tutor` passed.
- Targeted memory/regression tests passed for `integration_tests`, `engram_lite/tests/test_memory_quality.py`, `engram/tests/test_ingestion_updates.py`, `engram/tests/test_retrieval_quality.py`, and `language_tutor/tests/test_memory_backend_behavior.py`.

## Shared harness results

### default_memory_quality
- `engram_lite` probe pass rate: `1.0`; failed probes: `[]`
- `engram` probe pass rate: `1.0`; failed probes: `[]`

### stress_memory_quality
- `engram_lite` probe pass rate: `1.0`; failed probes: `[]`
- `engram` probe pass rate: `1.0`; failed probes: `[]`

## Bottom line

Both `engram` and `engram_lite` now pass the shared `default_memory_quality` and `stress_memory_quality` scenarios in the deterministic harness.
