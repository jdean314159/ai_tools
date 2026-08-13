# Course repository split dependencies

This inventory freezes the current teaching layer's dependencies on files
outside `course/`. Package imports are expected to become ordinary installed
dependencies after a split; file references need an explicit copy, fixture, or
link decision.

## External file references

| Course consumer | Current repository file | Split treatment |
|---|---|---|
| `failure_labs/evaluation_blind_spot/build_fixture.py` | `examples/asc_probe/runs/asc02_worker_only/live_probe_results.json` | Maintainer-only provenance input. Ship the built fixture; either copy the source report into a private build-data process or disable rebuilding in the student repo. |
| Notebook 05 | `docs/tutorials/broken_rag_lab.md` | Copy the tutorial into the course repo or replace with a versioned toolkit-doc link. |
| Notebook 06 | `llm_harness_core/EVALUATION_WALKTHROUGH.md` | Copy the teaching walkthrough or use a versioned package-doc link. |
| Notebook 08 | `agent_lib/examples/agent_red_team_lab.py` | Package as an installed example/fixture or copy a course-owned runner. |
| Notebook 08 | `docs/tutorials/agent_red_team_lab.md` | Copy the tutorial or use a versioned toolkit-doc link. |
| Notebook 09 | `llm_harness_core/EVALUATION_WALKTHROUGH.md` | Same decision as notebook 06; do not duplicate two copies. |
| Notebook 09 | `tests/integration_tests/memory_eval.py` | Replace with a course-owned evaluation fixture/script; do not depend on a package test path. |

**Resolved:** all seven file references above have been removed from
student-facing course content. The fixture builder now requires an explicit
maintainer-only source path and the committed bundle remains usable without it.

**Open — replacement lesson:** Notebook 07 exposed a larger issue than a file
reference: its imports target a
retired `language_tutor` application shape, while the current installable
example exposes `examples.language_tutor`. It is retained as source material
but explicitly excluded from the split rather than falsely declared portable.

**Resolved locally; external release prerequisite remains:** Notebook 01 now
installs the exact versions in `requirements.txt`, with a temporary
monorepo-compatible requirements-file lookup. The wheel-installed portability
gate passes, but distribution publication or a maintained wheelhouse remains
required for a clean network install.

## Runtime package dependencies

The notebooks import `llm_harness_core`, `llm_engines`, `llm_inspector`,
`llm_inspector_ui`, `engram`, `rag_lib`, and `agent_lib`. These are package
dependencies, not files to copy. The split project must freeze compatible
versions and test installation without the monorepo on `PYTHONPATH`.

## Gate for the eventual split

Before moving the directory, the course must pass with repository-root file
access disabled. No notebook or checker may resolve `docs/`, `examples/`,
package source trees, or `tests/` through the former monorepo layout.
