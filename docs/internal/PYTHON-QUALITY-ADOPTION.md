# Python quality adoption

## Policy

The repository root owns the shared Ruff baseline. Adoption is deliberately
staged so formatting changes remain reviewable and are not mixed with behavioral
refactors. `make quality-python` is the enforced gate; its default scope is
`llm_harness_core/src` and `llm_harness_core/tests`.

The initial policy uses Ruff's conservative `E4`, `E7`, `E9`, and `F` rules,
100-character lines, and a Python 3.10 syntax target. Python 3.10 remains the
target while supported packages still advertise `requires-python = ">=3.10"`.
Changing that compatibility floor requires a separate decision.

To inspect another package without changing the enforced default:

```bash
make quality-python PYTHON_QUALITY_SCOPE="package/src package/tests"
```

To format an adoption candidate:

```bash
make format-python PYTHON_QUALITY_SCOPE="package/src package/tests"
```

## Baseline inventory

Measured with Ruff 0.15.15 before the first adoption pass. Counts use the root
policy where applicable; `llm_inspector` retains its equivalent nearest-package
configuration.

| Scope | Lint findings | Files needing format |
|---|---:|---:|
| `llm_harness_core` | 1 | 8 |
| `action_trajectory_loop_guard` | 0 | 4 |
| `reasoning_loop_guard` | 0 | 2 |
| `mail_lib` | 0 | 6 |
| `examples/diagnostics_agent` | 0 | 22 |
| `llm_inspector_ui` | 4 | 31 |
| `agent_lib` | 12 | 55 |
| `llm_inspector` | 25 | 33 |
| `rag_lib` | 28 | 30 |
| `llm_engines` | 53 | 58 |
| `engram` | 55 | 51 |
| `examples/language_tutor` | 11 | 8 |
| `examples/language_tutor_reference_app` | 5 | 34 |
| `examples/mail_assistant` | 1 | 13 |
| `scripts` | 5 | 26 |
| root `tests` | 3 | 37 |

These counts are an adoption queue, not a quality score. Formatting volume and
lint findings measure different things, and generated or historical material
may need an explicit exclusion rather than automatic rewriting.

## Adoption order

1. `llm_harness_core` — enforced in CI now.
2. Loop guards and `mail_lib` — zero lint findings and small format-only diffs.
3. `llm_inspector_ui` — small lint correction before formatting.
4. `agent_lib`, `llm_inspector`, and `rag_lib` — review package by package.
5. `llm_engines` and `engram` — largest active-library cleanup sets.
6. Examples, scripts, and root integration tests — classify generated and
   historical files before adoption.

Each adoption commit must run that package's tests plus the repository gate.
Do not combine formatting with API renames or structural refactors.
