# AI Tools Vision Document

**Status:** Working architecture reference  
**Canonical location:** `docs/design/VISION.md`
**Purpose:** Canonical continuity document for future development, new threads, and architectural alignment.

---

## 1. Executive Summary

`ai_tools` is a modular Python suite intended to help people **understand, inspect, and better utilize LLMs**, especially local LLMs, while also providing reusable components for building LLM-based systems.

The suite is not meant to be only an application framework. It is also meant to be a **laboratory and observability environment** for:

- comparing LLM backends and model behaviors
- understanding memory augmentation and its effects
- inspecting RAG retrieval quality and failure modes
- visualizing context assembly and evidence flow
- eventually understanding agent planning, tool use, and constraints

The design goal is therefore **dual-purpose**:

1. **Composable harness** for building LLM-enabled applications.
2. **Educational and diagnostic environment** for making LLM behavior visible.

The correct mental model is:

> `ai_tools` is a modular LLM harness plus an inspection layer.

---

## 2. Core Design Intent

The suite exists to answer questions such as:

- Which model/backend should I use for this task?
- What did memory contribute to this prompt?
- What did RAG retrieve, and why?
- Which context actually reached the model?
- Where is latency accumulating?
- What changed the final answer most?
- How do engines, memory, retrieval, and agents interact in practice?

This means the system must emphasize:

- clean modularity
- explicit interoperability
- inspectable behavior
- stable contracts
- standalone package usability
- composable multi-package workflows

The system should avoid becoming a pile of loosely related utilities with hidden coupling.

---

## 2A. Harness Engineering Implications

The current architecture should be understood as a **harness engineering** stack, not just a library bundle.

In this repo, a *harness* means the combination of:

- context artifacts that tell models and agents where they are and what matters
- execution constraints and policies that keep automation within acceptable bounds
- feedback loops that detect failure, drift, and low-quality output
- inspection surfaces that let humans understand what happened

### Principles the suite should follow

1. **Context beats abstract instruction.**
   The stack should prefer repo-grounded context, current state, concrete file paths, and explicit constraints over large generic prompts.

2. **Planning and execution should be separable.**
   Agents should be able to propose work, expose intended verification, and then execute in a later step.

3. **Feedback loops are non-negotiable.**
   Computational checks, evaluator-style reviews, and observable traces should catch failure before results are trusted.

4. **Incremental progress is safer than broad autonomous changes.**
   The preferred workflow is one coherent task or feature at a time, with explicit verification and updated progress tracking.

5. **The codebase is the agent’s source of truth.**
   Architectural intent, local conventions, and current work state should live in versioned repo artifacts, not only in prompts or chat history.

6. **Build to delete.**
   Every harness control should be modular, measurable, and removable if later model generations make it unnecessary.

### First-class harness artifacts

The repo should treat the following as first-class engineering artifacts:

- continuity documents:
  - `docs/design/VISION.md`
  - `docs/internal/STATUS.md`
  - `docs/internal/ROADMAP.md`
  - `docs/internal/CLAUDE_THREAD_HANDOFF.md`
  - `ADR_INDEX.md`
- repo-local and package-local `AGENT.md` files
- JSON task/progress manifests that agents and humans can both read
- append-only or otherwise durable trace/event logs where long-running agent work requires recovery or auditability

### Consequence for package design

Packages should not only expose runtime functionality. They should also expose the *artifacts and signals* needed for harness operation:

- capability descriptors
- explicit constraints and policy surfaces
- observable stage boundaries
- result and error envelopes
- progress and verification hooks

This is part of what makes `ai_tools` both a harness and a laboratory.

---


## 2B. Packaging and Dependency Policy

The default repo path must remain lightweight and reproducible:

- `make install` creates and uses a project-local `.venv`.
- default install and `make test-core` should not require PyTorch or CUDA.
- heavyweight local ML features live behind explicit extras/targets such as
  `make install-gpu` and `make test-ml`.
- package `dev` extras should mean development/test tooling, not every runtime
  backend.
- unpublished sibling packages should be installed by the root `Makefile`, not
  pulled from PyPI through package extras.
