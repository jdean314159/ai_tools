# Package Roles and Current Support Status

Last updated: 2026-05-09

## Status summary

The repo is past the main package-layout stabilization checkpoint. Nine packages are on `src/` layout. `llm_engines` is intentionally on direct layout — see `tests/test_import_provenance.py` for the codified contract. The broad package-local gate passed after the `language_tutor`, `engram`, and `engram_ui` conversions.

Recent broad gate:

    1701 passed, 23 skipped in 937.49s

## Package matrix

| Package | Role | Current status | Notes |
|---|---|---|---|
| `llm_engines` | Engine abstraction layer for Ollama, vLLM/OpenAI-compatible APIs, llama.cpp-style backends, and shared request/response contracts. | Stabilized. Direct layout (`llm_engines/llm_engines`). | Codified by `tests/test_import_provenance.py`. Treat as foundational dependency. |
| `llm_harness_core` | Shared harness/interoperability primitives used across memory, inspection, and evaluation layers. | Participates in broad gate. | Keep APIs small and boring. Avoid duplicating contracts in downstream packages. |
| `engram_lite` | Lightweight memory module intended for production hardening and interop testing. | Participates in broad gate. | Should remain the simpler memory baseline and comparison target. |
| `engram` | Full memory system with working/episodic/semantic/neural/cold memory and lifecycle behavior. | Stabilized package layout. Lifecycle guards in place. | See `STATUS.md` for current code-health priorities. |
| `engram_ui` | Streamlit/UI layer for interacting with `engram`. | Moved under `engram/src/engram_ui`. | Keep UI imports package-based, not path-based. |
| `llm_inspector` | Inspection/provenance layer for prompt construction, retrieval traces, and comparison workflows. | Participates in broad gate. | Subprocess CLI tests are important because they catch editable-install exposure problems. |
| `llm_inspector_ui` | Richer UI layer for trace inspection/debugging. | Stabilized. `src/` layout. | Previous `describe_ui` import blocker is resolved. Do not treat it as active. |
| `rag_lib` | RAG building blocks, labs, and evaluation utilities. | Participates in broad gate. | Defer expansion until quality cleanup is complete. |
| `agent_lib` | Agent abstractions and coordination primitives. | Participates in broad gate. | Avoid adding complexity until packaging/lifecycle cleanup remains clean. |
| `language_tutor` | Reference app using engines, memory, and optional voice features. | Stabilized. `src/` layout. | Optional voice dependencies should not hard-fail basic imports. |

## Current priority

See `STATUS.md` for the current priority order.

## Dependency discipline

Use editable installs for local development:

    python -m pip install -e ./llm_engines
    python -m pip install -e ./language_tutor
    python -m pip install -e ./engram

Avoid relying on production `PYTHONPATH` mutations.
