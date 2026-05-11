# Quality Cleanup Plan

Last updated: 2026-05-11

## Status

All original phases complete. Active work has shifted to engine unification
and new backend development. See STATUS.md for the current priority order.

Recent broad gate (excluding test_performance.py):

    844 passed, 3 skipped in ~800s

## Phase 1 - Runtime lifecycle cleanup - DONE

Closed-state guards added to MemoryIngestor.apply() and
ProjectMemory.store_episode(). Readonly-database teardown warnings resolved.

## Phase 2 - Import-path cleanup - DONE

llm_engines confirmed on intentional direct layout. All other packages on
src/ layout. No production sys.path hacks remain. Codified in
tests/test_import_provenance.py.

## Phase 3 - Root package API simplification - DONE

engram/__init__.py if-chain replaced by 22-entry _LAZY_ATTRS table.
Dead code removed. Public API regression test added (tests/test_public_api.py).

## Phase 4 - Documentation consolidation - DONE

Four overlapping handoff docs collapsed into STATUS.md. PACKAGE_ROLES.md
and GITHUB_PUBLICATION_CHECKLIST.md corrected. QUALITY_CLEANUP_PLAN.md
updated to reflect completed phases.

## Phase 5 - God-class decomposition - DONE

project_memory.py: 3,251 to 1,941 lines.

Extracted modules:
- engram/src/engram/memory/result_types.py (TokenBudget, SynthesisHookConfig,
  ContextResult)
- engram/src/engram/memory/audit.py (run_remediation, _rem_* helpers)
- engram/src/engram/memory/synthesis.py (run_synthesis, build_synthesis_block,
  load_engine_config)
- engram/src/engram/prompt/__init__.py (new subpackage)
- engram/src/engram/prompt/helpers.py (wrap_memory_block, assemble_prompt,
  truncate_to_tokens, canonicalisation helpers, prompt-friendly formatters)
- engram/src/engram/prompt/builder.py (hierarchical_compress_text,
  build_prompt_core, build_prompt_trace_core)

## Phase 6 - Config over code - DONE

IngestionPolicy regex patterns extracted to memory/ingestion_patterns.yaml.
for_project_type() is now data-driven. Add languages/project-types by
editing YAML; no Python changes required.

## Phase 7 - Engine contract unification - DONE

ProjectMemory.respond() now routes through EngramLLMAdapter (preferred) or
legacy LLMEngine. Any llm_engines.ChatModel works directly with engram via
the adapter. New backends (NIM, AirLLM) only need one implementation.

## Phase 8 - Test infrastructure - DONE

MockEngine and CyclingFakeEngine centralised in engram/tests/harness/mocks.py.
Seven inline class definitions removed. conftest.py fake_engine fixture added.
61 unit tests added for prompt/helpers.py, prompt/builder.py, result_types.py.

## Next phases - see STATUS.md Active work section

Priority order:
1. NIM backend in llm_engines
2. Delete duplicate router/config_loader/discovery from engram/engine/
3. AirLLM backend (design first)
4. Hardware discovery update
5. engram_ui relocation
6. model_management.py decomposition
7. Move eval data to ~/.engram/eval/
8. Audit VISION.md / ROADMAP.md / LEARNING_PATH.md
9. Root cruft cleanup
10. Skill extraction for Engram
11. engram_lite parity check