- full Engram uses `engram/src/engram` as its canonical import path; old
  top-level package trees must not be restored.

This policy keeps the suite usable as a teaching/workbench repo while still
supporting advanced neural, HuggingFace, and GPU workflows explicitly.

## 3. Package-Level Responsibilities

### 3.1 `llm_engines`

**Responsibility:** Backend and model abstraction layer.

This package provides a stable interface over local and remote LLM engines. It should isolate backend-specific behavior so callers can reason in terms of common model operations rather than engine quirks.

Typical responsibilities:

- chat/completion execution
- model/provider abstraction
- capability discovery
- response normalization
- engine configuration
- fallback/failover behavior
- backend diagnostics

`llm_engines` is foundational. Other packages should depend on it rather than re-creating model abstractions.

---

### 3.2 `engram`

**Responsibility:** Standalone lightweight project memory for LLM applications.

`engram` is a single, self-contained implementation — there is no facade layer.
It exposes a minimal public API: `ProjectMemory` plus core types (`ProjectType`,
`TokenBudget`, the augmenter contracts), the additive `MemoryLayer` extension
contract and payloads, and interop helpers. `engram.__all__` also includes
telemetry types (`Telemetry`, `TelemetryEvent`) and embedding entry points
(`OllamaEmbedder`, `EmbeddingService`) as part of the public surface. Internal
storage and semantic implementation layers remain private.

Typical responsibilities:

- storing recent/project memory (via `engram.ProjectMemory`)
- retrieving relevant prior context
- assembling memory-augmented prompts
- emitting inspectable memory traces
- exposing evidence used for augmentation

By default it is lightweight: JSONL source-of-truth, required ChromaDB for the
episodic memory store, RRF hybrid retrieval, and no torch dependency. See
ADR-009 for the freeze/rename decision (supersedes the earlier facade design in
ADR-007).

---

### 3.3 Archived: heavy `engram` runtime

**Status:** Archived out of the monorepo (ADR-009); read-only at
github.com/jdean314159/engram.

The original full memory runtime — integrated RTRL neural layer, multi-tier
persistence, advanced retrieval policies, lifecycle management, and procedural
memory — was frozen and archived. The standalone `engram` in §3.2 remains the
supported memory path.

The recovered RTRL/TITANS algorithm, neural-memory wrapper, and surprise filter
exist as opt-in primitives under `engram.neural`. The `NeuralMemoryLayer`
adapter integrates paired-turn learning, telemetry, and persistence through the
additive `MemoryLayer` boundary. Neural recall affinity is disabled after evaluation
showed material recall loss. The adapter uses NumPy by default and is registered
by `ProjectMemory` only when explicitly enabled with an embedder. Its
embedding-reconstruction value dimension is 32 after the 64-dimensional
configuration overflowed at full evaluation volume; non-finite state fails
closed.

NEURAL-07 further isolated neural output after threshold, advisory-content, and
candidate-utility experiments failed their recall gates. Prompt hints and
surprise-based episode-importance changes are separately default-off research
controls; an enabled layer can collect telemetry without affecting recall. This
does not restore the archived heavy runtime: the neural layer cannot
replace core retrieval candidates, logprob-based surprise gating remains
unwired, and default-on status requires a separate corpus evaluation.

Typical responsibilities:

- richer memory levels / storage policies
- broader project memory management
- advanced retrieval / promotion / lifecycle behaviors
- canonical implementation of all shared primitive types
- more experimental or sophisticated memory features (RTRL, procedural)

`engram` should remain compatible with the same interop and observability model used elsewhere.

---

### 3.4 `llm_inspector`

**Responsibility:** Observability and analysis layer for LLM workflows.

This package should provide normalized inspection objects and helpers for understanding behavior across the suite.

Typical responsibilities:

- trace collection and normalization
- evidence/context inspection
- comparison and reporting helpers
- adapters that expose package behavior in inspectable form

`llm_inspector` is the bridge between raw subsystem behavior and human-readable analysis.

---

### 3.5 `llm_inspector_ui`

**Responsibility:** Interactive UI for selecting, comparing, and inspecting LLM system behavior.

