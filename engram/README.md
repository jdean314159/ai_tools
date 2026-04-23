# Engram

`engram` is the full persistent memory runtime in the `ai_tools` stack.

It is the heavier, richer counterpart to `engram_lite`:

- `engram_lite` is the default lightweight augmentation path
- `engram` is the advanced multi-layer memory system for deeper persistence, lifecycle behavior, and experimental memory features

`engram` should be understood as both:

1. a reusable memory subsystem for LLM applications, and
2. an inspectable object in the broader `ai_tools` workbench

The package is independently installable, but it is designed to compose with:

- `llm_engines` for backend/model abstraction
- `llm_harness_core` for shared interop objects
- `llm_inspector` / `llm_inspector_ui` for observability and comparison

---

## Current role in the stack

Use `engram` when you want more than lightweight prompt augmentation.

Typical reasons to choose `engram` instead of `engram_lite`:

- multi-layer memory with different storage and retrieval behaviors
- richer long-term persistence and project memory management
- more advanced lifecycle, promotion, and archival ideas
- a place to explore more experimental memory behaviors
- a fuller “memory laboratory” for inspection and comparison

Use `engram_lite` when you want a simpler, lower-friction default memory path.

---

## Memory layers

| Layer | Storage | What it stores | Typical role |
|---|---|---|---|
| **Working** | SQLite (WAL) | recent turns in the active session | immediate local context |
| **Episodic** | ChromaDB | important past interactions | reusable experience |
| **Semantic** | SQLite + FTS5 | facts, preferences, typed relations | persistent structured recall |
| **Cold** | SQLite FTS5 | archived episodes | low-cost long-term keyword recall |
| **Neural** | file / torch tensors | learned associative patterns, novelty signals | experimental associative memory |

All layers are optional at the dependency level. Working and cold storage can run with minimal extras. Episodic requires `chromadb`. Neural features require `torch`.

---

## Architectural position

In the current `ai_tools` design, `engram` should not be treated as a private side system.
It is part of the same composable harness as the other packages.

The intended direction is:

```text
llm_engines -> engram -> llm_inspector -> llm_inspector_ui
```

and, when appropriate:

```text
engram + rag_lib + llm_engines -> reference application or agent runtime
```

`engram` is expected to align with the same shared observability story as the rest of the suite, even where that migration is not yet complete.

---

## Quick start

```python
from pathlib import Path
from engram import ProjectMemory
from llm_engines import EngineFactory

engine = EngineFactory.create("ollama", model="qwen3:8b")

with ProjectMemory(
    project_id="my_assistant",
    project_type="general_assistant",
    base_dir=Path("./memory"),
    llm_engine=engine,
) as memory:
    result = memory.respond("What is asyncio?")
    print(result["answer"])
```

---

## Core interface

`ProjectMemory` is the main entry point. It coordinates the layers, token budgeting, retrieval behavior, and session state.

```python
result = memory.respond("Explain async/await in Python.")
print(result["answer"])
print(result["prompt_tokens"])

augment_result = memory.augment(AugmentRequest(user_text="..."))
prompt = augment_result.prompt
trace = augment_result.trace
```

The practical interpretation is:

- `respond(...)` is the integrated memory-plus-generation path
- `augment(...)` is the inspectable context-construction path

That distinction matters in `ai_tools`, because the suite is meant to make memory behavior visible rather than hide it.

---

## Installation

```bash
pip install -e "."
pip install -e ".[episodic]"
pip install -e ".[semantic]"
pip install -e ".[neural]"
pip install -e ".[all]"
```

---

## Design notes

Important architectural characteristics:

- single-writer architecture for write coordination
- WAL mode for SQLite-backed stores
- bounded event queue for backpressure
- content-addressed episodic deduplication
- neural novelty treated as a signal, not a direct classifier

These choices are intended to keep the memory runtime practical for local-first use while leaving room for more advanced memory experimentation.

---

## Relationship to `engram_lite`

The current intended split is:

### `engram_lite`
- lightweight default augmentation layer
- easier to adopt independently
- easier to test and use in reference integrations
- first choice for the workbench and lightweight apps

### `engram`
- fuller persistent memory runtime
- broader memory architecture and lifecycle ideas
- place for more ambitious or experimental memory behavior
- heavier but more expressive system

This distinction should continue to become clearer across the repo and UI.

---

## Interop and observability status

`engram` is architecturally expected to participate in the shared `llm_harness_core` vocabulary and the same observability model used by the rest of the suite.

That migration is not as complete here as it is for:

- `engram_lite`
- `llm_inspector`
- `llm_inspector_ui`
- `rag_lib`

So the current status is:

- core functionality exists and is substantial
- the package is important to the stack
- alignment with the new shared interop/inspection model is still in progress

---

## Remaining work

- align more outputs directly with `llm_harness_core`
- expose fuller shared trace/event shapes for inspection tools
- clarify the workbench story for full `engram` versus `engram_lite`
- expand integration coverage with `llm_inspector_ui` and other consumers
- continue stabilization of the more advanced layers before describing the package as production-ready

---

## Project context

For architectural context and continuity in the monorepo, see:

- `../VISION.md`
- `../CURRENT_STATE.md`
- `../ROADMAP.md`
- `../ADR_INDEX.md`
