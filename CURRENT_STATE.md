# ai_tools — Current State

## Purpose of this document

Use this file as the **implementation snapshot** for the `ai_tools` monorepo.

- `VISION.md` is the architectural intent and long-term design baseline.
- `CURRENT_STATE.md` is the practical answer to: **what is implemented now, what is partial, and what still needs to be done?**
- `ROADMAP.md` is the ordered execution plan.
- `ADR_INDEX.md` is the map of key architectural decisions.

When starting a new thread, treat `VISION.md` as the canonical design target and `CURRENT_STATE.md` as the canonical implementation snapshot.

---

## Snapshot summary

As of the latest reviewed repo state:

- The monorepo has been cleaned up significantly from earlier release-hygiene problems.
- A shared interoperability layer now exists as `llm_harness_core`.
- The observability path is materially improved:
  - `engram_lite` emits shared interop objects.
  - `llm_inspector` consumes and exports shared interop objects.
  - `llm_inspector_ui` renders shared traces and shared capability descriptors.
  - `rag_lib` now exposes inspectable retrieval-stage behavior instead of acting only as a hidden backend.
- `VISION.md` now exists at the repo root and should be treated as the architecture/handoff reference.
- A first-pass teaching spine now exists via `START_HERE.md`, `LEARNING_PATH.md`, `course/notebooks/`, and `course/starter_projects/`.

The codebase is now better described as:

> a modular, local-first LLM harness and educational/diagnostic environment,
> with a partially implemented shared interop layer and a substantially improved
> observability stack.

---

## Cross-cutting status

### 1. Repo hygiene and packaging

Improved in recent work:

- Release-blocking syntax problems were corrected.
- Checked-in build debris and patch leftovers were removed from the working snapshot used for the updated archives.
- CI coverage was expanded to include compile checks and more package coverage.
- Several monorepo import-shadowing issues were mitigated with lightweight root-level import shims.

Still true / still worth watching:

- The monorepo still mixes production packages, reference apps, and design documents in one tree.
- Root-level import shims are a developer-experience aid, not an ideal final packaging story.
- A full fresh wheel-build/install validation was not re-run after the most recent `rag_lib` observability work.

### Teaching layer

Implemented in first-pass form:

- root-level `START_HERE.md` defining the beginner-safe entry ramp
- root-level `LEARNING_PATH.md` defining the intended learning order
- `course/notebooks/` with ordered concept/walkthrough notebooks
- `course/starter_projects/` with runnable starter scaffolds
- existing focused labs under `docs/tutorials/`
- canonical evaluation walkthrough via `llm_harness_core/EVALUATION_WALKTHROUGH.md`, `course/notebooks/07_evaluating_llm_applications.ipynb`, and starter-project evaluation scaffolds

Known remaining work:

- deepen the notebooks from conceptual scaffolds into fuller guided exercises
- make `language_tutor` the clearest end-to-end reference app for the course path
- strengthen `llm_inspector_ui` explanatory text so the workbench teaches, not just displays
- continue turning workbench guidance into concrete guided compare/evaluate flows
- deepen the new evaluation walkthrough into fuller scored exercises and exported example reports

Assessment:

The repo now has a visible course structure, but the teaching assets are still introductory scaffolds rather than a mature full curriculum.

---

### 2. Interoperability layer

Implemented:

- New package: `llm_harness_core`
- Shared schemas now exist for:
  - capability descriptors
  - messages and tool invocations
  - retrieved documents and memory records
  - operation results/errors/warnings
  - trace events

Packages already adapted to the interop layer:

- `llm_engines`
- `engram_lite`
- `llm_inspector`
- `llm_inspector_ui`
- `rag_lib`

Packages not yet fully adapted:

- `engram`
- `language_tutor`
- `agent_lib`

Important nuance:

- `ADR-006` now reflects reality better: the interop core is accepted and already implemented across multiple packages, though migration is still incomplete.

### 3. Observability / educational value

This is no longer just an application-support stack.

The suite is increasingly aligned with the intended goal of helping users **understand and better utilize LLMs**, not merely build on top of them.

Working today:

- engine capability inspection
- prompt/memory trace normalization
- comparison and diff support in the inspector stack
- shared trace events across major packages
- RAG retrieval-stage diagnostics in the UI path

Still incomplete:

