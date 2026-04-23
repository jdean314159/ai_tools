# ai_tools

`ai_tools` is the umbrella system that ties together the local-LLM toolchain:

- **`engram-lite`** for memory, retrieval, and prompt assembly
- **`llm_engines`** for model discovery, provisioning, backend configuration, and inference
- **`llm_inspector`** for trace normalization, comparison, diffing, and export
- **`llm_inspector_ui`** for the interactive chat workbench

The goal is to make local and hybrid LLM experimentation practical:

- choose a model
- choose an engine/backend
- optionally add memory augmentation
- inspect the exact prompt that was built
- compare strategies side by side
- save and reuse working configurations

This repository/package is the *system-of-systems* view. It explains how the pieces cooperate. It is not intended to duplicate the internals of the underlying libraries.

---

## Design goals

`ai_tools` exists to support a local-first LLM workflow that is:

- **modular**: memory, engines, inspection, and UI are separate concerns
- **observable**: prompt construction and evidence should be visible, not hidden
- **reusable**: the same libraries should work across chat, RAG, tutoring, programming assistants, and other projects
- **experiment-friendly**: users should be able to compare baseline vs augmented runs without rewriting code
- **user-friendly**: model selection, backend selection, and testing should happen in one workbench

The system is designed so that core libraries do the work, and the UI composes them.

---

## Package roles

### `engram-lite`

Owns:

- session memory
- retrieval across memory layers
- prompt assembly
- memory-aware trace production

Does **not** own:

- model catalogs
- model downloads
- generic chat UI
- multi-system comparison UX

`engram-lite` should expose a stable prompt-building surface and a stable trace API.

### `llm_engines`

Owns:

- backend discovery
- engine health/readiness
- model catalogs and installed-model listing
- provisioning/download hooks
- engine instantiation
- inference execution

This is the layer that knows about Ollama, vLLM, OpenAI-compatible endpoints, Hugging Face search/provisioning, and similar concerns.

### `llm_inspector`

Owns:

- normalized trace schema
- compare/diff/bundle logic
- JSON/report export
- adapters from augmentation systems into inspector traces

This is not a RAG-only tool. It is the observability layer for context augmentation and prompt construction.

### `llm_inspector_ui`

Owns:

- chat workbench UI
- engine/model selection
- startup/readiness display
- profile management
- run/session persistence
- compare-mode presentation
- prompt/evidence/token panels

The UI should orchestrate the libraries, not absorb their logic.

---

## How the pieces fit together

A single user message should produce a durable **run artifact**.

High-level flow:

1. User selects an engine and model in the UI.
2. User selects one or more augmenters.
3. The UI checks engine readiness and branch readiness.
4. The selected augmenter builds a prompt.
5. `llm_inspector` normalizes the prompt trace.
6. `llm_engines` executes the prompt with the selected model.
7. The UI stores the result as a run artifact and shows:
   - response
   - final prompt
   - sections
   - evidence
   - token accounting
   - metrics
   - diffs/comparisons when applicable

This makes every run both interactive and inspectable.

---

## Core runtime concepts

### Session

A session is the persistent container for:

- chat turns
- run artifacts
- current workbench state

### Turn

A turn is a user or assistant message in the transcript.

### Run artifact

A run artifact is the record of one execution branch. It should include:

- engine id
- model id
- augmenter id
- mode (`chat` or `compare`)
- status (`ok`, `error`, or `skipped`)
- input text
- final prompt
- normalized trace
- response text
- engine metrics
- saved settings used for the run

This is the key unit of reproducibility and inspection.

### Profile

A profile is a saved configuration containing:

- selected engine/model
- engine config and inference settings
- selected augmenter(s)
- augmenter-specific options
- prompt token budget settings

Profiles make the workbench reusable instead of one-off.

---

## Modes of operation

### Chat mode

One augmenter, one engine, one model, ongoing transcript.

Use this for:

- ordinary conversation
- memory accumulation
- prompt-inspection during real use

### Compare mode

One user input, multiple augmentation branches, same engine/model unless explicitly changed later.

Use this for:

- baseline vs memory augmentation
- future RAG vs memory comparison
- prompt diff analysis
- response comparison under controlled conditions

Compare mode should allow partial execution:

- runnable branches should run
- unavailable branches should be stored as `skipped`
- the comparison view should show both successful and skipped branches explicitly

