# ai_tools

A modular, local-first suite of Python libraries for building, inspecting, and
understanding LLM-based systems. Each package is a reusable building block you
can adopt on its own or compose with the others.

The design priority is **inspectability**: a subsystem is not complete merely
because it works — it should make its behavior visible. Which backend ran, what
memory or retrieval was selected and why, what context actually reached the
model, where latency went.

Local-first throughout: a default install needs no GPU, no PyTorch, and no cloud
API keys. Heavier capabilities (local model execution, neural memory, GPU
inference) are optional tiers, not baseline requirements.

## Install

```bash
make install      # creates a project-local .venv, installs all packages
make test-core    # default test suite (no torch, no network)
```

`import engram`, `import llm_engines`, etc. resolve without `sentence_transformers`
or PyTorch. Optional capability tiers:

```bash
make install-gpu  # CUDA PyTorch + GPU extras
make test-ml      # torch-dependent tests
```

## Packages

Each package declares a maturity tier. **stable** = public API committed;
**beta** = usable, API mostly settled; **experimental** = do not build on it
expecting stability.

| Package | Tier | What it does | Entry point |
|---|---|---|---|
| [llm_harness_core](./llm_harness_core/README.md) | stable | Shared interop contracts: capabilities, messages, evidence, results, trace events | contracts module |
| [llm_engines](./llm_engines/README.md) | stable | One interface over Ollama, OpenAI-compatible APIs, Anthropic, vLLM, llama.cpp | engine factory |
| [engram](./engram/README.md) | beta | Project memory: prompt building, hybrid retrieval, inspectable evidence traces | `ProjectMemory` |
| [rag_lib](./rag_lib/README.md) | beta | Retrieval building blocks: chunking, hybrid BM25+dense, reranking, evaluation contracts | pipeline object |
| [llm_inspector](./llm_inspector/README.md) | beta | Trace normalization, run comparison, evidence/report conversion | inspection API |
| [llm_inspector_ui](./llm_inspector_ui/README.md) | beta | Interactive workbench to inspect engines, memory, and RAG behavior | run as a tool |
| [agent_lib](./agent_lib/README.md) | **experimental** | Planner/executor/tool runtime with policy and sandbox boundaries | coordination primitives |

Application modules and worked examples also live in this repository. The
currently active application is the local-first
[`mail_assistant`](./examples/mail_assistant/README.md), built on the
deterministic `mail_lib` module. See the [examples index](./examples/README.md)
for the complete list.

`agent_lib` is experimental — its API will move. Build on it only for
exploration, not for anything you need to stay stable.

## Composing the packages

The packages are independent but designed to compose. Common stacks:

```text
Minimal      llm_engines + llm_inspector
Memory       llm_engines + engram + llm_inspector
Retrieval    llm_engines + rag_lib + llm_inspector
Full         llm_engines + engram + rag_lib + llm_inspector + llm_inspector_ui
```

Add `llm_inspector_ui` to any stack to inspect it through a shared workbench.
Add `agent_lib` only after the engine, memory/retrieval, and inspection layers
are understood.

## Examples

Worked applications built on the suite live in [`examples/`](./examples/). They
are built against the public APIs above — they show the supported way to use the
libraries, not internal shortcuts. `language_tutor` is the reference example
for composing `llm_engines` and `engram`; `mail_assistant` is the active
local-first application.

## What the suite makes visible

The observability stack (`llm_inspector` + `llm_inspector_ui`) is package-
agnostic and surfaces:

- which model/backend ran
- what memory was retrieved and why
- what RAG retrieved, reranked, or dropped
- what context actually reached the model
- warnings and degraded-mode decisions
- where latency accumulated

## Documentation

- **Per-package READMEs** — start here for using any single package.
- [docs/design/](./docs/design/) — architecture and design intent.
- [adr/](./adr/) and [ADR_INDEX.md](./ADR_INDEX.md) — architectural decision records.
- [CONTRIBUTING.md](./CONTRIBUTING.md) — how to contribute; build, test, and release process.
- [docs/internal/](./docs/internal/) — working notes (status, roadmap, governance). Not required to use the libraries.

## License

See [LICENSE](./LICENSE).
