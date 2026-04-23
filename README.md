# ai_tools

`ai_tools` is a modular, local-first suite of Python libraries for **understanding, inspecting, and better utilizing LLMs**, while also providing reusable components for building LLM-based systems.

This repo should be read as both:

- a **composable harness** for LLM-enabled applications
- an **educational and diagnostic environment** for making model behavior visible

## New here?

Start with [START_HERE.md](./START_HERE.md).

That file is the fastest beginner-safe path through the repo. It tells you:
- what this repo is for
- what to do first
- what to ignore for now
- what success looks like in the first session

## Audience labels

The docs in this repo use these labels:
- **Beginner** — safe first contact for new learners
- **Intermediate** — best after the beginner path is complete
- **Advanced** — more moving parts, policy surface, or architectural depth
- **Maintainer** — useful for contributors and release work, not required for first study

## Recommended first reading order

1. [START_HERE.md](./START_HERE.md) **[Beginner]**
2. [LEARNING_PATH.md](./LEARNING_PATH.md) **[Beginner]**
3. [course/README.md](./course/README.md) **[Beginner]**
4. package READMEs for the current stage you are studying **[Beginner–Intermediate]**
5. [CURRENT_STATE.md](./CURRENT_STATE.md) **[Intermediate]**
6. [ROADMAP.md](./ROADMAP.md) **[Intermediate]**
7. [VISION.md](./VISION.md) and the ADRs **[Advanced–Maintainer]**

## Ignore these for now

If you are new to the repo, you do not need to understand everything at once. You can safely defer:
- `adr/` and deep architecture notes
- `docs/history/`
- red-team and isolation reports
- `engram` internals
- `agent_lib` until the rest of the stack makes sense
- most release and stabilization reports

Use the teaching path first, then come back to the deeper documents.

## Canonical root documents

- [START_HERE.md](./START_HERE.md) — beginner-safe entry ramp **[Beginner]**
- [LEARNING_PATH.md](./LEARNING_PATH.md) — canonical teaching sequence **[Beginner]**
- [VISION.md](./VISION.md) — architecture and design intent **[Advanced]**
- [CURRENT_STATE.md](./CURRENT_STATE.md) — implementation snapshot **[Intermediate]**
- [ROADMAP.md](./ROADMAP.md) — ordered next phases **[Intermediate]**
- [ADR_INDEX.md](./ADR_INDEX.md) — architectural decision map **[Advanced–Maintainer]**
- [AGENT_FILE_SPEC.md](./AGENT_FILE_SPEC.md) — spec for repo-local and package-local `AGENT.md` files **[Maintainer]**
- [TASK_MANIFEST_SPEC.md](./TASK_MANIFEST_SPEC.md) — spec for JSON task/progress manifests **[Maintainer]**

## Packages

Package-level labels below are meant as learning-orientation hints, not hard barriers.

| Package | Role | Learner label | Notes |
|---|---|---|---|
| [llm_harness_core](./llm_harness_core/README.md) | Shared interoperability core | Intermediate | Common schemas for capabilities, messages, evidence, results, and trace events |
| [llm_engines](./llm_engines/README.md) | Engine abstraction | Beginner | Common model/backend interface, capability descriptors, normalized responses |
| [engram_lite](./engram_lite/README.md) | Lightweight memory augmentation | Beginner | Prompt building, evidence traces, inspectable memory behavior |
| [engram](./engram/README.md) | Full memory runtime | Advanced | Richer persistent/project memory and advanced retrieval policies |
| [rag_lib](./rag_lib/README.md) | Retrieval and retrieval diagnostics | Beginner–Intermediate | Inspectable retrieval, reranking, and prompt assembly |
| [llm_inspector](./llm_inspector/README.md) | Observability layer | Beginner | Trace normalization, comparison, evidence/report conversion |
| [llm_inspector_ui](./llm_inspector_ui/README.md) | Interactive workbench | Intermediate | Inspect engines, memory, and RAG behavior through a shared UI |
| [agent_lib](./agent_lib/README.md) | Agent orchestration | Advanced | Inspectable planner/executor/tool runtime |
| [language_tutor](./language_tutor/README.md) | Reference application | Intermediate | Demonstrates the stack in a concrete interactive app |

## Package status and support matrix

This matrix is the quick guide for what to reach for first.

Category meanings:
- **Core** — foundational package intended to be reused across the suite
- **Default** — recommended first choice for most users and most teaching paths
- **Advanced** — useful, but brings more complexity or moving parts
- **Experimental** — promising and actively used, but not yet presented as the most stable default path
- **Reference app** — application-level package used to demonstrate how the stack composes

