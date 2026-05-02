# AGENT.md — ai_tools root

## Mission

Stabilize and evolve the `ai_tools` monorepo as a layered toolkit for local-first LLM applications, teaching materials, memory, retrieval, inspection, reference apps, and agent orchestration.

## Canonical orientation files

Read these first:

1. `VISION.md`
2. `PACKAGE_ROLES.md`
3. `CURRENT_STATE.md`
4. `course/CURRICULUM.md`
5. `TASKS.json`

## Default package order

Use this order unless the task says otherwise:

1. `llm_harness_core`
2. `llm_engines`
3. `engram_lite`
4. `llm_inspector`
5. `rag_lib`
6. `llm_inspector_ui`
7. `language_tutor`
8. `agent_lib`
9. `engram`

## Safety and editing rules

- Preserve `engram_lite` as the default teaching memory path.
- Treat full `engram` as the advanced memory path unless a task explicitly targets it.
- Do not broaden agent write permissions to make tests pass.
- Empty write allowlists must mean no writes.
- Keep examples runnable without live model access where practical.
- Update docs and validation scripts together when notebook names or course order changes.

## Verification commands

Use the narrowest command that validates the touched package first, then broader checks as needed:

```bash
python -m compileall -q agent_lib engram_lite llm_inspector_ui scripts course
python -m pytest -q agent_lib/tests/test_programming_harness.py llm_inspector_ui/tests/test_rag_retrieval_ui.py
python scripts/check_teaching_artifacts.py
python scripts/check_publication_hygiene.py
```