This package is the main educational and operational interface for humans.

Typical responsibilities:

- model/engine selection
- capability display
- viewing memory patterns
- viewing RAG retrievals and evidence
- comparing runs and traces
- surfacing diagnostics and warnings

The UI is not merely a frontend. It is the principal tool for making hidden system behavior legible.

---

### 3.6 `rag_lib`

**Responsibility:** Retrieval-augmented generation and retrieval diagnostics.

This package should provide retrieval functionality and make retrieval behavior inspectable.

Typical responsibilities:

- chunk/document retrieval
- ranking and reranking
- evidence/citation selection
- prompt assembly from retrieved context
- retrieval-stage tracing and scoring

`rag_lib` should not be a black box. Its internal stages must be visible to the inspector and UI.

---

### 3.7 `agent_lib`

**Responsibility:** Agent orchestration and tool-using workflow support.

This package should enable controlled multi-step workflows while also exposing what the agents are doing.

Typical responsibilities:

- task planning
- step execution
- tool invocation
- artifact generation
- workspace policy enforcement
- agent trace/event emission

`agent_lib` is not just for automation. It is also for showing planning/tool behavior clearly and safely.

---

## 4. System-Wide Principle

Every major subsystem should be both:

- **usable** as infrastructure, and
- **inspectable** as a learning/diagnostic object.

This is the defining principle of the suite.

If a subsystem works but hides too much of its reasoning, scoring, evidence selection, or transformations, it is incomplete relative to the suite’s goals.

---

## 5. Interoperability Layer

A small shared package now exists to support composition:

### `llm_harness_core`

This package is the interoperability core. It should remain minimal and dependency-light.

It exists to define the shared vocabulary used across the suite.

### Current shared concepts

- `CapabilityDescriptor`
- `CapabilityKind`
- `LLMMessage`
- `ToolInvocation`
- `RetrievedDocument`
- `MemoryRecord`
- `OperationResult`
- `OperationWarning`
- `OperationError`
- `TraceEvent`

### Purpose of the interop layer

The interop core makes the packages composable by design rather than by convention.

It should support:

- package capability declaration
- shared config vocabulary over time
- shared result/error envelopes
- shared event/tracing schema
- shared document/evidence/message representations

### What it must not become

`llm_harness_core` must **not** become:

- a utilities dumping ground
- a backend implementation layer
- a UI layer
- a storage layer
- a place for business logic

It is a contract package.

---

## 6. Dependency Direction

The dependency graph should remain disciplined.

### Desired rule

- `llm_harness_core` depends on no heavy package in the suite.
- `llm_engines` depends on `llm_harness_core`.
- `engram` depends on `llm_harness_core`.
- `llm_inspector` depends on `llm_harness_core`.
- `llm_inspector_ui` depends on `llm_inspector`, `llm_harness_core`, and selected feature packages.
- `rag_lib` depends on `llm_harness_core`.
- `agent_lib` depends on `llm_harness_core`.

The interop layer is the stable bottom. It should not depend upward.

---

## 7. Interaction Model Between Components

### 7.1 Engine + Memory flow

Typical flow:

1. A user prompt is created.
2. `engram` or `engram` retrieves relevant memory.
3. Memory contributions are represented as `MemoryRecord` and trace events.
4. Prompt/context is assembled.
5. `llm_engines` executes the model call.
6. Result is surfaced as a shared `OperationResult`.
7. `llm_inspector` and `llm_inspector_ui` display:
   - what memory was retrieved
   - what context was injected
   - what the model returned
   - any warnings or degraded modes

### 7.2 RAG flow

Typical flow:

1. A query enters `rag_lib`.
2. Retrieval occurs over chunks/documents.
3. Ranking/reranking/filtering stages run.
4. Selected documents become `RetrievedDocument` objects.
5. Prompt assembly occurs using selected evidence.
6. `rag_lib` emits retrieval-stage `TraceEvent`s.
7. `llm_inspector` / UI render:
   - retrieved items
   - scores/ranks
   - stage transitions
   - final selected evidence
   - diagnostics such as retrieval summary and prompt assembly state

