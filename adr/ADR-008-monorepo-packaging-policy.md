# ADR-008 — Monorepo Packaging and Import Policy

Status: Accepted
Date: 2026-05-08

## Context

The `ai_tools` repo contains multiple related Python packages. Package layouts became mixed during active development.

Current src-layout packages:

    agent_lib/src/agent_lib
    engram_lite/src/engram_lite
    llm_harness_core/src/llm_harness_core
    llm_inspector/src/llm_inspector
    llm_inspector_ui/src/llm_inspector_ui
    rag_lib/src/rag_lib

Current direct-layout packages:

    llm_engines/llm_engines
    engram/engram
    language_tutor/language_tutor

Mixed layout can cause import ambiguity when pytest collects from the monorepo root. Same-name outer project directories can shadow real implementation packages.

## Decision

The repo will move toward one packaging policy:

1. Importable packages should use `src/` layout.
2. Editable installs are the preferred development validation path.
3. Tests should not require manual `PYTHONPATH` for normal validation.
4. Root `conftest.py` may contain a temporary centralized pytest import bootstrap while mixed layouts remain.
5. Package-local `conftest.py` files must not compensate for package metadata or import-path problems.
6. Top-level package imports should be lightweight and should not initialize optional heavy systems.
7. Import provenance should be tested explicitly when package layout changes.

## Current implementation checkpoint

Latest broad gate:

    833 passed, 37 skipped in 34.90s

Package-local import bootstraps have been removed. Root `conftest.py` remains as the centralized transitional bootstrap for repo-root pytest collection.

## Editable install order

    python -m pip install -e ./llm_harness_core
    python -m pip install -e ./llm_engines
    python -m pip install -e ./engram
    python -m pip install -e ./engram_lite
    python -m pip install -e ./llm_inspector
    python -m pip install -e ./rag_lib
    python -m pip install -e ./llm_inspector_ui
    python -m pip install -e ./language_tutor
    python -m pip install -e ./agent_lib

## Remaining implementation order

Convert remaining direct-layout packages in separate, testable steps:

1. `llm_engines/src/llm_engines`
2. `language_tutor/src/language_tutor`
3. `engram/src/engram` and, if retained, `engram/src/engram_ui`

Do not convert every package in one commit.

## Validation standard

A package layout change is complete only when:

1. package metadata points to the new layout
2. tests import the package from the intended implementation file
3. editable install works in a clean environment
4. selected package tests pass
5. selected cross-package tests pass
6. docs and CI commands reflect the new layout

The broad package-local gate is documented in `NEXT_STEP.md` and `LLM_HANDOFF.md`.
