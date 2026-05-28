# Next Thread Handoff — ai_tools

Last updated: 2026-05-27

## Read these first

1. `docs/internal/STATUS.md` — current repo state (single source of truth).
2. This file — what to do next and why.

## Where we are

Foundation phase is complete: all seven packages have a defined public API,
two reference examples exist (`examples/language_tutor`,
`examples/agent_coordination_teaching`), and design guidance for deferred work
is captured (`AGENT_BUILD_NOTES.md`, `INFERENCE_OPTIMIZATION.md`, ADR-011).

A critic-mode review concluded the project is sound in direction but documents
more than it builds, and that the bounded-session workflow structurally biases
work toward session-sized tasks (cleanup, API defs, single examples, notes) and
away from the sustained, multi-session integration that would most validate the
toolkit. The agreed corrective: **drive real, demanding projects through
ai_tools and let the friction reshape the libraries.**

## Immediate objective: start the first project campaign

Pick one real project and build it *through* ai_tools as a demanding external
consumer. Recommended first: **NetFlow analysis** (quadratic-complexity security
analysis over connection data — the user's dissertation domain). It exercises
the most-deferred capabilities: the RLM pattern in `rag_lib`, large-context
handling, `engram` for cross-pass state, and `llm_engines` cache behavior on the
local 3090. Alternatives: photo organization (batch/scale), mystery-novel tool
(multi-agent — natural trigger for the future agent repo).

**Working method for the campaign:**

- Treat it as a multi-session campaign with its own continuity. At project
  start, create `docs/projects/<name>/CAMPAIGN.md` to hold the running state
  (goal, current step, decisions, open gaps) so the work survives across threads
  and tools — the same externalized-memory pattern the rest of the repo uses.
- Build using only public APIs. When the API forces a private reach or is
  missing something, that gap is a justified library change (the established
  `.text` / llamacpp-factory pattern). Surface the gap, fix the public surface,
  record it in the campaign's API_CHANGES section.
- Real-model validation matters here in a way stubs cannot provide. Run against
  local Ollama (or llama.cpp) on the 3090, not just deterministic stubs.
- Apply deferred design guidance only when the project actually demands it.
  `INFERENCE_OPTIMIZATION.md` (RLM, cache) and `AGENT_BUILD_NOTES.md` (agents)
  are the briefs; consult when triggered, don't build ahead of need.

## Carry-over to verify before starting

- Three `session_id` one-liners in the examples applied (tutor `_generate`,
  coordination `planner.py`, `workers.py`).
- `examples/language_tutor_slice/` removed (redundant after full tutor adoption).
- `make test-core` green; example test suites pass.

## Validation

    make install && make test-core
    # plus, for the chosen project, real-model runs on local hardware

## Open decisions (not blocking)

- Which project runs first (recommend NetFlow).
- Whether to begin dogfooding `engram` as the continuity/memory substrate for
  the project campaigns themselves (indexing STATUS/ADR/campaign docs so a fresh
  thread retrieves relevant prior decisions instead of re-reading everything).
  Real use of the toolkit and a hard test of it at once.
