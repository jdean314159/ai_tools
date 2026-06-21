# ai_tools — Learning Path

**Audience label:** Beginner → Intermediate

This document is the **teaching spine** for the `ai_tools` monorepo.

Use it when the goal is to **learn how to build LLM applications in a disciplined way**, not merely to browse the packages.

The recommended order is intentional. It moves from:

1. model access
2. inspection
3. memory augmentation
4. retrieval augmentation
5. application composition
6. agent orchestration

If you are teaching from this repo, prefer this file over sending learners package-by-package without structure.

The canonical notebook sequence is maintained in [`course/CURRICULUM.md`](../../course/CURRICULUM.md).

---

## Before you begin

If this is your first contact with the repo, read [`START_HERE.md`](./START_HERE.md) first.

## What to ignore at first

You do not need to understand these on day one:
- `adr/`
- `docs/history/`
- `agent_lib` internals
- deep `engram` internals
- release and stabilization reports

Return to them after the default path makes sense.

## Prerequisites

A learner should already be comfortable with:
- Python virtual environments
- installing editable packages with `pip install -e`
- reading small Python scripts and tests
- basic prompt/response interaction with an LLM

Helpful but not required:
- Ollama or another local backend
- prior experience with retrieval or vector stores
- prior experience with multi-agent systems

---

## Recommended setup

For a lightweight local teaching setup:

```bash
make install
make test-core
```

For the inspector workbench path:

```bash
cd llm_inspector_ui
python -m pytest -q tests
```

For the teaching materials check:

```bash
python scripts/check_teaching_artifacts.py
```

---

## Stage 1 — Call a model through a clean interface **[Beginner]**

### Goal
Understand the engine abstraction before introducing augmentation.

### Learn here
- [`llm_engines`](../../llm_engines/README.md)
- [`llm_harness_core`](../../llm_harness_core/README.md)
- notebooks: [`course/notebooks/00_llm_fundamentals.ipynb`](../../course/notebooks/00_llm_fundamentals.ipynb), [`course/notebooks/01_environment_setup.ipynb`](../../course/notebooks/01_environment_setup.ipynb), [`course/notebooks/02_engine_basics.ipynb`](../../course/notebooks/02_engine_basics.ipynb)
- starter project: [`course/starter_projects/minimal_chat_app`](../../course/starter_projects/minimal_chat_app)

### Questions to answer
- What is the minimum contract needed to call a model well?
- How should model/backend capabilities be represented?
- What should be normalized before higher layers consume responses?

### Outcome
By the end of this stage, a learner should be able to describe why a reusable engine layer matters and how it prevents backend-specific code from leaking into every application.

---

## Stage 2 — Inspect what happened, not just what came back **[Beginner]**

### Goal
Introduce observability early.

### Learn here
- [`llm_inspector`](../../llm_inspector/README.md)
- [`llm_inspector_ui`](../../llm_inspector_ui/README.md)
- guide: [`llm_inspector_ui/WORKBENCH_TEACHING_GUIDE.md`](../../llm_inspector_ui/WORKBENCH_TEACHING_GUIDE.md)
- notebook: [`course/notebooks/03_inspecting_model_behavior.ipynb`](../../course/notebooks/03_inspecting_model_behavior.ipynb)

### Questions to answer
- What metadata matters for debugging an LLM application?
- What context actually reached the model?
- How can a baseline run be compared with an augmented run?

### Outcome
Learners should stop treating model outputs as opaque and start treating the application as an inspectable pipeline.

---

## Stage 3 — Add lightweight memory carefully **[Beginner]**

### Goal
Show memory augmentation as an inspectable prompt-construction problem.

### Learn here
- [`engram`](../../engram/README.md)
- notebook: [`course/notebooks/04_memory_with_engram.ipynb`](../../course/notebooks/04_memory_with_engram.ipynb)
- starter project: [`course/starter_projects/memory_tutor`](../../course/starter_projects/memory_tutor)

### Questions to answer
- What should count as a memory worth retrieving?
- How do we show why a memory was included?
- What can go wrong when memory is stale, irrelevant, or contaminated?

### Outcome
Learners should be able to explain the trade-off between simple prompt history and structured, inspectable memory augmentation.

---

## Stage 4 — Add retrieval without turning the system into a black box **[Beginner–Intermediate]**

### Goal
Teach RAG as a series of explicit decisions.

