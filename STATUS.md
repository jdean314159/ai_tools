# Repo Status

Last updated: 2026-05-11

Single source of truth for "where the repo is right now." See
QUALITY_CLEANUP_PLAN.md for the broader plan and ROADMAP.md for
longer-horizon direction.

## Package layout

Nine packages on `src/` layout:

    agent_lib/src/agent_lib
    engram/src/engram
    engram/src/engram_ui              (under engram/, not its own top-level)
    engram_lite/src/engram_lite
    language_tutor/src/language_tutor
    llm_harness_core/src/llm_harness_core
    llm_inspector/src/llm_inspector
    llm_inspector_ui/src/llm_inspector_ui
    rag_lib/src/rag_lib

One package intentionally on direct layout:

    llm_engines/llm_engines

`tests/test_import_provenance.py` codifies the direct layout for
`llm_engines`. This is a deliberate choice; `llm_engines` had no
import-ambiguity problem to fix.

## Validation

Last broad gate (excluding test_performance.py):

    844 passed, 3 skipped in ~800s

Full gate including test_performance.py adds ~100s for one test.
Skip during iteration:

    --ignore=engram/tests/harness/test_performance.py

Public API regression test (fast, run after any __init__.py change):

    python -m pytest tests/test_public_api.py -v --tb=short

## Completed work

### Original quality-hardening list (items 1-3, 5-6)

1. **Doc consolidation** - four handoff docs collapsed into STATUS.md;
   false llm_engines src/ claim corrected in PACKAGE_ROLES.md and
   GITHUB_PUBLICATION_CHECKLIST.md.

2. **project_memory.py god-class decomposition** - 3,251 to 1,941
   lines across two phases:
   - Phase A: TokenBudget, SynthesisHookConfig to memory/result_types.py;
     audit remediation to memory/audit.py; synthesis orchestration to
     memory/synthesis.py.
   - Phase B: prompt helpers to prompt/helpers.py; build_prompt,
     build_prompt_trace, _hierarchical_compress to prompt/builder.py;
     ContextResult to memory/result_types.py.
   - ProjectMemory is now a ~1,941-line orchestration facade.

3. **engram/__init__.py lazy-attr cleanup** - 50-line if-chain replaced
   by 22-entry _LAZY_ATTRS table + 7-line __getattr__. Dead
   if name == "engine" branch removed. tests/test_public_api.py added.

5. **IngestionPolicy regex to YAML** - hardcoded English/Spanish patterns
   extracted to memory/ingestion_patterns.yaml. for_project_type() is
   now data-driven; add languages/project-types by editing YAML only.

6. **respond() inspect.signature kludge removed** - LLMEngine ABC
   already enforces **kwargs; runtime inspection was dead code. Six
   non-conforming test doubles fixed.

### Engine unification (new items 1-3)

1. **respond() routes through EngramLLMAdapter** - ProjectMemory now
   accepts llm_adapter= (preferred) alongside llm_engine= (legacy).
   Any llm_engines.ChatModel works directly with ProjectMemory.respond()
   via the adapter - no parallel engram.engine implementation needed for
   new backends (NIM, AirLLM).
   - EngramLLMAdapter.generate() extended to accept temperature.
   - model_name passthrough added for fingerprinting.
   - resolve_neural_fingerprint walks into wrapped adapters.
   - Inline _OllamaAdapter in synthesis.py deleted.

2. **MockEngine centralised** - seven inline FakeEngine/CyclingFakeEngine
   class definitions removed from six test files. Both now live in
   engram/tests/harness/mocks.py:
   - MockEngine(response=...) - configurable fixed response.
   - CyclingFakeEngine(responses=[...]) - cycles through a list.
   - engram/tests/conftest.py created with fake_engine fixture.
   - Future contract changes to generate() require one edit, not six.

3. **Unit tests for prompt stack** - 61 new tests across:
   - test_prompt_helpers.py - all public functions in prompt/helpers.py.
   - test_result_types.py - TokenBudget, SynthesisHookConfig, ContextResult.
   - test_prompt_builder.py - hierarchical_compress_text all compression
     phases; _get_helper_map sanity checks.
   - Two production bugs surfaced and fixed:
     - wrap_memory_block now returns "" for whitespace-only input.
     - builder.py was missing logger definition and had two wrong relative
       imports (from .memory. should be from ..memory.).

## Active work - in priority order