- improved teaching-oriented explanations in `llm_inspector_ui` compare/startup surfaces
- end-to-end, polished explanation flows across all packages
- agent observability
- explicit before/after views for every major transformation stage
- a unified pedagogical quickstart across the stack
- learner-level labels propagated more broadly through package docs

---

## Harness artifact status

### State
Partially in place.

### What exists

- canonical root continuity documents:
  - `VISION.md`
  - `CURRENT_STATE.md`
  - `ROADMAP.md`
  - `ADR_INDEX.md`
- a clearer shared interop layer and observability direction
- stronger agent/runtime policy surfaces than earlier snapshots

### Newly specified

- `AGENT_FILE_SPEC.md` for repo-local and package-local `AGENT.md` files
- `TASK_MANIFEST_SPEC.md` for JSON task/progress manifests

### What is still needed

- actual `AGENT.md` placement in the packages that benefit most
- first real task manifests for long-running agent-driven work
- UI/inspector support for showing harness artifacts and progress state

### Assessment
The repo now has an explicit continuity/documentation core, but the next step is to turn that from documentation policy into working harness artifacts used by tools and agents.

---

## Package-by-package status

## `llm_harness_core`

### State
Implemented and now central to the stack.

### What exists

- shared schemas for interoperability
- a dependency-light core package intended to sit below the rest of the ecosystem
- public API tests

### What is still needed

- stabilize field naming and lifecycle expectations across all downstream users
- formally accept and lock the ADR once the remaining package migrations are complete
- decide versioning/compatibility policy for the shared schema layer

### Assessment
This is the right architectural move and should remain intentionally small.

---

## `llm_engines`

### State
Strong foundational package; partially migrated into the shared harness vocabulary.

### What exists

- backend abstraction across local and cloud engines
- shared interop conversion helpers
- compatibility shim for the old contracts module
- improved packaging/CI state relative to earlier snapshots

### Known remaining work

- add a first-class `get_default_registry()` or equivalent public entry point so other packages stop relying on workarounds/bootstrapping helpers
- verify streaming/tool-calling paths end to end through the workbench
- continue reducing legacy compatibility surface once downstream packages are updated

### Assessment
This is one of the most mature packages in the repo.

---

## `engram_lite`

### State
Implemented as a real package, integrated into the shared interop layer, and now the default lightweight memory path for the workbench/teaching spine.

### What exists

- `ProjectMemory`
- prompt-building / augmentation contracts
- persistence tests and compatibility tests
- interop conversions to shared results, memory records, and capability descriptors

### Known remaining work

- clarify the intended boundary between `engram_lite` and full `engram` in user-facing docs and examples
- expand the educational/inspection story so users can more clearly see what memory was used and why
- keep the lightweight augmenter path covered by cross-package smoke tests as inspector contracts evolve

### Assessment
This has moved beyond “placeholder extraction target” and should now be treated as a real package with a defined role.

---

## `engram`

### State
Powerful and feature-rich, but not yet fully brought into the new interop/observability architecture.

### What exists

- multi-layer memory runtime
- daemon/event bus architecture
- broader memory capabilities than `engram_lite`
- large test surface
- existing docs and examples

### Known remaining work

- adapt more of its outputs to `llm_harness_core`
- align its inspection model more directly with the newer shared event vocabulary
- decide how it should coexist with `engram_lite` operationally in the workbench and reference apps
- revisit any older assumptions in docs that predate the interop-core work

### Assessment
Architecturally important, but currently somewhat ahead of the rest of the stack in complexity and behind it in shared-schema alignment.

---

## `rag_lib`

### State
Substantially improved and now on the observability path.

### What exists

- inspectable retrieval pipeline support
- retrieval-stage trace emission
- shared retrieved-document conversions
- a real UI path for RAG retrieval inspection
- targeted tests for retrieval interop and UI rendering

### What was recently added

- `RetrievalTrace`
- interop helpers
- stage-level diagnostics for retrieval, reranking, and prompt assembly
- `RagAugmenter` path in `llm_inspector_ui`

### Known remaining work

- confirm the long-term adapter boundary between `rag_lib` and `llm_inspector`
- expand stage explanations so users can clearly understand why documents were selected, reordered, or dropped
- consider how to present retrieval quality, score thresholds, and failure modes in more educational terms
- revisit packaging/build validation after the latest changes

