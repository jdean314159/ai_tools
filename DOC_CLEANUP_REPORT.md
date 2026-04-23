# Documentation cleanup report

## Updated active documents

- `README.md`
- `VISION.md`
- `CURRENT_STATE.md`
- `ROADMAP.md`
- `ADR_INDEX.md`
- `docs/architecture_v2.md`
- `llm_engines/README.md`
- `engram_lite/README.md`
- `llm_inspector/README.md`
- `llm_inspector_ui/README.md`
- `rag_lib/README.md`

## Normalized package README names

- `engram_lite/README_engram_lite.md` -> `engram_lite/README.md`
- `llm_inspector/README_llm_inspector.md` -> `llm_inspector/README.md`
- `llm_inspector_ui/README_llm_inspector_ui.md` -> `llm_inspector_ui/README.md`

## Moved to historical archive

- `README_ai_tools.md` -> `docs/history/README_ai_tools.md`
- `AI-Toolkit-Dev-Log.md` -> `docs/history/AI-Toolkit-Dev-Log.md`
- `rag_lib_build_plan.md` -> `docs/history/rag_lib_build_plan.md`
- `llm_engines/README_llm_engines_draft.md` -> `docs/history/README_llm_engines_draft.md`
- `language_tutor/Documentation/*` -> `docs/history/language_tutor_legacy/`

## ADR status reconciliation

- `adr/ADR-006-interoperability-core.md` updated from `Proposed` to `Accepted`

## Intent

The root and package `README.md` files are now the active documentation path.
Older planning and transition-era documents were removed from that path so they do not compete with the current architecture documents.
