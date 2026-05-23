# AGENT.md — ai_tools root

## Mission

Build and maintain `ai_tools` as a suite of reusable, local-first Python libraries that others can use to build their own LLM-based projects.

## Canonical orientation files

Read these first:

1. `docs/design/VISION.md`
2. `docs/internal/MEMBERSHIP.md`
3. `docs/internal/STATUS.md`
4. `docs/internal/PACKAGE_ROLES.md`
5. `docs/internal/QUALITY_CLEANUP_PLAN.md`

## Default package order

Use this order unless the task says otherwise:

1. `llm_harness_core`
2. `llm_engines`
3. `engram`
4. `llm_inspector`
5. `rag_lib`
6. `llm_inspector_ui`
7. `agent_lib`
8. `examples/`

## Safety and editing rules

- Preserve `engram` as the default teaching memory path.
- Treat full `engram` as the advanced memory path unless a task explicitly targets it.
- Do not broaden agent write permissions to make tests pass.
- Empty write allowlists must mean no writes.
- Keep examples runnable without live model access where practical.
- Update docs and validation scripts together when notebook names, course order, package layout, or install targets change.
- Keep default install/test paths lightweight; PyTorch and GPU stacks belong behind explicit ML/GPU targets.

## Verification commands

Use the narrowest command that validates the touched package first, then broader checks as needed:

```bash
python -m compileall -q agent_lib engram llm_inspector_ui scripts course
python -m pytest -q agent_lib/tests/test_programming_harness.py llm_inspector_ui/tests/test_rag_retrieval_ui.py
python scripts/check_teaching_artifacts.py
make -n install
make -n test-core
python scripts/check_publication_hygiene.py
```
