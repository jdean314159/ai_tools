# Repo Status

Last updated: 2026-05-27

Single source of truth for the current `ai_tools` repo state. Use this file
first when starting a new thread or resuming work after a handoff.

## Current posture

**Phase: foundation complete; entering project-driven refinement.**

The public-API pass (MEMBERSHIP step 3) is complete for all seven packages
(`__all__` + scope/quickstart README each). Two reference examples exist in
`examples/`. The next phase is to drive real, demanding projects *through*
ai_tools and let the friction reshape the libraries — closing the co-evolution
loop rather than adding more speculative design surface. See
NEXT_THREAD_HANDOFF.md.

Foundation state:

- `engram/` is the standalone memory library (formerly engram_lite). Heavy
  engram archived at github.com/jdean314159/engram. `engram_ui` deleted
  (ADR-010). No package is broken.
- All seven packages have a defined public surface. `engram` trimmed to
  `ProjectMemory` + core types; `agent_lib` trimmed to coordination primitives
  with a loud EXPERIMENTAL notice.
- `llm_engines` gained, justified by real consumers this phase: a `.text`
  convenience on `GenerationResponse`; a `CacheStats` type; a `session_id`
  prefix-cache hint on `GenerationRequest`; and a llama.cpp factory routing fix
  (`get_engine("llamacpp", ...)` now works via the public surface).
- `examples/language_tutor` — full tutor (adopted from a Codex draft, refined:
  StructuredOutputHandler, merged per-turn analysis, session_id). Tests pass.
- `examples/agent_coordination_teaching` — `agent_lib` coordination teaching
  example (adopted from a Codex draft, refined: public-import fix, structured
  output, isolation notes per ADR-011, public-API audit test, session_id).
  Tests pass. Explicitly NOT the worker/mentor ASC.

Design guidance captured (deferred work, not built): `AGENT_BUILD_NOTES.md`
(worker/mentor pattern, roles, context-rot reduction, §8 future dedicated agent
repo), `INFERENCE_OPTIMIZATION.md` (RLM pattern, KV-cache layer, §3a RAM/NVMe
tiering, §6 multi-agent implications), `ADR-011` (agent execution isolation,
Proposed).

Course materials will move to a separate repo (decided). Documentation serves
as the project's externalized memory across bounded AI sessions and tools.

## Package layout

Packages on `src/` layout:

    agent_lib/src/agent_lib
    engram/src/engram              ← renamed from engram_lite
    language_tutor/src/language_tutor
    llm_harness_core/src/llm_harness_core
    llm_inspector/src/llm_inspector
    llm_inspector_ui/src/llm_inspector_ui
    rag_lib/src/rag_lib

One package intentionally remains on direct layout:

    llm_engines/llm_engines

## Installation tiers

    make install        # lightweight default, no torch/CUDA required
    make install-ml     # PyTorch-backed neural/local-model extras
    make install-gpu    # CUDA PyTorch + llama.cpp CUDA build path
    make test-core      # default test suite
    make test-ml        # torch-dependent tests

## Validation commands

    make install && make test-core
    python scripts/check_publication_hygiene.py
    python scripts/check_teaching_artifacts.py

    # Verify engram resolves to the standalone
    .venv/bin/python -c "import engram; print(engram.__file__)"
    # Expected: <repo>/engram/src/engram/__init__.py

## Active work — the project-driven refinement phase

The foundation is built. The validated next move (per the critique recorded in
the design discussion) is to **run real, demanding projects through ai_tools as
a hard external consumer**, and let each project's friction reshape the
libraries. This closes the co-evolution loop that documentation and examples
alone leave open. Each project is treated as a multi-session campaign with its
own continuity, so the work survives bounded sessions rather than losing to
session-sized tasks.

Candidate projects (each stress-tests a different part of the stack):

1. **NetFlow analysis (recommended first).** Quadratic-complexity security
   analysis over connection data — your dissertation domain. Stresses: RLM
   pattern (`rag_lib`), large-context handling, `engram` for cross-pass state,
   `llm_engines` cache behavior, local-first inference on the 3090. The
   strongest loop-closer because it exercises the most-deferred capabilities.
2. **Photo organization (90k+ collection).** Stresses: batch pipelines,
   non-LLM tooling integration, `engram` for identity/cluster memory at scale.
3. **Mystery-novel development tool.** Stresses: multi-agent coordination
   (Brainstormer/Writer/Critic/Continuity), `agent_lib`, long-form `engram`
   memory — the natural trigger for the future agent orchestration repo.

The discipline for each: build the project as a real consumer using only public
APIs; when the API forces a private reach or is missing something, that gap is a
justified `llm_engines`/`engram`/`rag_lib` change (the `.text` / llamacpp-factory
pattern); record gaps in the project's API_CHANGES record.

## Carry-over items to verify in a fresh thread

- The three `session_id` one-liners in the examples (tutor `_generate`,
  coordination `planner.py` and `workers.py`) — confirm applied.
- `examples/language_tutor_slice/` — the minimal acceptance slice. Now redundant
  given the full tutor was adopted. Remove if not already removed.
- `make test-core` green; both example test suites pass locally against the stub
  and, ideally, once against a real Ollama model.

## Notes for next session

- Work from `~/ai_tools`, confirm `git status --short --branch` shows `main`.
- No package is broken; `make test-core` should be green.
- Decision rule for any library growth: build a capability when a concrete
  project run fails without it, not when a design discussion suggests it.
- Design guidance for deferred work lives in `docs/design/AGENT_BUILD_NOTES.md`
  and `docs/design/INFERENCE_OPTIMIZATION.md`; consult before building anything
  in those areas.
