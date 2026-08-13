# Course curriculum manifest

This file is the canonical notebook sequence for the teaching layer. Keep `START_HERE.md`, `LEARNING_PATH.md`, `course/README.md`, and `scripts/check_teaching_artifacts.py` aligned with this list.

| Order | Notebook | Primary package focus | Status |
|---:|---|---|---|
| 00 | `course/notebooks/00_llm_fundamentals.ipynb` | LLM concepts, prompts | active |
| 01 | `course/notebooks/01_environment_setup.ipynb` | environment setup | active |
| 02 | `course/notebooks/02_engine_basics.ipynb` | `llm_engines`, `llm_harness_core` | active |
| 03 | `course/notebooks/03_inspecting_model_behavior.ipynb` | `llm_inspector`, `llm_inspector_ui` | active |
| 04 | `course/notebooks/04_memory_with_engram.ipynb` | `engram` | active |
| 05 | `course/notebooks/05_rag_with_rag_lib.ipynb` | `rag_lib` | scaffolded |
| 06 | `course/notebooks/06_advanced_rag_and_evaluation.ipynb` | `rag_lib`, `llm_inspector` | active |
| 07 | `course/notebooks/07_reference_app_walkthrough.ipynb` | `language_tutor` | scaffolded |
| 08 | `course/notebooks/08_agent_safety_and_failure_modes.ipynb` | `agent_lib` | scaffolded |
| 09 | `course/notebooks/09_evaluating_llm_applications.ipynb` | `llm_harness_core`, integration evaluation | scaffolded |

The recorded failure lab at
`course/failure_labs/evaluation_blind_spot/` supplements notebooks 03 and 09.
It is an offline exercise, not an additional notebook in the ordered sequence.

`engram` is the default teaching memory layer. Full `engram` is the advanced path for learners who need richer persistent memory behavior and are ready for the additional dependency and policy surface.
