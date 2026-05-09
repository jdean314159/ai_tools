# ADR-008: Monorepo Packaging Policy

Status: Accepted  
Last updated: 2026-05-09

## Context

The ai_tools repo contains multiple installable or package-like components that are developed together but should behave as ordinary Python packages. Earlier direct-layout packages caused import ambiguity, namespace-package exposure, and subprocess CLI failures.

Recent stabilization converted the previously problematic direct-layout packages to `src/` layout:

    llm_engines/src/llm_engines
    language_tutor/src/language_tutor
    engram/src/engram
    engram/src/engram_ui

The broad package-local validation gate passed after this conversion and after restoring the `engram.engine` package surface.

## Decision

All installable ai_tools packages should use normal package metadata and `src/` layout unless there is a documented exception.

Production code must not require repo-root `PYTHONPATH` hacks. Development should use editable installs.

Examples:

    python -m pip install -e ./llm_engines
    python -m pip install -e ./language_tutor
    python -m pip install -e ./engram

## Validation requirements

Every package-layout change must run at least:

    tests/test_import_provenance.py
    affected_package/tests

Any change affecting subprocess CLI behavior must also validate that subprocesses can import the package from the active environment without inherited repo-local `PYTHONPATH`.

The full package-local gate is:

    tests/test_import_provenance.py
    llm_engines/tests
    language_tutor/tests
    agent_lib/tests
    engram_lite/tests
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

`engram/src/engram/__init__.py` uses lazy package-surface behavior. Keep it table-driven and minimal. Root package APIs should remain boring and predictable. Subpackages such as `engram.engine` must be reachable through normal Python package semantics.
