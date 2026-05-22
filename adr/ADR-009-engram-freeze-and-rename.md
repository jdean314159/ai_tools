# ADR-009: Freeze engram, dissolve engram_lite, rename to engram

**Date:** 2026-05-22
**Status:** Accepted
**Supersedes:** ADR-007 (engram_lite as engram facade)

## Context

The monorepo contained two parallel memory libraries: `engram` (the original
integrated system, which received most active development) and `engram_lite`
(intended as the clean extracted component). Analysis in May 2026 showed:

1. The two libraries had functionally converged. The historical eval advantage
   of engram_lite was traced to a missing `vector_similarity_threshold` in
   engram, not to an architectural difference.

2. ADR-007 (engram_lite as a facade over engram) had been implemented, making
   engram_lite entirely hollow — every module was a re-export shim. There was
   no independent engram_lite implementation left in the monorepo.

3. The original standalone engram_lite implementation (v0.2.0) was recovered
   from a backup. It had: JSONL-as-source-of-truth, RRF hybrid retrieval,
   `vector_similarity_threshold=0.4` built in, no torch dependency by default.

4. An identical additive-decomposition problem existed in the engine layer:
   `engram/engine/` (~5,700 lines) and `llm_engines/` (~10,700 lines) ran
   in parallel. engram_ui depended on engram.engine, not llm_engines.

5. Jeff already maintained a separate GitHub repo (github.com/jdean314159/engram)
   from before the monorepo decomposition — the natural archive point.

## Decision

1. **Freeze engram.** No new feature development. The standalone repo at
   github.com/jdean314159/engram is the canonical archive, marked read-only.
   The `engram/` directory was removed from the monorepo.

2. **Restore the original standalone engram_lite implementation** into the
   `engram_lite/` tree, replacing the hollow facade.

3. **Rename `engram_lite` → `engram`.** The package name, import path, and
   directory are all `engram`. The `engram-lite` PyPI name is retired.

4. **Add two compat types** (`ProjectType`, `TokenBudget`) to bridge callers
   that imported them from the heavy engram.

5. **Add `build_prompt_interop`** with a module-level `build_interop_events`
   helper in `inspection.py` so the llm_inspector interop path works without
   the legacy `to_interop_events` reconstruction.

## Consequences

- Course materials and all packages use `import engram` — consistent with the
  intended teaching story.
- The new `engram` is lightweight by default: JSONL + optional ChromaDB,
  no torch, no neural layer, no cold/procedural storage.
- The frozen archive is available for reference.
- `engram_ui` still imports from `engram.engine.*` (now gone). It is broken
  until engine reconciliation migrates it to `llm_engines`. Tracked separately.
- The duplicate engine layer (`engram/engine/` vs `llm_engines/`) is the next
  major cleanup; deserves its own ADR once `engram_ui` migration is scoped.

## Alternatives considered

- **Keep engram_lite as a facade over engram (ADR-007).** Rejected: engram is
  frozen so it cannot be a live dependency.
- **Keep the name engram_lite.** Rejected: misleading for a full multi-layer
  system; `import engram` is cleaner for course materials.
- **Keep engram in the monorepo, mark frozen.** Rejected: pre-existing GitHub
  repo is the right archive; dead code in the monorepo adds noise.