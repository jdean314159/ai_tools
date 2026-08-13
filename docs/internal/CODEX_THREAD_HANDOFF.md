# Fresh Codex thread handoff

- Prepared: 2026-08-12
- Repository: `/home/cybernaif/repos/ai_tools`
- Selected project: RUN-RECORD-00 Phase 6 complete; next slice unselected

## Read order

1. `AGENTS.md`
2. `docs/design/VISION.md`
3. `docs/internal/STATUS.md`
4. `docs/internal/ROADMAP.md`
5. `docs/projects/RUN-RECORD-00-unified-run-artifacts.md`
6. `docs/internal/CLAUDE_THREAD_HANDOFF.md` for the completed NAV campaign
   evidence and closed-direction history

Do not read `SESSION_HANDOFF.md` end to end; it is a historical log.

## First assignment

Review `RUN-RECORD-00-PHASE-6-BUNDLES.md` and select one bounded capability
before implementing it. Course fixtures are viable, but no successor is
selected. Do not pull UI, RAG, or photo producers into it without a concrete
need.

## Critical factual correction

This project is not greenfield. The existing NAV schema-v1 producer is
`agent_lib/src/agent_lib/eval/repo_navigation.py:1672`; its CLI writes
`run-record.json` in `agent_lib/examples/repo_navigation_eval.py:266-277`, and
`agent_lib/examples/nav_counterfactual_finalize.py` consumes the artifact.
ADR-021 and ADR-022 govern the shared semantics and ownership. Phase 2
implemented the dependency-free core envelope plus lossless NAV-v1 and ASC
adapters. Phase 3 added generation recording, cross-kind tests, and a live
Ollama acceptance run. Phase 4 added Inspector library/CLI consumption,
separate generation/agent summaries, and conservative comparisons.
Phase 5 added ASC/NAV experiment adapters, honest checkpoint/final semantics,
separate published child artifacts, and Inspector experiment summaries.
Phase 6 added portable local-directory bundles, exact-byte integrity, confined
resolution, experiment-child packaging, and Inspector bundle loading.

## Working-tree posture

The Phase 0–2, documentation, and license-reconciliation changes were reviewed
and committed during the 2026-08-13 cleanup. Inspect `git status` and preserve
any newer work.

## Verification posture

Phase 4 focused and integration gates pass. The environment-sensitive Engram
golden is now a strict conditional `xfail` when optional `tiktoken` is absent;
see the Phase 4 report. Invoke root pytest as `python -m pytest`; the bare
`pytest` console script does not preserve the repository root early enough for
the centralized example-package bootstrap.