---

## Readiness model

The system distinguishes between several different states.

### Engine existence

The engine is registered in `llm_engines`.

### Engine reachability

The backend can actually be contacted from the current UI session.

### Model availability

The selected engine/configuration can see at least one model.

### Run readiness

A specific engine + model + configuration is ready for execution.

### Branch readiness

A specific augmenter branch is ready for execution.

This separation is important because a backend can exist without being reachable, and can be reachable without having usable models.

---

## Default behavior

The system should be **local-first**, not cloud-first.

Recommended default-selection policy:

1. last-used healthy engine/model
2. auto-detected healthy local engine/model
3. debug/demo engine
4. cloud provider as explicit opt-in

Cloud models such as Claude, ChatGPT, Gemini, or DeepSeek should be supported as first-class options, but they should not be the default path.

---

## UI expectations

The workbench UI should support:

- chat transcript
- engine selection
- model selection
- readiness/startup diagnostics
- Hugging Face or other model search/provision flows
- profile save/load/duplicate/delete
- prompt section inspection
- evidence inspection
- token accounting
- compare-mode grouping by input turn
- JSON export for runs and sessions

The UI should feel like a single place to:

- pick a model
- launch/test it
- augment prompts
- inspect what happened

---

## Repository organization

One reasonable top-level structure is:

```text
ai_tools/
  README.md
  docs/
  examples/

  engram_lite/
  llm_engines/
  llm_inspector/
  llm_inspector_ui/
```

This top-level repository can serve as:

- a coordination repo
- shared documentation home
- integration test home
- examples/demo home

Each library should still remain independently installable and versionable.

---

## Suggested interfaces

At the integration level, the key contracts are:

### Augmenter contract

An augmenter should accept a user request and return:

- prompt
- prompt trace
- prompt token counts
- optional raw context

### Engine registry contract

The engine layer should support:

- list engines
- list models
- search models
- provision models
- create engine
- health/readiness probes
- engine config schema

### Inspector contract

The inspector layer should support:

- normalize traces
- compare traces
- diff traces
- build export bundles

### UI orchestrator contract

The UI should build a run plan and return one or more run artifacts.

---

## Current implementation direction

The current design direction is:

- move memory/prompt tracing into `engram-lite` / Engram itself
- keep `llm_inspector` as a thin normalized observability layer
- keep model/backend logic in `llm_engines`
- move generic chat/inspection UI responsibility into `llm_inspector_ui`

That split avoids turning any one package into a monolith.

---

## What belongs in `ai_tools`

Good candidates for this umbrella layer:

- top-level architecture docs
- integration examples
- end-to-end demos
- handoff documentation
- compatibility notes between packages
- integration tests that span multiple libraries

What should *not* live here long-term:

- duplicated engine logic from `llm_engines`
- duplicated memory logic from `engram-lite`
- duplicated trace logic from `llm_inspector`
- UI business logic that belongs in `llm_inspector_ui`

`ai_tools` should explain and coordinate more than it should implement.

---

## Example end-to-end scenario

A typical workbench interaction looks like this:

1. Start `llm_inspector_ui`
2. Select a healthy local engine such as Ollama or vLLM
3. Select a model
4. Choose `baseline` or `engram` augmentation
5. Send a message
6. Inspect:
   - final prompt
   - sections
   - evidence
   - token accounting
7. Save the working configuration as a profile
8. Run compare mode against another augmenter
9. Export the run or session as JSON

This is the core user experience the system is designed to support.

---

## Near-term roadmap

Near-term priorities:

- strengthen `llm_engines` registry/bootstrap and config schema support
- continue improving `llm_inspector_ui` as the main workbench
- add rerun/edit-run behavior from stored run artifacts
- improve export/report flows
- add broader integration tests across packages

Longer-term priorities:

- richer compare workflows
- better provisioning UX for models
- more augmenters beyond baseline and memory
- tighter compatibility/versioning documentation across packages

---

## Summary

`ai_tools` is the orchestration view of the stack.

It exists to make these separate capabilities work together cleanly:

- **memory** from `engram-lite`
- **execution** from `llm_engines`
- **observability** from `llm_inspector`
- **interactive experimentation** from `llm_inspector_ui`

The system should let a user choose a model, run it, augment it, inspect it, compare it, and save what worked — without collapsing the underlying libraries into one large package.
