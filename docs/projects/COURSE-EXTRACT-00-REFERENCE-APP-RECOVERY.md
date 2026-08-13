# Reference-App Recovery for Course Extraction

**Status:** Complete for the notebook 07 default path.

The recovered `language_tutor` source matched the application API that
`course/notebooks/07_reference_app_walkthrough.ipynb` expected, but it targeted
obsolete engine-discovery and dual Engram/Engram Lite APIs. It now lives at
`examples/language_tutor_reference_app`, consistent with the repository rule
that domain applications are examples rather than reusable library packages.

## Changes

- Replaced obsolete discovery calls with current `llm_engines.discovery` facts.
- Collapsed the removed Lite/full memory split onto the current `engram` API.
- Added a dependency-light `build_reference_stack()` teaching boundary.
- Restored notebook 07 to the 11-notebook extraction set.
- Added the distribution to the wheel-installed portability proof.
- Made wheel builds operate on temporary source copies so the proof does not
  leave build metadata in the working tree.

## Validation

```text
reference-app tests:       106 passed, 45 skipped
notebook 07 default path:  passed
wheel-installed course:    passed (11 notebooks)
full repository pytest:    1086 passed, 305 skipped
```

The skips are explicit residual test debt rather than supported-path evidence:
the recovered synchronous route suite needs migration to the current HTTPX
transport, the optional voice subprocess suite needs bounded subprocess tests,
and live Ollama remains opt-in. None is exercised by notebook 07's default
reference-stack walkthrough.

## Deferred

The smaller `examples/language_tutor` and this full reference application have
different teaching roles today. Consolidation requires a concrete duplicate or
conflicting path; recovery alone does not authorize it.
