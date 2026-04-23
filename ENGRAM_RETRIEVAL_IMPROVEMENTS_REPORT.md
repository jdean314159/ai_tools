# Engram Retrieval Improvements Report

## What changed

- Added update-aware semantic ingestion for common correction/update phrasings.
- Canonicalized stored fact text so stale superseded values are omitted from the stored memory content.
- Added topic-stable fact ids for those update-derived facts so future updates can overwrite the same semantic slot cleanly.
- Added targeted tests for canonical correction ingestion and schedule-update ingestion.
- Extended the shared memory-eval regression tests so `engram` must now pass the harder decoy and update probes.

## Current effect on the shared harness

- **engram_lite**: decoy rejection=0.0, update resolution=0.0, failed probes=decision_decoy, update_resolution
- **engram**: decoy rejection=1.0, update resolution=1.0, failed probes=none