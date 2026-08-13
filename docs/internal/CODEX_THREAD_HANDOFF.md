# Fresh Codex thread handoff

- Prepared: 2026-08-12
- Repository: `/home/cybernaif/repos/ai_tools`
- Selected project: RUN-RECORD-00 Phase 4 complete; next slice unselected

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

Review `RUN-RECORD-00-PHASE-4-INSPECTOR.md` and select one bounded capability
before implementing it. Experiment/campaign records are the leading
architectural option. Do not pull UI, RAG, photo, or course fixtures into it.

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

## Working-tree posture

The Phase 0–2, documentation, and license-reconciliation changes were reviewed
and committed during the 2026-08-13 cleanup. Inspect `git status` and preserve
any newer work.

## Verification posture

Phase 4 focused and integration gates pass. The full Inspector suite has one
unrelated environment-sensitive Engram golden mismatch when optional
`tiktoken` is absent; see the Phase 4 report. Invoke root pytest as
`python -m pytest`; the bare
`pytest` console script does not preserve the repository root early enough for
the centralized example-package bootstrap.
