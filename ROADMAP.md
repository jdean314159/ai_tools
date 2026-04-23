# ai_tools — Roadmap

## Purpose of this document

This is the ordered execution plan for the `ai_tools` monorepo.

It is intentionally more practical than `VISION.md` and more forward-looking than `CURRENT_STATE.md`.

Use it to answer:

- what should happen next
- what depends on what
- what “done” means for each phase

---

## Planning assumptions

This roadmap assumes the current project goals remain unchanged:

1. `ai_tools` is a **local-first modular LLM harness**.
2. `ai_tools` is also an **educational and diagnostic environment** for helping users understand LLM behavior.
3. `llm_harness_core` is the interoperability layer that should gradually replace package-local schemas where appropriate.
4. `llm_inspector_ui` is the main user-facing laboratory/workbench for understanding the stack.

---

## Immediate priorities

Before deeper subsystem work, continue maturing the repo as a teaching environment and public GitHub artifact:
- keep `START_HERE.md` and `LEARNING_PATH.md` aligned as the canonical beginner entry path
- propagate beginner/intermediate/advanced/maintainer labels into package docs where useful
- add a root glossary and common-confusions guide to reduce vocabulary friction
- grow notebooks and starter projects from scaffolds into fuller guided exercises
- keep the default teaching order explicit: engines -> inspection -> memory -> RAG -> application -> agents
- keep upgrading `llm_inspector_ui` from a trace viewer into a guided learning workbench
- keep evaluation explicit: baseline -> augmentation -> evaluator -> rationale -> evidence
- keep `scripts/check_publication_hygiene.py` clean before publication snapshots

## Phase 0 — Add harness artifacts and continuity controls

### Goal
Make the repo itself a better harness for agents and humans by standardizing the context and progress artifacts that future work depends on.

### Work

- add a formal repo-level spec for `AGENT.md` files
- add a formal repo-level spec for JSON task/progress manifests
- place root and package-local `AGENT.md` files where they provide real local guidance
- decide which packages need task manifests first:
  - `agent_lib`
  - `engram_lite`
  - `rag_lib`
  - `language_tutor`
- teach the reference workflows and future programming tooling to read these artifacts before acting
- ensure the inspector/UI can eventually display task/progress state and relevant harness artifacts

### Done when

- the repo has one explicit story for agent-facing context artifacts
- future threads and agent runs do not have to rediscover package-local conventions
- task/progress continuity can survive session boundaries without relying on chat context

### Why this comes first
This creates the repo-grounded context layer that the rest of the harness relies on.

---

## Phase 1 — Stabilize the interoperability layer

### Goal
Turn the new interop work from “promising cross-package slice” into a stable suite-wide contract.

### Work

- reconcile `ADR-006` with reality:
  - either mark it Accepted or explicitly document it as “Accepted with ongoing migration”
- review field naming and semantics in `llm_harness_core`
- migrate remaining packages where appropriate:
  - `engram`
  - `language_tutor`
  - `agent_lib`
- document compatibility expectations for shared event/result/message schemas

### Done when

- all core packages either:
  - use shared interop objects directly, or
  - have a documented reason not to
- the team has one authoritative story for cross-package data shapes
- `ADR-006` no longer disagrees with the repo state

### Why this comes first
Without this, future work risks creating a second round of package-local vocabularies.

---

## Phase 2 — Make the workbench fully end-to-end and reliable

### Goal
Ensure `llm_inspector_ui` can demonstrate the full stack in a way that is both reliable and explanatory.

### Work

- validate end-to-end flows:
  - engine selection
  - augmentation
  - model invocation
  - trace capture
  - artifact storage/export
- make `engram_lite` the primary lightweight memory path where appropriate
- test the real `rag` augmenter path in realistic scenarios
- add integration tests spanning:
  - `llm_engines`
  - `engram_lite`
  - `rag_lib`
  - `llm_inspector`
  - `llm_inspector_ui`
- write an operational quickstart for launching and using the workbench

### Done when

- a new user can launch the workbench and successfully inspect:
  - a baseline run
  - a memory-augmented run
  - a RAG retrieval run
- end-to-end integration tests exist and pass
- the UI teaches what is happening, not just that something happened

### Why this comes second
This is the fastest route to making the suite demonstrably useful for both learning and evaluation.

---

## Phase 3 — Complete the observability story

### Goal
Make the hidden transformations of LLM systems legible across the stack.

### Work

- standardize event taxonomies across major subsystems
- enrich trace payloads with more explicit reasons and stage summaries
- make it easy to answer questions such as:
  - what was retrieved
  - what was dropped
  - what memory was injected
  - what actually reached the model
  - where latency accumulated
- improve compare/diff views for prompt/context changes and retrieval/memory differences
- decide what “golden” outputs the observability stack should lock in via tests

### Done when

- the UI can clearly show before/after transformations for major stages
- the inspector can compare not just prompts but major context-construction decisions
- educational clarity improves rather than regresses as the system becomes more capable

### Why this matters
This is the part that most directly serves the project’s educational purpose.

---

## Phase 4 — Bring `engram` and `engram_lite` into a clearer relationship

### Goal
Reduce confusion about which memory package should be used when, and why.

### Work

- define the operational boundary between:
  - `engram_lite` as lightweight/default memory augmentation
  - `engram` as the fuller persistent memory runtime
- align both packages with shared interop and inspector expectations
- update docs and UI language to make the distinction clear
- decide where `engram`-specific capabilities belong in the workbench

### Done when

- users can understand which memory package to choose without reading the code
- both packages emit inspectable behavior in compatible ways
- the workbench can present each package intentionally rather than accidentally

### Why this matters
Right now the memory story is strong but somewhat split between two packages.

