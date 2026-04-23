# Engram Lite User-Preferred Ingestion Report

## Goal
Bring `engram_lite` closer to `engram`'s memory-formation policy by favoring user-originated inputs for storage and avoiding raw assistant/model outputs unless they are explicit memory artifacts.

## Changes made

### Memory formation policy
- `engram_lite` now defaults to **user-preferred auto-ingestion**.
- Auto-ingestion still exists, but only for roles in `auto_ingest_roles`, which now defaults to `("user",)`.
- Assistant turns are still kept in recent working memory, but are no longer auto-ingested into episodic memory by default.

### Assistant-memory exceptions
- Assistant-originated content may still be stored when it is explicitly tagged as a memory artifact.
- Allowed assistant memory kinds default to:
  - `session_summary`
  - `decision`
  - `preference`
- This check accepts either `kind` or `type` metadata, and also supports an explicit `allow_assistant_memory` override.

### Scoring changes
- Removed the old positive `assistant_summary_signal` bias.
- Generic assistant outputs without an explicit memory kind are now filtered out by the ingestion scorer.

### Visibility / diagnostics
- `get_stats()` now exposes:
  - `auto_ingest_roles`
  - `assistant_memory_kinds`
- Quality counters now include:
  - `assistant_auto_ingest_skipped`
- `engram_lite.interop.describe_memory(...)` now advertises the user-preferred ingestion policy in capability metadata.

### Documentation
Updated:
- `engram_lite/README.md`
- `CURRENT_STATE.md`
- `ROADMAP.md`

## Validation
- `python -m compileall -q engram_lite`
- `pytest -q engram_lite/tests` → 55 passed
- `pytest -q language_tutor/tests/test_memory_backend_behavior.py` → 6 passed

## Behavioral effect
`engram_lite` now behaves more like a lightweight user-memory layer:
- user turns can still be auto-ingested when they look durable and relevant
- assistant turns remain available in recent working context
- assistant summaries/decisions/preferences can still be stored deliberately
- generic assistant chatter is no longer treated as memory by default

## Remaining next step
The next meaningful step is still the evaluation harness comparing:
- old `engram_lite`
- improved `engram_lite`
- full `engram`

That will show whether this policy improves signal quality, reduces redundancy/noise, and improves answer uplift.
