# llm_engines

> Draft README
>
> This draft is based on the architecture and interfaces designed around `llm_engines` in the current system split. It should be tightened against the actual package exports once the implementation is finalized.

`llm_engines` is the engine, model, and backend layer of the stack.

It should make it easy for applications and UIs to:

- discover available backends
- list locally available models
- search external model sources such as Hugging Face
- provision or register models
- create engine handles
- invoke models through a stable interface
- inspect backend readiness and health

## What it should own

`llm_engines` should own:

- backend discovery
- model discovery
- model provisioning / download hooks
- backend config schemas
- backend health checks
- engine creation and invocation
- provider-specific adapters

It should not own:

- memory retrieval
- prompt inspection and diffing
- chat UI state
- workbench orchestration policy

## Role in the architecture

In the larger split:

- `engram-lite` builds memory-aware prompts
- `llm_engines` executes them
- `llm_inspector` observes and compares them
- `llm_inspector_ui` gives users a single place to configure and test them

## Core capabilities

A useful `llm_engines` registry should expose operations like:

- `list_engines()`
- `list_models(engine_id, config=...)`
- `search_models(query, source=...)`
- `provision_model(...)`
- `create_engine(engine_id, config=...)`
- optional readiness methods such as:
  - `health_check(...)`
  - `ping_engine(...)`
  - `get_engine_status(...)`
  - `get_engine_config_schema(...)`

## Engine registry model

The UI and surrounding libraries should not hard-code provider logic.

Instead, `llm_engines` should present a registry that returns descriptors and factory objects.

### Engine descriptor

An engine descriptor should identify things like:

- engine id
- human-readable label
- local vs remote
- capabilities
- provider metadata

### Model descriptor

A model descriptor should identify things like:

- model id
- label
- source
- whether the model is installed
- optional metadata such as context length or quantization

## Configuration schema

A key usability feature is that the UI should be able to render engine-specific connection controls automatically.

That means `llm_engines` should expose a config schema describing fields such as:

- base URL
- API key
- timeout
- backend-specific toggles

This is what lets a workbench UI support multiple engine types without hard-coding each one.

## Health and readiness

The engine layer should distinguish between:

- engine is known
- engine is reachable
- models are visible
- a selected model is runnable under the current config

That distinction is critical in the UI because it lets users understand whether a failure is caused by:

- missing registration
- dead backend
- bad URL / auth
- no models provisioned
- wrong model selection

## Intended backend types

The architecture is designed to accommodate backends such as:

- Ollama
- vLLM
- OpenAI-compatible endpoints
- local Hugging Face-backed engines
- cloud providers through compatible engine wrappers

The exact list depends on the current implementation.

## Provisioning model

`llm_engines` should also be the place where model search and provisioning logic lives.

That may include:

- Hugging Face model search
- metadata lookup
- compatibility checks
- downloading or registering a model locally
- binding a provisioned model to a backend

The UI should expose these capabilities, but `llm_engines` should implement them.

## Minimal invocation contract

An engine handle should support a stable invocation model along the lines of:

- prompt text
- model id
- engine settings
- session id
- response text
- metrics

This lets the rest of the stack treat the engine layer generically.

## Relationship to the workbench

A good workbench should let the user:

1. choose an engine
2. choose a model
3. configure connection details
4. verify readiness
5. chat and inspect behavior immediately

That workflow is only possible if `llm_engines` presents a stable, UI-friendly API.

## Design goals

- provider-neutral surface
- local-first friendly
- cloud-capable but not cloud-dependent
- explicit readiness / health model
- provisioning hooks for model onboarding
- stable invocation contract
- easy integration with `llm_inspector_ui`

## Status

This README is intentionally architectural.

It should be revised once the concrete `llm_engines` exports, bootstrap path, and supported backends are finalized.
