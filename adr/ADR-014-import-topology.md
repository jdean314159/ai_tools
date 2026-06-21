# ADR-014: Resolve `llm_engines` direct-layout import shadowing

**Date:** 2026-06-07
**Status:** Accepted
**Deciders:** Jeff Dean
**Related:** ADR-008 (monorepo packaging policy), `conftest.py` (repo-root test
bootstrap), `llm_engines/pyproject.toml`, `tests/test_import_provenance.py`

---

## Context

The repo assessment flagged "fragile import topology": repo-root `pytest`
collection can shadow the installed `llm_engines` with the in-tree package
directory, and `examples/diagnostics_agent` tests only resolve imports when run
via `cd examples/diagnostics_agent` (which `make test-diagnostics` and now the CI
core job both do). The recent hygiene pass made CI run diagnostics tests for the
first time, so CI now *depends* on that `cd` workaround.

Investigation shows this is not a loose end — it is a **standing violation of
ADR-008**, which is Accepted. ADR-008 states:

- all installable packages use `src/` layout unless a documented exception exists;
- production code must not require repo-root `PYTHONPATH` hacks.

Two facts contradict that:

1. **`llm_engines` is the one spine package still in direct layout.**
   `llm_engines/llm_engines/` (no `src/`), while every other spine package is
   `*/src/*`. ADR-008's own context section lists `llm_engines/src/llm_engines`
   as already converted — that conversion either never landed for this package or
   regressed.

2. **`llm_engines/pyproject.toml` sets `pythonpath = ["."]`** under
   `[tool.pytest.ini_options]`, injecting its own repo dir onto the path. This is
   precisely the repo-root path hack ADR-008 prohibits, and it is the mechanism
   by which the in-tree dir wins over the installed wheel during collection.

The repo-root `conftest.py` is a defensive countermeasure to this violation, not
a neutral bootstrap. It maintains `SOURCE_PACKAGE_EXPECTATIONS`, drops and
re-imports packages that resolve to the wrong location, and **raises `ImportError`
if a package's provenance is wrong**. Its own comments call it "temporary
protection against repo-root namespace shadowing … removable after all packages
use src layout." There is also a `tests/test_import_provenance.py` gate enforcing
provenance. So the machinery to detect and tolerate the problem exists; the
underlying layout fix does not.

Notably, `SOURCE_PACKAGE_EXPECTATIONS` covers the spine packages and
`examples.language_tutor` but **not** `examples.diagnostics_agent` — which is why
diagnostics collection is not protected at repo root and must be run via `cd`.

## Problem statement at decision time

The decision needed to bring import topology back into compliance with ADR-008,
so that:
- repo-root collection cannot shadow `llm_engines`;
- the conftest provenance-anchoring can eventually be deleted, not extended;
- CI does not silently depend on per-job `cd` workarounds that break when a new
  test job forgets them.

## Options

### Option A — Convert `llm_engines` to `src/` layout (compliance fix)

Move `llm_engines/llm_engines/` → `llm_engines/src/llm_engines/`, update
`pyproject.toml` (`packages.find` / `package-dir`), and **remove
`pythonpath = ["."]`**. This is the conversion ADR-008 already mandates and
claims happened.

- **Pros:** removes the root cause; brings the repo into compliance with its own
  accepted ADR; lets the conftest anti-shadowing block (`_anchor_source_packages`,
  `SOURCE_PACKAGE_EXPECTATIONS`) be deleted once `test_import_provenance.py`
  passes without it; no more direct-layout package in the tree; CI `cd` becomes a
  convenience, not a correctness requirement.
- **Cons:** moves the most-imported package in the repo; touches every relative
  path/import assumption keyed to `llm_engines/llm_engines`; requires a careful
  editable-reinstall across laptop and workstation (sync hazard); `git mv` history
  churn. Highest one-time effort.
- **Risk:** medium. Mechanical but wide blast radius. Mitigated by the existing
  `test_import_provenance.py` and the full ADR-008 package gate.

### Option B — Bootstrap `examples/diagnostics_agent` in the conftest (entrench)

Add `examples.diagnostics_agent` to `SOURCE_PACKAGE_EXPECTATIONS` and the source
paths so repo-root collection resolves it too, leaving `llm_engines` direct.

- **Pros:** smallest change; removes the diagnostics `cd` requirement; low risk.
- **Cons:** does the opposite of ADR-008 — entrenches the workaround the conftest
  itself says should be removable; the direct-layout violation and
  `pythonpath = ["."]` remain; the conftest grows instead of shrinking; every new
  example must be remembered-and-added here forever.
- **Risk:** low immediate, high long-term (permanent maintenance of the shadow
  guard; ADR-008 stays violated with no record reconciling the two).

### Option C — Status quo, documented

Keep direct layout and the `cd` workaround; document that repo-root collection of
`llm_engines`/diagnostics is unsupported and tests must run per-package.

- **Pros:** zero change.
- **Cons:** leaves an accepted-ADR violation in place; CI depends on the `cd`
  convention with no guard against a future job omitting it; the conftest's
  provenance machinery remains load-bearing indefinitely.
- **Risk:** low today, but it is the option most likely to produce a confusing CI
  failure later (a new job collects from root, shadows `llm_engines`, and the
  failure looks like a real test break).

## Decision

**Option A was accepted and implemented.** `llm_engines` moved to
`llm_engines/src/llm_engines`, its package metadata was updated, and the
package-local `pythonpath = ["."]` entry was removed. Import provenance tests
now enforce the converted layout.

Retiring the root conftest anchoring guard was evaluated separately and rejected.
Pytest importlib root collection can still create outer namespace packages from
package-named conftests. ADR-008 therefore retains the guard as a permanent,
deliberate compensating control.

## Consequences

- ADR-008 is true for the `llm_engines` package layout.
- The root conftest remains the documented namespace-shadowing guard.
- `make test-diagnostics` and the CI core job retain package-local working
  directories for clarity rather than import correctness.
- Editable installs must be refreshed after moving between revisions from before
  and after the layout conversion.

## Out of scope

- Any change to other spine packages (already `src/` layout).
- The `examples/language_tutor` and `examples/agent_coordination_teaching` layouts
  (unaffected; revisit only if they later shadow).