1. **NIM backend in llm_engines** - NVIDIA NIM is OpenAI-compatible.
   Add llm_engines/backends/nim.py as a thin subclass of OpenAIEngine
   (different base URL, auth header, model name format). Register in
   EngineFactory; add config block to llm_engines.yaml. ~3 hours.

2. **Delete duplicate modules from engram/engine/** - router.py,
   config_loader.py, discovery.py exist in both engram/engine/ and
   llm_engines/. NOTE: three callers must be migrated first:
   - language_tutor/hardware_strategy.py → llm_engines.discovery
   - engram/memory/synthesis.py → llm_engines config loader
   - engram_ui/runtime_manager.py → llm_engines config loader
   Keep: model_manager.py, runtime_status.py, model_discovery.py,
   base.py (LLMEngine ABC), CLI commands.

3. **AirLLM backend** - design decision required first: standalone
   airllm_lib package (recommended) vs buried in llm_engines/backends/.
   AirLLM is not a server - it loads model shards layer-by-layer.
   Needs StreamingModel support and cold-start handling.

4. **Hardware discovery update** - extend llm_engines/discovery.py to
   recommend AirLLM when VRAM < 8GB and model size exceeds available VRAM.

5. **engram_ui relocation** - currently at engram/src/engram_ui/ inside
   engram's source tree. Should be engram_ui/src/engram_ui/ like every
   other package.

6. **model_management.py decomposition** - 1,702 lines; same god-class
   pattern as the original project_memory.py.

7. **Move eval data to ~/.engram/eval/** - engram/data/ accumulates 33MB
   of test artifacts in the working directory.

8. **Audit VISION.md / ROADMAP.md / LEARNING_PATH.md** - same drift risk
   as the handoff docs consolidated at the start of this work.

9. **Root cruft cleanup** - STATUS #9 files already removed. Remaining:
   - git rm Status.md (stale duplicate of STATUS.md, 2026-05-09)
   - git rm test_llm_adapter_path.py (exact duplicate of engram/tests/ copy)
   - git mv TASKS.json docs/history/task_manifests/ (all tasks done)
   - git mv one-shot scripts from scripts/ to docs/history/dev_scripts/:
     debug_memory_failures.py, generate_synthetic_data.py,
     run_answer_uplift_eval.py, summarize_answer_uplift.py,
     run_beginner_demo.py, run_test_survey.sh

10. **Skill extraction for Engram** - the Hermes Agent gap from VISION.md.
    procedural.py storage/retrieval is complete (FTS5+cosine hybrid).
    Phase B: extraction pipeline from episodic/semantic memory.
    Phase C: wire into ProjectMemory and UnifiedRetriever.
    ~2-3 days of focused work.

11. **engram_lite.ProjectMemory true facade migration** - ADR-007 is
    partially implemented. Submodule re-exports are done. The centerpiece
    project_memory.py (1,306 lines) is still parallel implementation.
    Migrating it to delegate to engram.ProjectMemory is the real work.
    This is not a parity check; it is the bulk of the ADR-007 migration.

12. **llm_harness_core rescope** - synthetic_data.py (355 lines) and
    evaluators.py (135 lines) are implementations, not contracts. Move
    synthetic_data.py to rag_lib or a dev utility; move evaluators.py
    to llm_inspector. Act before callers accumulate at the wrong layer.

13. **CI tooling gaps** - add to CI:
    - ruff linting gate (configs already exist in pyproject.tomls)
    - mypy type-checking gate
    - coverage reporting (--cov flag, not a hard gate initially)
    - hygiene script: add grep for shell=True and bare eval(/exec( in
      non-test Python; fail if found (establishes baseline pre-sandbox)

## Planned: mentor/worker coding loop (agent_lib)

Design agreed: Claude (API) as planner/reviewer, qwen3:32b (local Ollama)
as code executor. Loop: plan -> execute -> test -> review -> repeat.

Key dependency: sandboxed code execution (Docker subprocess) must be built
first. This is also required for course modules 3, 6, and 8.
First agent_lib module will be coding_loop.py + sandbox/docker_runner.py.

## Notes for next session

- llm_adapter= is the preferred path for new code. llm_engine= still
  works for backward compatibility.
- prompt/ is a new subpackage under engram/src/engram/. New prompt-assembly
  logic belongs there.
- ingestion_patterns.yaml controls IngestionPolicy patterns; edit it
  directly to add languages or project types.
- MockEngine and CyclingFakeEngine live in engram/tests/harness/mocks.py.
  Import from there; do not redefine inline.
- The 844-passed / 3-skipped gate is the current baseline.