### 7.3 Agent flow (intended)

Typical flow:

1. A task enters `agent_lib`.
2. Planning occurs.
3. Steps and tool calls are emitted as shared events.
4. Agent outputs and artifacts are represented in shared result envelopes.
5. Safety policy and workspace policy are applied.
6. Inspector/UI show:
   - plan steps
   - tool calls
   - execution outcomes
   - warnings/failures
   - artifact lineage

### 7.4 UI flow

`llm_inspector_ui` is the human entry point.

It should be able to:

- show available engines and their capabilities
- show memory augmenters and their capabilities
- show retrieval pipelines and retrieval diagnostics
- compare runs across engines, memory settings, and retrieval settings
- display shared trace events regardless of origin package

---

## 8. Observability Requirements

Observability is a first-class requirement, not an afterthought.

Every major subsystem should expose enough data to answer:

- What happened?
- In what order?
- Why were these items selected?
- What was excluded?
- What context reached the model?
- What scores, ranks, or warnings were involved?
- How long did stages take?
- What degraded or failed?

### Shared observability expectations

Each subsystem should emit enough trace information to support:

- stage boundaries
- scoring/ranking
- inclusion/exclusion reasoning when available
- evidence provenance
- latency timing when available
- warning/failure reporting
- before/after transformations

This is especially important for:

- memory retrieval
- RAG retrieval and reranking
- agent planning and tool usage
- fallback behavior in engines

---

## 9. Current Interop Progress

As of this document, the following broad direction has been implemented:

### Completed or substantially advanced

- A minimal interoperability package exists: `llm_harness_core`.
- `llm_engines` has been adapted to convert to/from shared interop types.
- `engram` has been adapted to emit shared memory and trace objects.
- `llm_inspector` has been adapted to consume and expose shared interop types.
- `llm_inspector_ui` has been adapted to render shared traces and capability descriptors.
- `rag_lib` has been adapted to emit retrieval-stage diagnostics and shared retrieval objects.
- `llm_inspector_ui` now has a real `rag` augmenter path and retrieval diagnostics views.

### Not yet complete

- `agent_lib` is not yet fully migrated to the shared interop / observability layer.
- `engram` may still need fuller interop alignment depending on subsystem boundaries.
- Full monorepo-wide end-to-end regression coverage still needs continued hardening.
- Some older package-local trace vocabularies may still exist as compatibility layers.

---

## 10. Architectural Invariants

These should be treated as rules unless there is a strong reason to change them.

### 10.1 Single source of truth for contracts

No duplicate contract systems should exist when one canonical one is intended.

### 10.2 Packages must remain independently usable

Each package should be useful on its own and install without dragging in the whole suite unless feature extras are explicitly requested.

### 10.3 Interop core must stay minimal

Heavy dependencies must not leak into `llm_harness_core`.

### 10.4 Private vocabularies should converge on shared vocabularies

Backward compatibility is acceptable. Permanent duplication is not.

### 10.5 The UI should consume shared objects, not package-specific one-off glue whenever possible

The UI is the visibility layer for the whole suite. It should depend on shared semantics.

### 10.6 Every subsystem should expose inspectable behavior

A working black box is insufficient for this project’s goals.

### 10.7 Repo hygiene matters

The monorepo should not accumulate stale patch files, build outputs, caches, invalid helper files, or backup artifacts in a way that obscures authoritative code.

---

## 11. User Experience Goals

Users should be able to adopt the suite in several ways:

### 11.1 Use only one package

Examples:

- just `llm_engines` for model abstraction
- just `engram` for memory augmentation
- just `rag_lib` for retrieval
- just `llm_inspector_ui` for inspection

### 11.2 Compose a few packages

Examples:

- `llm_engines` + `engram`
- `llm_engines` + `rag_lib`
- `engram` + `llm_inspector_ui`
- `rag_lib` + `llm_inspector_ui`

### 11.3 Use the full harness

Examples:

- engine + memory + retrieval + inspection
- later: engine + memory + retrieval + agent + inspection

In all of these modes, the user should be able to understand what the system is doing, not just obtain outputs.