| Package | Category | Current support status | Start here? | Notes |
|---|---|---|---|---|
| [llm_harness_core](./llm_harness_core/README.md) | Core | Active and authoritative | Yes, for architecture | Shared contracts and evaluator hooks should converge here |
| [llm_engines](./llm_engines/README.md) | Core | Active and stable | Yes | Primary engine/backend abstraction |
| [llm_inspector](./llm_inspector/README.md) | Core | Active and stable | Yes | Main trace/comparison layer |
| [llm_inspector_ui](./llm_inspector_ui/README.md) | Core | Active, still growing | Yes | Shared workbench for inspecting system behavior |
| [engram_lite](./engram_lite/README.md) | Default | Active and recommended | Yes | Preferred first memory path for most users and courses |
| [rag_lib](./rag_lib/README.md) | Default | Active and recommended | Yes | Preferred retrieval path for most users and courses |
| [engram](./engram/README.md) | Advanced | Active, maturing toward shared interop | After `engram_lite` | Richer memory runtime with more complexity and policy surface |
| [language_tutor](./language_tutor/README.md) | Reference app | Active, still being aligned to the current stack | After core/default packages | Best current example of an application built from the suite |
| [agent_lib](./agent_lib/README.md) | Experimental | Active, improving, but not the first default for general use | Later | Strong teaching and research value, but still evolving around interop and safety/isolation reporting |

Recommended first paths:
- **Minimal stack**: `llm_engines` + `llm_inspector`
- **Memory-first stack**: `llm_engines` + `engram_lite` + `llm_inspector`
- **RAG-first stack**: `llm_engines` + `rag_lib` + `llm_inspector`
- **Advanced memory path**: substitute `engram` for `engram_lite` when you need richer memory behavior and are willing to take on more complexity
- **Agent path**: add `agent_lib` only after the engine, memory/retrieval, and inspection layers are understood

For the current implementation snapshot and the ordered next phases, see [CURRENT_STATE.md](./CURRENT_STATE.md) and [ROADMAP.md](./ROADMAP.md).

## Teaching path and course materials

For instructional use, start with [START_HERE.md](./START_HERE.md) and then continue to [LEARNING_PATH.md](./LEARNING_PATH.md).

Course scaffolding lives under [course/](./course/):
- [course/notebooks/](./course/notebooks/) — ordered walkthrough notebooks
- [course/starter_projects/](./course/starter_projects/) — runnable starter scaffolds learners can extend
- [docs/tutorials/](./docs/tutorials/) — focused labs for failure analysis and comparison

The intended teaching order is: engine abstraction -> inspection -> memory -> RAG -> composed application -> agents. This is the default beginner path for the repo.
Use [llm_harness_core/EVALUATION_WALKTHROUGH.md](./llm_harness_core/EVALUATION_WALKTHROUGH.md) alongside Stages 3–6 so learners compare baseline and augmented behavior as they go.

## Main composition paths

The suite is designed so packages can be used independently or in composition.

```text
llm_engines + engram_lite + llm_inspector + llm_inspector_ui
llm_engines + rag_lib + llm_inspector + llm_inspector_ui
llm_engines + engram_lite + rag_lib + llm_inspector + llm_inspector_ui
```

Reference applications and workflows then sit on top:

```text
llm_engines + engram_lite -> language_tutor (default)
llm_engines + engram      -> language_tutor (optional)

llm_engines + engram_lite + llm_inspector -> agent_lib (default memory path)
llm_engines + engram      + llm_inspector -> agent_lib (optional richer memory path)
```

## What the suite should make visible

A subsystem is not complete merely because it works. It should also make its behavior inspectable.

Examples:

- which model/backend ran
- what memory was retrieved and why
- what RAG retrieved, reranked, or dropped
- what context actually reached the model
- what warnings or degraded-mode decisions occurred
- where latency accumulated
- eventually, what agents planned and executed

## Current architectural direction

The repo is converging on a small shared interoperability layer in `llm_harness_core`.
That layer is intended to keep package composition explicit and keep the observability stack package-agnostic.

## Documentation hygiene

The files above are the active sources of truth.
Legacy planning and transition notes should live under `docs/history/` so they do not compete with the current architecture documents.

## GitHub publication readiness

Use [GITHUB_PUBLICATION_CHECKLIST.md](./GITHUB_PUBLICATION_CHECKLIST.md) before publishing a new snapshot.

The repo also includes:
- [scripts/check_teaching_artifacts.py](./scripts/check_teaching_artifacts.py) — validates the curriculum-facing assets
- [scripts/check_publication_hygiene.py](./scripts/check_publication_hygiene.py) — validates tree hygiene and doc placement for public release
