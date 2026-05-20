# Package Roles and Current Support Status

Last updated: 2026-05-20

## Status summary

The repo is past the main packaging/import stabilization checkpoint and has
also completed a GitHub publication/clone-verification pass. Most packages use
`src/` layout; `llm_engines` intentionally remains on direct layout.

The default install path is now expected to be lightweight:

    make install
    make test-core

PyTorch and heavyweight local-model packages are optional extras, reached via
`make install-ml`, `make install-gpu`, and `make test-ml`.

See `STATUS.md` for the authoritative current baseline and active work list.

## Package matrix

| Package | Role | Current status | Notes |
|---|---|---|---|
| `llm_harness_core` | Shared harness/interoperability primitives. | Core package. | Keep APIs small and dependency-light. Avoid moving implementation-heavy utilities here unless they are true contracts. |
| `llm_engines` | Engine abstraction for Ollama, OpenAI-compatible APIs, Anthropic, vLLM, llama.cpp, HuggingFace, and future backends. | Intentional direct layout: `llm_engines/llm_engines`. | `dev` should stay lightweight. HuggingFace/PyTorch/vLLM/llama.cpp belong behind explicit extras. |
| `engram_lite` | Lightweight memory path for teaching and production-hardening. | Default memory path. | Should remain the simpler baseline and comparison target. ADR-007 facade migration is still active work. |
| `engram` | Full memory runtime with advanced memory layers and retrieval policy. | Advanced package on `src` layout. | Canonical import path is `engram/src/engram`. Base imports should not require episodic/local-embedding/neural extras. |
| `engram_ui` | Streamlit sandbox/reference UI for full Engram. | Top-level package on `src` layout. | Installed by the root `Makefile` after `engram`. Keep UI dependencies separate from the memory runtime. |
| `llm_inspector` | Inspection/provenance layer for traces, evidence, prompt construction, and comparison workflows. | Core observability package. | Important for making memory/RAG/agent behavior inspectable. |
| `llm_inspector_ui` | Interactive workbench for trace inspection and debugging. | Active package on `src` layout. | Previous `describe_ui` import blocker is resolved. Do not treat it as active. |
| `rag_lib` | RAG building blocks, labs, and evaluation utilities. | Default retrieval path. | Keep examples runnable without live model access where practical. |
| `agent_lib` | Agent abstractions and coordination primitives. | Experimental/advanced. | Continue only with explicit sandbox, policy, and trace boundaries. |
| `language_tutor` | Reference app using engines, memory, and optional richer features. | Reference application. | Should default to the lightweight stack and make richer memory/voice features optional. |

## Dependency discipline

Use the root `Makefile` for local development instead of installing packages
out of order by hand:

    make install
    make test-core

Do not add unpublished sibling packages as PyPI dependencies in package extras.
For example, `engram[dev]` should not depend on `llm-inspector`; the root
`Makefile` installs sibling packages in monorepo order.

Keep `dev` extras for test/development tooling. Put heavyweight runtime stacks
behind explicit extras such as `ml`, `ml-dev`, `local-embeddings`,
`huggingface`, `local-backends`, or `experimental`.