---

## 12. Safety and Control Expectations

This is especially important for `agent_lib`, but applies more broadly.

The suite should favor:

- explicit boundaries
- auditable actions
- clear warnings for degraded or fallback behavior
- constrained workspace access
- inspectable tool usage
- behavior that is understandable by advanced users

For agents in particular, policy and sandboxing are not optional long-term concerns. They are core trust requirements.

---

## 13. Current Known Weaknesses / Ongoing Work

These items should remain visible when planning future work:

1. `agent_lib` still needs fuller interop integration and stronger execution isolation.
2. Monorepo-wide CI and packaging hardening should continue to improve.
3. Some compatibility shims currently exist because packages were previously developed with local/private vocabularies.
4. The educational/diagnostic intent should continue to influence design choices, especially for event schemas and UI rendering.
5. Older local tracing/reporting utilities may still need consolidation around shared objects.

---

## 14. Immediate Next-Phase Priorities

These are the recommended next priorities after the current state represented by this document.

### Priority 1: `agent_lib` interop + observability

`agent_lib` should emit shared trace events and shared result envelopes so the UI can expose:

- planning
- tool calls
- step outcomes
- failures/warnings
- artifacts generated
- policy boundary decisions

### Priority 2: stronger end-to-end views in `llm_inspector_ui`

The UI should increasingly show comparative, explanatory views rather than raw traces only. Useful views include:

- memory vs. RAG vs. final prompt contribution
- stage latency comparisons
- evidence provenance comparisons
- engine comparison under identical context conditions

### Priority 3: continued contract consolidation

Any remaining package-private representations that overlap with shared interop objects should be gradually retired or reduced to compatibility adapters.

### Priority 4: repo + release hardening

Continue to improve:

- wheel build coverage
- monorepo regression checks
- import sanity from clean installs and repo root
- release hygiene

---

## 15. What Future Threads Should Assume

When resuming work in a new thread, the following assumptions should be treated as current unless the code says otherwise:

1. The suite is intended for **understanding and better using LLMs**, not just building applications.
2. The architecture is modular on purpose, so packages should remain independently useful.
3. `llm_harness_core` is the shared interop layer and should remain small and authoritative.
4. The observability path is central: `engram` → `llm_inspector` → `llm_inspector_ui`, with `rag_lib` now included in that same inspectable pipeline.
5. The UI is expected to visualize memory behavior, engine capability, and RAG retrievals.
6. `agent_lib` is the next major subsystem that needs the same level of interop and observability.
7. The guiding principle is that **important system behavior should be visible, attributable, and explainable**.

---

## 16. One-Paragraph Canonical Description

`ai_tools` is a modular Python suite for local-first LLM use that combines model abstraction, memory, retrieval, inspection, UI visualization, and agent workflow support. Its purpose is not only to make LLM-enabled systems easier to build, but also to help users understand how those systems behave. To support that, the packages are being aligned around a shared interoperability layer (`llm_harness_core`) and a common observability model so that engines, memory augmentation, RAG retrieval, and eventually agents can all be inspected through consistent traces, evidence objects, capability descriptors, and result envelopes.

---

## 17. Short Context Block for Fast Handoff

Use this when starting a new thread if needed:

- `ai_tools` is a modular local-first LLM harness plus inspection environment.
- Main packages: `llm_engines`, `engram`, `llm_inspector`,
  `llm_inspector_ui`, `rag_lib`, `agent_lib`.
- Goal is not just app-building; it is also helping users understand and better utilize LLMs.
- Shared interop package now exists: `llm_harness_core`.
- Shared objects include capabilities, messages, retrieved docs, memory records, trace events, and operation results.
- `llm_engines`, `engram`, `llm_inspector`, `llm_inspector_ui`, and `rag_lib` have begun interop alignment.
- `llm_inspector_ui` is intended to inspect engine behavior, memory augmentation, and RAG retrievals.
- `rag_lib` should expose retrieval-stage diagnostics, not just return results.
- `agent_lib` is the next major subsystem needing interop + observability alignment.
- Architectural rule: important behavior should be visible, attributable, and explainable.