---

## Phase 5 — Migrate `language_tutor` into the current architecture

### Goal
Turn `language_tutor` into the canonical reference application for the suite.

### Work

- migrate fully to modern `llm_engines`
- choose and document its memory strategy (`engram_lite`, `engram`, or configurable)
- optionally integrate `rag_lib` for curriculum/explanation retrieval
- expose useful observability hooks for teaching and debugging
- update docs so the app demonstrates the current stack instead of an older one
- keep a reference-app guide and machine-readable stack description aligned with the implementation

### Done when

- `language_tutor` runs cleanly on the current stack
- it demonstrates how the packages are meant to be composed
- it can be used as a teaching example in the future course

### Why this matters
A good reference app prevents the suite from feeling abstract.

---

## Phase 6 — Harden `agent_lib` into a safe, inspectable subsystem

### Goal
Build agent capability without sacrificing safety, composability, or observability.

### Work

- complete the remaining agent/UI integration around the new interop layer
- deepen agent observability so planning/tool/task flow is easy to compare and diagnose
- design and implement real execution isolation
  - filesystem isolation
  - process isolation
  - network policy
  - time/resource limits
- expand how `agent_lib` appears in `llm_inspector_ui`, beyond generic trace tabs

### Done when

- agent execution is not just policy-restricted but architecturally isolated
- agent runs support richer comparison and diagnostics in the UI
- the package is clearly part of the suite, not a side initiative

### Why this matters
This is the highest-risk area technically and operationally.

---

## Phase 7 — Consolidate docs, tests, and release discipline

### Goal
Make the suite easier to resume, easier to trust, and easier to distribute.

### Work

- maintain the root docs:
  - `VISION.md`
  - `CURRENT_STATE.md`
  - `ROADMAP.md`
  - `ADR_INDEX.md`
- add or improve:
  - monorepo smoke tests
  - full wheel build/install checks
  - CI coverage for newer interop paths
  - quickstarts and examples
- decide whether root-level import shims remain temporary or become policy
- create a release checklist for package and monorepo validation

### Done when

- a new thread can resume work with minimal context reconstruction
- packaging confidence is high across the whole monorepo
- release drift is caught by automation instead of manual review

### Why this matters
This is the continuity and productization layer.

---

## Suggested near-term execution order

If only one next step is chosen at a time, the recommended order is:

1. finalize/stabilize the interop core and ADR status
2. run the workbench end-to-end and harden integration tests
3. improve observability/teaching UX in the UI
4. clarify `engram` vs `engram_lite`
5. migrate `language_tutor`
6. design and harden `agent_lib`
7. continue docs/release discipline improvements

---

## Explicit non-goals for the next phase

These are important because they are attractive distractions:

- do not expand `llm_harness_core` into a grab-bag utility package
- do not start large new features in `agent_lib` before sandbox direction is settled
- do not over-abstract the observability layer before the current UI flows are proven
- do not let the workbench become a bag of package-specific adapters again

---

## Harness lifecycle discipline

The harness should be built as a set of removable controls, not a permanently accumulating stack.

### Work

- add kill-switches or configuration toggles for major harness controls where practical
- define ablation checks for controls that may become obsolete as models improve
- periodically test whether evaluator loops, extra tools, or scaffolding are still earning their cost
- prefer modular controls that can be removed without destabilizing the rest of the stack

### Done when

- the team can identify which harness components are load-bearing and which have become overhead
- model upgrades lead to deliberate simplification instead of silent harness bloat

---

## Practical definition of “healthy project state”

The project is in a healthy near-term state when all of the following are true:

- the shared interop layer is stable and documented
- the workbench reliably demonstrates engines, memory, and RAG
- the inspector stack can explain major transformations across those systems
- the reference app uses the current architecture
- agent work proceeds on a real sandboxed foundation
- root docs keep future threads from having to rediscover the architecture


## Update after agent_lib hardening

Process-level command hardening and optional Docker/Podman-backed command isolation are now in place in `agent_lib`. The next safety step is higher-assurance sandboxing beyond containerized host execution, followed by a full monorepo stabilization pass.


## Near-term follow-up

1. Dedicated engram stabilization pass and full suite rerun
2. Release-candidate build/install verification for all packages
3. Higher-assurance execution isolation decision for `agent_lib`
4. Richer comparison workflows in `llm_inspector_ui`


- The shared memory evaluation harness now exists and should keep expanding as the comparison spine between `engram_lite` and `engram`.

- The next memory-eval extension should be real-model answer-uplift runs against configured local/cloud endpoints, followed by larger scenario bundles and action-use probes.


## Near-term memory evaluation follow-up

- add documented model-run recipes for the optional answer-uplift path
- expand the scenario suite with larger corpora and more adversarial paraphrase/decoy/update families
- add action-use probes so memory can be tested for usefulness in tool-driven workflows, not just QA and prompt-support
- use the shared harness to guide targeted fixes in `engram_lite` and `engram` as new probe families expose real weaknesses


- Engram now has update-aware semantic ingestion for common correction/update phrasings, so canonical facts can replace stale formulations during retrieval-focused evaluations.


## Ongoing memory quality work

- Keep prompt hygiene aligned with canonical memory writes so stale `old_value` and raw correction text do not re-enter final prompts.
- Continue tightening episodic relevance so durable but unrelated memories do not crowd out query-specific context.

- keep strengthening beginner-mode explanations in llm_inspector_ui so trace reading stays accessible as more diagnostics are added


- Stabilization follow-up completed: root teaching validator now runs cleanly, and mixed-package pytest collection is supported via shared repo test path configuration plus `agent_lib` test path bootstrapping.