### Assessment
This package now fits the stated project goal much better than before, because retrieval is becoming inspectable rather than hidden.

---

## `llm_inspector`

### State
Core observability package is in good shape and now meaningfully aligned with the interop layer.

### What exists

- normalized trace model
- compare/diff/export flow
- interop conversions to shared messages, memory records, and operation results
- backward-compatible handling of older event shapes

### Known remaining work

- reduce duplication between older internal representations and shared interop objects over time
- strengthen adapters for all augmentation sources, not just memory-focused paths
- continue improving golden tests for new interop-backed traces

### Assessment
This package is now the anchor for cross-package observability and should stay schema-driven rather than package-specific.

---

## `llm_inspector_ui`

### State
Much improved; now genuinely closer to the intended workbench/laboratory role.

### What exists

- shared capability rendering
- shared trace rendering
- compatibility handling for old/new event shapes
- real `rag` augmenter path
- retrieval diagnostics tabs in single-run and compare flows

### Known remaining work

- run and validate more true end-to-end scenarios from engine selection through augmentation, model call, inspection, and artifact persistence
- improve the UX language so the UI teaches users what they are seeing rather than only dumping diagnostics
- document the happy path for launching and using the workbench
- keep baseline, `engram_lite`, full `engram`, and RAG augmenter behavior aligned through `integration_tests/test_augmenter_spine.py`

### Assessment
This is increasingly the central user-facing “laboratory” for the suite.

---

## `language_tutor`

### State
Reference app with real value, but still behind the current architecture.

### What exists

- a functioning domain application
- release-hardening improvements from recent cleanup work
- tests for memory behavior and integration
- a dedicated `REFERENCE_APP_GUIDE.md` for the teaching path
- a machine-readable reference-stack endpoint for docs/workbench alignment

### Known remaining work

- migrate fully onto the modern `llm_engines` path
- decide whether its memory path should be `engram`, `engram_lite`, or a configurable choice
- integrate the newer observability layer in a user-meaningful way
- continue aligning documentation with the current suite rather than older engine assumptions
- extend the current reference-stack description into richer tutor-specific inspector/workbench views

### Assessment
Now clearly teachable as the Stage 5 composed application, but still short of the final fully instrumented reference-app target.

---

## `agent_lib`

### State
Partially aligned with the intended architecture.

### What exists

- tests and initial runtime/policy structure
- direction toward coordinator-based agent orchestration
- shared interop helpers for agent runtimes, tool runtimes, runs, and step events
- shared trace emission for agent planning, tool invocation, tool results, memory attachment, and workspace-policy visibility
- basic agent-diagnostics rendering in `llm_inspector_ui`

### Key unresolved issue

The most important architectural omission remains **real execution isolation**.

Current state:

- path and command policy controls exist
- a true OS/container sandbox does not yet exist
- network/process/filesystem isolation is not yet first-class

### Known remaining work

- harden sandboxing / isolation as an actual architectural feature, not just a policy wrapper
- decide how agent execution should be launched and inspected from first-class UI flows
- deepen agent observability beyond step traces into run comparison, latency, and failure-analysis views
- connect the package cleanly to the rest of the harness instead of treating it as a semi-separate initiative

### Assessment
Now materially aligned with the shared observability direction, but still pre-stabilization because isolation remains incomplete.

---

## What is definitely true now

These points should be treated as reliable when resuming work:

1. `VISION.md` is the canonical architecture/handoff document.
2. The suite is intended both as:
   - a composable LLM harness, and
   - an educational/diagnostic environment for understanding LLM behavior.
3. `llm_harness_core` now exists and is the beginning of the shared interoperability layer.
4. The foundational observability path is now real across:
   - `engram_lite`
   - `llm_inspector`
   - `llm_inspector_ui`
   - `rag_lib`
5. `rag_lib` is no longer only a backend; it now participates in inspectable retrieval diagnostics.
6. `agent_lib` now has interop alignment and baseline observability, but it still needs real sandbox design and execution hardening.

---

## What should be clarified next if context is lost

If a future thread gets confused, re-anchor on these questions in order:

