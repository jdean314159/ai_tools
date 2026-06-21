# Package Roles and Current Support Status

Last updated: 2026-05-22

## Status summary

The memory-package consolidation is complete. The monorepo now has a single
memory library: `engram`.

Default install is lightweight:

    make install
    make test-core

PyTorch and heavyweight local-model packages are optional extras.

See `STATUS.md` for the authoritative current baseline and active work list.

## Package matrix

| Package | Role | Current status | Notes |
|---|---|---|---|
| `llm_harness_core` | Shared harness/interoperability primitives. | Core package. | Keep APIs small and dependency-light. |
| `llm_engines` | Engine abstraction for Ollama, OpenAI-compatible APIs, Anthropic, vLLM, llama.cpp, and future backends. | `src/` layout (`llm_engines/src/llm_engines`); converted from direct layout by ADR-014. | `dev` should stay lightweight. HuggingFace/PyTorch/vLLM/llama.cpp behind explicit extras. |
| `engram` | Standalone memory library. JSONL source-of-truth, optional ChromaDB, RRF hybrid retrieval, semantic graph. | Active and recommended. | Default memory path for teaching and production use. No torch required by default. |
| `llm_inspector` | Inspection/provenance layer for traces, evidence, prompt construction, and comparison workflows. | Core observability package. | Important for making memory/RAG/agent behavior inspectable. |
| `llm_inspector_ui` | Interactive workbench for trace inspection and debugging. | Active. | Do not add direct engine/runtime dependencies here; consume engines via `llm_engines`. |
| `rag_lib` | RAG building blocks, labs, and evaluation utilities. | Default retrieval path. | Keep examples runnable without live model access where practical. |
| `agent_lib` | Agent abstractions and coordination primitives. | Experimental/advanced. | Continue only with explicit sandbox, policy, and trace boundaries. |
| `language_tutor` | Reference app using engines, memory, and optional richer features. | Active. Engine imports migrated to llm_engines. | Default memory path is `engram`. |

### Vendored reference subtrees (not ai_tools packages)

- `asc/` - externally authored agent development app, imported as a template
  for building an equivalent capability on the ai_tools libraries. It is
  exempt from the documentation hygiene gates through `scripts/_vendored.py`.
  The eventual ai_tools-based equivalent is first-class code and is not exempt.

## Dependency discipline

    make install       # installs all packages in correct monorepo order
    make test-core     # runs default suite

Do not add unpublished sibling packages as PyPI dependencies in package extras.
Keep `dev` extras for test/development tooling only.
