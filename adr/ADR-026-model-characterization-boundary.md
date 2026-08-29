# ADR-026 — Model characterization boundary

**Status:** Accepted  
**Date:** 2026-08-29

## Decision

`llm_engines` owns a small suite of fixed synthetic probes for observable
endpoint behavior. The first suite checks exact chat output, structured JSON,
tool-call construction, and token log probabilities. A capability absent from
the adapter declaration is reported as `not_declared`; endpoint rejection is
`error`; and a completed but incorrect observation is `failed`. This is not
independent endpoint-feature discovery.

The suite is not a benchmark of general model quality. It does not infer
hidden reasoning or internal model processes. Application prompts, memory,
RAG, agent trajectories, and user data are outside this profile and require
separate governed experiments.

Probe execution belongs to `llm_engines`, which already owns inference
contracts and backend adapters. `llm_inspector` remains inference-free: it
recognizes, summarizes, and compares the resulting artifact profile.
`llm_harness_core` supplies the generic durable experiment envelope.

The default report and artifact retain:

- declared capabilities;
- backend and reported model labels;
- pass, fail, not-declared, or error status per probe; and
- bounded scalar observations such as token counts and latency.

They omit raw prompts, model responses, endpoint URLs, API keys, and exception
messages. The prompts are fixed synthetic inputs, and the report is safe to
share subject to the sensitivity of the model label itself.

The experiment profiles are version 2. Version 1 was withdrawn during review:
it called adapter declarations endpoint support, forced thinking off, and
retained host-specific model paths. Version 2 records the tri-state thinking
request, uses `not_declared`, expands output budgets when thinking might be
active, and retains only the model-label basename.

The single-run profile is `llm_engines.model_characterization`.
Its result is best-effort even at temperature zero because inference servers,
hardware, templates, and model builds can vary. Repeated-run stability uses
the separate `llm_engines.model_characterization_campaign` version-2 profile.
It records per-probe status counts, pass rates, status stability, and
minimum/median/maximum observed chat latency. These descriptive values are not
confidence intervals. Context limits, concurrency, memory, and RAG remain
future profiles rather than implied properties of either report.

## Acceptance observations

- A deterministic fake engine exercises all four supported probes.
- Adapter capabilities not declared remain distinct from observed failures and
  endpoint errors.
- Probe exceptions retain only their public exception type.
- The report contains no raw synthetic prompt or response content.
- The artifact round-trips through the shared envelope parser.
- Inspector recognizes and summarizes per-probe outcomes.
- A live Qwen 3.8 27B endpoint served by llama.cpp on the DGX Spark passed all
  four probes on 2026-08-29. The exact version-2 artifact and limitations are
  recorded in `docs/projects/llm_engines/SPARK-QWEN-CHARACTERIZATION-2026-08-29.md`.
- Repeated campaigns preserve each bounded run and compute descriptive status
  and latency summaries without retaining raw content.
