# ADR-008: Monorepo Packaging Policy

Status: Accepted  
Last updated: 2026-06-08
Superseded-in-part-by: none; re-affirmed by ADR-014 (`llm_engines` `src/` conversion)

## Context

The ai_tools repo contains multiple installable or package-like components that are developed together but should behave as ordinary Python packages. Earlier direct-layout packages caused import ambiguity, namespace-package exposure, and subprocess CLI failures.

At the time of the original decision, stabilization had converted the
previously problematic direct-layout packages to `src/` layout:

    llm_engines/src/llm_engines
    language_tutor/src/language_tutor
    engram/src/engram
    engram/src/engram_ui

The broad package-local validation gate passed after that conversion and after
restoring the then-current `engram.engine` package surface. That surface was
later removed by the ADR-009 consolidation.

> Update (2026-06-08, ADR-014): The layout above reflects the state at this
> ADR's original date. The tree subsequently drifted: `llm_engines` reverted to
> direct layout (`llm_engines/llm_engines`) and `language_tutor` moved to
> `examples/language_tutor`. ADR-014 re-converted `llm_engines` to
> `llm_engines/src/llm_engines` and removed its `pythonpath = ["."]` hack,
> restoring compliance with this ADR. On 2026-06-08, package-level
> `pythonpath = ["src"]` settings were also removed from `agent_lib` and
> `engram`; their isolated suites remained green through editable installs.
> Direct imports then resolved every spine package under its `src/` directory,
> but anchoring-off targeted pytest collection still loaded outer namespace
> packages for `llm_engines`, `llm_inspector`, `llm_inspector_ui`, `agent_lib`,
> and `rag_lib`. A follow-up probe removed the root `pytest.ini` `pythonpath`
> block while anchoring was disabled, but pytest still preloaded outer namespace
> modules for `llm_engines`, `llm_inspector_ui`, `agent_lib`, and `rag_lib`
> before `pytest_configure`; only `llm_inspector` resolved normally in that
> probe. The `pythonpath` block was therefore not the sole shadow source and was
> restored for the valid source paths while its stale entries were removed.
>
> Follow-up (2026-06-08): The proposed two-lever conftest fix was tested and
> rejected at its required guard-off gate. Adding `tests/__init__.py` to anchor
> package conftests produced a real `tests.conftest` plugin-name collision
> between package suites. Converting the five affected projects to explicit,
> complete package lists did produce setuptools finder-based editable installs,
> but Python's normal `PathFinder` still discovered the repository-root outer
> directories as namespace packages first when commands ran from the monorepo
> root. Direct root imports then resolved with `__file__ = None`, and the
> `llm_inspector` monorepo-root import smoke test failed. Those packaging and
> conftest changes were rolled back, the editable installs were rebuilt, and
> source-package imports again resolve under each project's `src/` directory.
> The root anchoring guard is retained as the deliberate compensating control
> for importlib root-collection namespace shadowing. Guard retirement was
> attempted and rejected on cost/benefit grounds: the available alternatives
> either introduce conftest collisions or regress ordinary repository-root
> imports. This is a closed architecture decision, not pending cleanup.

## Decision

All installable ai_tools packages should use normal package metadata and `src/` layout unless there is a documented exception.

Production code must not require repo-root `PYTHONPATH` hacks. Development should use editable installs.

Repository-root pytest collection must retain the source-package anchoring guard
in `conftest.py`. The guard is test infrastructure for a measured importlib
collection behavior, not a production import dependency.

Examples:

    python -m pip install -e ./llm_engines
    python -m pip install -e ./examples/language_tutor
    python -m pip install -e ./engram

## Validation requirements

Every package-layout change must run at least:

    tests/test_import_provenance.py
    affected_package/tests

Any change affecting subprocess CLI behavior must also validate that subprocesses can import the package from the active environment without inherited repo-local `PYTHONPATH`.

The full package-local gate is:

    tests/test_import_provenance.py
    llm_engines/tests
    examples/language_tutor/test_language_tutor.py
    agent_lib/tests
    engram/tests
    llm_inspector_ui/tests
    llm_inspector/tests
    rag_lib/tests
    llm_harness_core/tests
    engram/tests --run-engram

## Hygiene requirements

Generated artifacts must not be committed:

    .pytest_cache
    __pycache__
    *.pyc
    *.egg-info
    *.patch
    generated archives

Run before commit:

    rm -rf .pytest_cache
    find . -type d -name '__pycache__' -prune -exec rm -rf {} +
    find . -type f -name '*.pyc' -delete
    find . -type d -name '*.egg-info' -prune -exec rm -rf {} +

    PYTHONDONTWRITEBYTECODE=1     python scripts/check_publication_hygiene.py

## Consequences

Positive:

- fewer ambiguous imports,
- better subprocess behavior,
- easier editable-install workflow,
- cleaner CI/publication story,
- less reliance on path mutation.

Tradeoff:

- tests and scripts must be explicit about package installation and test-only path setup.
- editable installs may create `*.egg-info`; this is expected locally but must be removed before publication hygiene and commit.

## Current exception/attention area

`engram/src/engram/__init__.py` defines the supported package surface. Keep it
minimal and predictable; removed historical subpackages must not be cited as
current validation requirements.