### Learn here
- [`rag_lib`](../../rag_lib/README.md)
- tutorial: [`docs/tutorials/broken_rag_lab.md`](../tutorials/broken_rag_lab.md)
- notebooks: [`course/notebooks/05_rag_with_rag_lib.ipynb`](../../course/notebooks/05_rag_with_rag_lib.ipynb), [`course/notebooks/06_advanced_rag_and_evaluation.ipynb`](../../course/notebooks/06_advanced_rag_and_evaluation.ipynb)
- starter project: [`course/starter_projects/source_grounded_qa`](../../course/starter_projects/source_grounded_qa)

### Questions to answer
- What was retrieved?
- What was reranked or filtered?
- Why did the final context window contain these documents and not others?

### Outcome
Learners should be able to diagnose RAG failures as retrieval and context-construction failures, not merely “the model hallucinated.”

---

## Stage 5 — Study a composed application **[Intermediate]**

### Goal
See how the layers fit together in a real application.

### Learn here
- [`examples/language_tutor`](../../examples/language_tutor/README.md)
- notebook: [`course/notebooks/07_reference_app_walkthrough.ipynb`](../../course/notebooks/07_reference_app_walkthrough.ipynb)

### Questions to answer
- What does a real application built from these layers look like?
- Which dependencies are essential, optional, or configurable?
- How should inspection and evaluation be exposed in an app intended for users?

### Outcome
Learners should be able to move from isolated subsystems to a coherent application architecture.

---

## Stage 6 — Introduce agents last **[Advanced]**

### Goal
Show orchestration, tool use, and safety after the rest of the stack is understood.

### Learn here
- [`agent_lib`](../../agent_lib/README.md)
- tutorial: [`docs/tutorials/agent_red_team_lab.md`](../tutorials/agent_red_team_lab.md)
- notebook: [`course/notebooks/08_agent_safety_and_failure_modes.ipynb`](../../course/notebooks/08_agent_safety_and_failure_modes.ipynb)
- comparison guide: [`docs/native_vs_integration.md`](../native_vs_integration.md)

### Questions to answer
- What belongs in policy versus hard isolation?
- What makes agent execution inspectable?
- When is a native runtime better than an integration path?

### Outcome
Learners should understand both the value and the risks of agent-based systems, and should not treat policy restrictions as equivalent to sandboxing.

---

## Evaluation spine — Measure changes before adding more complexity **[Beginner–Intermediate]**

### Goal
Teach learners to compare baseline, memory-augmented, retrieval-augmented, and agent-mediated behavior with shared evaluators instead of anecdotes.

### Learn here
- `llm_harness_core/EVALUATION_WALKTHROUGH.md`
- `course/notebooks/09_evaluating_llm_applications.ipynb`
- `course/starter_projects/source_grounded_qa/eval.py`
- `integration_tests/memory_eval.py`

### Questions to answer
- What is the baseline answer?
- What changed after memory or retrieval was added?
- Which evaluator is honest enough for this comparison?
- Did the answer improve, or did it only become longer and more confident?

### Outcome
Learners can justify claims of improvement with evaluator outputs, evidence checks, and side-by-side comparisons rather than intuition alone.

## Suggested course rhythm **[Instructor / Intermediate]**

For a short course or self-study track:

- **Module 1:** stages 1–2
- **Module 2:** stage 3
- **Module 3:** stage 4
- **Module 4:** stage 5
- **Module 5:** stage 6

Recommended rule: do not teach agents before learners can explain engine abstraction, memory augmentation, retrieval augmentation, and trace inspection.

---

## Default versus advanced paths **[Beginner–Advanced]**

### Default path for most learners
- `llm_engines`
- `llm_inspector`
- `engram`
- `rag_lib`
- `language_tutor`
- `agent_lib` last

### Advanced path
Use these only after the default path is understood:
- `engram` instead of `engram` when richer persistent memory is the real learning target
- integration-mode agent orchestration when comparing external orchestration against native runtime design

---

## What learners should be able to do by the end **[Beginner–Intermediate]**

A successful learner should be able to:
- build a small LLM application on a normalized engine layer
- inspect what context reached the model
- add memory and explain why a memory was retrieved
- add retrieval and explain why evidence was included or excluded
- compare baseline and augmented runs
- discuss agent safety in terms of both policy and isolation

That is the standard this repo should teach toward.
