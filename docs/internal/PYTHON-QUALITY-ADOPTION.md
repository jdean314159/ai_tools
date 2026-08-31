# Python quality adoption

## Policy

The repository root owns the shared Ruff baseline. Adoption is deliberately
staged so formatting changes remain reviewable and are not mixed with behavioral
refactors. `make quality-python` is the enforced gate; its default scope is
`llm_harness_core`, both loop-guard packages, `mail_lib`, `llm_inspector_ui`,
`agent_lib`, `llm_inspector`, `rag_lib`, `llm_engines`, and `engram`.

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
| `action_trajectory_loop_guard` | 0 | 0 (adopted) |
| `reasoning_loop_guard` | 0 | 0 (adopted) |
| `mail_lib` | 0 | 0 (adopted) |
| `examples/diagnostics_agent` | 0 | 0 (adopted) |
| `llm_inspector_ui` | 0 | 0 (adopted) |
| `agent_lib` | 0 | 0 (adopted) |
| `llm_inspector` | 0 | 0 (adopted) |
| `rag_lib` | 0 | 0 (adopted) |
| `llm_engines` | 0 | 0 (adopted) |
| `engram` | 0 | 0 (adopted) |
| `examples/language_tutor` | 0 | 0 (adopted) |
| `examples/language_tutor_reference_app` | 0 | 0 (adopted) |
| `examples/mail_assistant` | 0 | 0 (adopted) |
| `examples/agent_coordination_teaching` | 0 | 0 (adopted after classification) |
| `examples/asc_probe` harness | 0 | 0 (adopted; generated `runs/` excluded) |
| top-level example probes | 0 | 0 (adopted; live evidence not rerun) |
| `scripts` | 5 | 26 |
| root `tests` | 3 | 37 |

These counts are an adoption queue, not a quality score. Formatting volume and
lint findings measure different things, and generated or historical material
may need an explicit exclusion rather than automatic rewriting.

## Adoption order

1. `llm_harness_core` — adopted and enforced in CI.
2. Loop guards and `mail_lib` — adopted and enforced in CI.
3. `llm_inspector_ui` — adopted and enforced in CI.
4. `agent_lib` — adopted and enforced in CI.
5. `llm_inspector` — adopted and enforced in CI.
6. `rag_lib` — adopted and enforced in CI.
7. `llm_engines` — adopted and enforced in CI.
8. `engram` — adopted and enforced in CI.
9. `examples/diagnostics_agent` — adopted and enforced in CI.
10. `examples/language_tutor` — adopted and enforced in CI.
11. `examples/mail_assistant` — adopted and enforced in CI.
12. `examples/agent_coordination_teaching` — adopted and enforced in CI.
13. `examples/language_tutor_reference_app` — adopted and enforced in CI.
14. `examples/asc_probe` harness — adopted; generated `runs/` evidence remains excluded.
15. Top-level example probes — adopted; compilation verified without rerunning live experiments.
16. Remaining examples, scripts, and root integration tests — classify generated
    and historical files before adoption.

Each adoption commit must run that package's tests plus the repository gate.
Do not combine formatting with API renames or structural refactors.
