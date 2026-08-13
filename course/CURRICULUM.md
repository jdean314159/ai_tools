# Course curriculum manifest

This file is the canonical notebook sequence for the teaching layer. Paths are
relative to the course root so the manifest survives repository extraction.
Keep `README.md` and the teaching checks aligned with this list.

| Order | Notebook | Primary package focus | Status |
|---:|---|---|---|
| 00 | `notebooks/00_llm_fundamentals.ipynb` | LLM concepts, prompts | active |
| 01 | `notebooks/01_environment_setup.ipynb` | environment setup | active |
| 02 | `notebooks/02_engine_basics.ipynb` | `llm_engines`, `llm_harness_core` | active |
| 03 | `notebooks/03_inspecting_model_behavior.ipynb` | `llm_inspector` | active |
| 04 | `notebooks/04_memory_with_engram.ipynb` | `engram` | active |
| 05 | `notebooks/05_rag_with_rag_lib.ipynb` | `rag_lib` | scaffolded |
| 06 | `notebooks/06_advanced_rag_and_evaluation.ipynb` | `rag_lib`, `llm_inspector` | active |
| 07 | `notebooks/07_reference_app_walkthrough.ipynb` | `language_tutor` reference app | active |
| 08 | `notebooks/08_agent_safety_and_failure_modes.ipynb` | `agent_lib` | scaffolded |
| 09 | `notebooks/09_evaluating_llm_applications.ipynb` | `llm_harness_core`, integration evaluation | scaffolded |
| 10 | `notebooks/10_context_engineering.ipynb` | `llm_engines`, `rag_lib`, `engram` | active |

The recorded failure lab at
`failure_labs/evaluation_blind_spot/` supplements notebooks 03 and 09.
It is an offline exercise, not an additional notebook in the ordered sequence.

`failure_labs/generation_provenance_gap/` supplements notebooks 02 and 03 with
a privacy-safe real local generation and an evidence-bounded reproducibility
exercise.

Notebook 07 uses the recovered `language-tutor` distribution after its engine,
memory, and reference-stack seams were rebuilt against current public APIs.

`engram` is the default teaching memory layer. Full `engram` is the advanced path for learners who need richer persistent memory behavior and are ready for the additional dependency and policy surface.