1. What is the current intended role of the package under discussion?
2. Has that package already been migrated to `llm_harness_core`?
3. Is the task about implementation, observability, or educational UX?
4. Is the current blocker architectural, packaging-related, or test/validation-related?
5. Does `VISION.md` still reflect the intended long-term design, or has the design changed?

---

## Recommended next-document usage

- Read `VISION.md` first for architectural intent.
- Read `CURRENT_STATE.md` second for what is already implemented.
- Read `ROADMAP.md` third to choose the next execution step.
- Read `ADR_INDEX.md` fourth to avoid re-litigating settled design decisions.


## Recent update: agent_lib sandbox hardening

- `ProgrammingToolRuntime` now executes `run_command` through a hardened path instead of delegating blindly to an inner tool.
- Command execution now enforces workspace policy timeout settings, scrubs environment variables by default, caps captured output size, and isolates the child process group on POSIX so timeout cleanup reaches spawned subprocesses.
- `WorkspacePolicy` now includes command-execution controls such as `command_timeout_seconds`, `max_command_output_chars`, `inherit_environment`, `allowed_environment_keys`, and `denied_environment_keys`.
- A root-level `engram/__init__.py` monorepo shim was added so root-checkout test runs can import `engram` reliably.
- Optional external command isolation is now available through Docker or Podman, with networking disabled by default and explicit metadata about requested backend, actual backend, image, and fallback behavior.
- Remaining gap: this is not yet a complete kernel- or VM-level sandbox, and broader UI surfacing of blocked/degraded runs still needs work.


## Monorepo stabilization status

The post-interop stabilization pass has corrected repo-root import shim issues, refreshed inspector golden traces for the shared interop format, fixed a `language_tutor` release-hardening regression, and updated one stale `engram` architecture test to reflect the current default SQLite semantic backend. Most package-level suites now pass again from a repo-root checkout. A dedicated full `engram` suite rerun is still pending.

- `engram_lite` now has lightweight memory hygiene plus basic canonical update handling: lightweight ingestion/importance scoring, store-time deduplication, scored internal episodic retrieval, user-preferred auto-ingestion, and topic-aware canonicalization for simple correction/update statements. It now skips raw assistant turns for auto-ingest unless assistant content is explicitly stored as a summary/decision/preference artifact.

- Cross-backend memory evaluation now lives under `integration_tests/memory_eval.py` and supports both single-scenario runs and a default multi-scenario suite. It compares `engram_lite` and `engram` on durable-signal retention, paraphrase recall, decoy rejection, update resolution, noise rejection, redundancy, prompt-support, and optional answer-uplift when a real model is configured.


## Memory evaluation harness status

The shared `integration_tests/memory_eval.py` harness now has two levels: a seeded default scenario and a denser stress scenario with more adversarial decoys and updates. It can also run optional answer-uplift checks against an OpenAI-compatible model endpoint via environment configuration. The deterministic suite currently passes for both backends on the seeded and stress scenarios, while the real-model path is available but only runs when a model endpoint is configured.


- Engram now has update-aware semantic ingestion for common correction/update phrasings, so canonical facts can replace stale formulations during retrieval-focused evaluations.


## Engram prompt hygiene

- `engram` now renders semantic memory into prompts using canonical content only, instead of verbose metadata dumps.
- Episodic correction/update texts are canonicalized for prompt injection so superseded values do not leak back into the model context.
- Transient-note style turns are filtered more aggressively and no longer become durable semantic memory by default.


## Publication/readability status

- the teaching spine is now explicit through `LEARNING_PATH.md`, notebooks, starter projects, the reference-app guide, the workbench guide, and the evaluation walkthrough
- package READMEs are being aligned to that teaching spine so GitHub readers do not have to infer the intended order
- public-release hygiene now has an explicit checklist and a publication-hygiene validation script
- `integration_tests/test_augmenter_spine.py` now verifies the repo-level augmentation path across baseline, `engram_lite`, RAG, and optional full `engram`

- llm_inspector_ui now includes beginner-mode explanations in Compare and Startup so the workbench can teach prompt/evidence/retrieval interpretation in plain language


- Publication stabilization: `scripts/check_teaching_artifacts.py` now completes end-to-end in the repo environment, repo-level pytest import resolution was hardened for mixed-package teaching/reference test runs, and the optional full-Engram augmenter smoke test is gated behind `AI_TOOLS_TEST_FULL_ENGRAM=1`.
