# Language Tutor — Reference App Guide

`language_tutor` is the package learners should study when they are ready to move from isolated subsystems to a real application.

This guide answers a different question than the package README.
The README explains what the package contains. This guide explains **why it exists in the teaching sequence** and **how it maps to the rest of the stack**.

---

## Why this package matters

A learner can understand engines, memory, and retrieval individually and still not know how to build an actual LLM application.

`language_tutor` exists to bridge that gap. It shows how to combine:

- a model/backend abstraction
- a memory backend
- application-specific state and workflows
- an HTTP/UI surface
- inspectable diagnostics that can later flow into the workbench

In the course sequence, this is **Stage 5 — composed application**.

---

## Current stack map

```text
language_tutor
├── llm_engines         engine selection and normalized backend access
├── engram              project memory through TutorMemoryBackend
├── llm_harness_core    shared capability/result/trace contracts
├── llm_inspector       intended comparison/reporting path
└── llm_inspector_ui    intended visual workbench path
```

What is true **today**:
- the engine and memory composition paths are real
- the shared interop result objects are real
- the app is a valid integration target and teaching example

What is still **maturing**:
- fuller workbench surfacing for tutor-specific traces
- optional `rag_lib` integration for curriculum or explanation retrieval
- continued cleanup of older standalone assumptions

---

## How to read the package

Read these files in this order:

1. `examples/language_tutor_reference_app/README.md`
2. `examples/language_tutor_reference_app/src/language_tutor/tutor_session.py`
3. `examples/language_tutor_reference_app/src/language_tutor/memory_backend.py`
4. `examples/language_tutor_reference_app/src/language_tutor/interop.py`
5. `examples/language_tutor_reference_app/src/language_tutor/routes/session.py`
6. `examples/language_tutor_reference_app/src/language_tutor/routes/conversation.py`
7. `examples/language_tutor_reference_app/tests/test_language_tutor_interop_contracts.py`

That order follows the educational question sequence: composition, orchestration, memory boundary, shared contracts, API surface, then validation.

---

## What each subsystem teaches

### 1. `llm_engines`
Teaches how to keep model/backend differences from leaking into app code.

Where to see it here:
- `engine_manager.py`
- `llm_engines_adapter.py`

### 2. `engram`
Teaches that memory is not merely “save chat history.” It is prompt construction plus inspectable retrieval.

Where to see it here:
- `memory_backend.py`
- `TutorSession.handle_text()`

The tutor-owned protocol keeps this lesson on the public boundary rather than
on Engram internals.

### 3. `llm_harness_core`
Teaches that a real suite needs shared result, capability, and trace schemas so different packages can interoperate.

Where to see it here:
- `interop.py`
- `tests/test_language_tutor_interop_contracts.py`

### 4. `llm_inspector` and `llm_inspector_ui`
Teach that inspection should be part of the application architecture, not an afterthought.

Current state here:
- the tutor already emits compatible shared interop objects
- deeper tutor-specific workbench views are still a follow-on step

### 5. `rag_lib`
Teaches retrieval-backed grounding.

Current state here:
- not yet a primary runtime dependency of `language_tutor`
- best understood as an extension path for explanation retrieval, curriculum retrieval, or source-grounded lesson generation

---

## Best teaching sequence inside this app

### Pass 1 — run it
Goal: see the application shape.

### Pass 2 — follow a single user turn
Trace how a message moves through:
1. API route
2. `TutorSession.handle_text()`
3. memory prompt construction
4. executor call
5. post-processing and persistence

### Pass 3 — compare recorded memory behavior
Run the same scenario in two fresh Engram directories.
Ask which observations are stable and which require stronger evidence.

### Pass 4 — inspect the shared contracts
Use the interop helpers and tests to see what should be visible to comparison and observability tools.

### Pass 5 — discuss extension points
Only after the above should learners consider:
- `rag_lib` integration
- richer inspector UI views
- agent-style orchestration around the tutor

---

## Helpful commands

Run the package tests:

```bash
python -m pytest -q examples/language_tutor_reference_app/tests
```

Inspect the machine-readable reference-app description:

```bash
# After starting the FastAPI app
curl http://localhost:8080/api/session/reference-stack
```

Try the alternate memory backend:

```bash
curl -X POST http://localhost:8080/api/session/start \
  -H "Content-Type: application/json" \
  -d '{"language":"spanish","memory_backend":"engram"}'
```

---

## What success looks like

After working through this guide, a learner should be able to explain:

- why the app depends on `llm_engines` rather than calling a backend directly
- why `engram` sits behind a tutor-owned protocol
- how shared interop results make the app inspectable
- where `rag_lib` could fit without pretending it is already fully integrated
- why a reference application is necessary in a teaching repo with many libraries
