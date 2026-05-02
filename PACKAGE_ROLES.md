# Package roles

This file is the repo-level stabilization map. It defines the intended role of each package so documentation, examples, tests, and future agent work do not re-derive the architecture differently.

| Package | Role | Default learner path | Advanced notes |
|---|---|---:|---|
| `llm_harness_core` | Shared interop contracts: capabilities, messages, results, traces, retrieved documents, and memory records. | yes | Keep small and dependency-light. Other packages should adapt to this layer, not redefine it. |
| `llm_engines` | Model/backend access behind normalized engine capabilities and response schemas. | yes | Local backends first; cloud providers optional and explicit. |
| `engram_lite` | Default lightweight memory augmentation for teaching, demos, and small applications. | yes | Should remain installable and inspectable without forcing full Engram complexity. |
| `engram` | Advanced/full memory runtime with richer persistence, policy, and retrieval behavior. | after `engram_lite` | Use when richer memory behavior is the lesson or production target. |
| `rag_lib` | Retrieval and source-grounded QA patterns with visible evidence flow. | yes | Keep failure labs runnable without requiring a live model. |
| `llm_inspector` | Core trace/evaluation inspection logic and CLI-facing inspection primitives. | yes | Should consume shared interop records from memory and retrieval packages. |
| `llm_inspector_ui` | Streamlit workbench for comparing baseline, memory, retrieval, and later agent runs. | yes | `engram_lite` is the default memory branch; full `engram` is advanced. |
| `language_tutor` | Reference application showing how the layers compose into a user-facing tool. | intermediate | Should default to `llm_engines` plus `engram_lite`; full `engram` remains optional. |
| `agent_lib` | Inspectable agent orchestration, programming workflow, policy checks, and safety labs. | last | Policy gates are not sandboxing; use explicit sandbox/worktree boundaries where needed. |
| `course` | Teaching notebooks, starter projects, and curriculum manifest. | yes | `course/CURRICULUM.md` is the canonical notebook sequence. |
| `integration_tests` | Cross-package behavioral validation and memory/retrieval evaluation harnesses. | maintainers | Use these to prevent contract drift between packages. |

## Stabilization rule

When validation of teaching materials exposes package deficiencies, fix the package deficiency, then return to the teaching spine and update the docs/tests that depend on the changed behavior. Do not add a new teaching branch until the prior branch is green against its examples and smoke tests.
