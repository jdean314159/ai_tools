# LLM Applications Course

A practical 10-week course on building LLM-based applications, with a focus on
local-first development using open-weight models.

## Philosophy

- **Local first.** Every concept is demonstrated with locally-hosted models via
  Ollama. Cloud APIs (Anthropic, OpenAI) are treated as drop-in alternatives,
  not requirements.
- **Toolkit-grounded.** Code examples use the `ai_tools` libraries directly.
  Students see real, tested code — not toy abstractions written for the slides.
- **Inspectable by default.** Applications should expose what they retrieved,
  what they remembered, and why they made a decision. Opacity is a bug.
- **Security-aware throughout.** LLM-generated code runs in containers. API
  keys stay in environment variables. Prompt injection is discussed early.

## Hardware

| Setup | Models available | Notes |
|---|---|---|
| Any browser | Colab T4 (15 GB) | Primary path for students without a GPU |
| 8 GB VRAM | `qwen3.5:9b`, `gemma3:4b` | Laptop discrete GPU |
| 16 GB VRAM | `qwen3.6:35b-a3b` | MoE, efficient on 16 GB |
| 24 GB VRAM | `qwen3.6:27b` | RTX 3090/4090 |

All exercises include a Colab fallback. Local Ollama is a one-line swap.

## Prerequisites

- Python basics: functions, classes, file I/O
- Comfort with the command line
- No prior ML or AI experience required

## Course Structure

`CURRICULUM.md` is the canonical manifest for notebook order and status.
`REPO_SPLIT_DEPENDENCIES.md` inventories monorepo file references that must be
resolved before extracting the course into its own repository.


| Notebook | Topic | Week | Toolkit |
|---|---|---|---|
| [00](notebooks/00_llm_fundamentals.ipynb) | LLM Fundamentals + Prompt Engineering | 1 | none |
| [01](notebooks/01_environment_setup.ipynb) | Environment Setup | 2 | none |
| [02](notebooks/02_engine_basics.ipynb) | Engine Abstraction | 3–4 | `llm_engines` |
| [03](notebooks/03_inspecting_model_behavior.ipynb) | Inspecting Model Behavior | 3–4 | `llm_inspector` |
| [04](notebooks/04_memory_with_engram.ipynb) | Memory | 5–6 | `engram` |
| [05](notebooks/05_rag_with_rag_lib.ipynb) | RAG Fundamentals | 7 | `rag_lib` |
| [06](notebooks/06_advanced_rag_and_evaluation.ipynb) | Advanced RAG + Evaluation | 8 | `rag_lib`, `llm_inspector` |
| [07](notebooks/07_reference_app_walkthrough.ipynb) | Reference App Walkthrough | 9 | all |
| [08](notebooks/08_agent_safety_and_failure_modes.ipynb) | Agent Safety + Failure Modes | 9 | `agent_lib` |
| [09](notebooks/09_evaluating_llm_applications.ipynb) | Evaluation + Capstone | 10 | `llm_harness_core` |
| [10](notebooks/10_context_engineering.ipynb) | Context Engineering + Inference Optimisation | 10–11 | `llm_engines`, `rag_lib`, `engram` |

## Starter Projects

Three minimal scaffolds for independent work after the notebooks:

- [`starter_projects/minimal_chat_app/`](starter_projects/minimal_chat_app/) —
  single-turn chat via `llm_engines`
- [`starter_projects/memory_tutor/`](starter_projects/memory_tutor/) —
  conversation with `engram` memory
- [`starter_projects/source_grounded_qa/`](starter_projects/source_grounded_qa/) —
  retrieval-backed Q&A with `rag_lib`

## Recorded failure labs

[`failure_labs/evaluation_blind_spot/`](failure_labs/evaluation_blind_spot/)
is an offline, no-GPU exercise built from a privacy-safe portable RunRecord
bundle. Students use Inspector to discover that completed runs and a healthy
headline metric conceal both a false-negative visible oracle and a
visible-pass/held-out-fail evaluation gap.

## Getting Started

```bash
# Install all packages into the shared venv
cd ~/ai_tools
make install

# Launch Jupyter
source ~/ai-env/bin/activate
pip install jupyter
jupyter notebook course/notebooks/00_llm_fundamentals.ipynb
```

For Colab: open any notebook and click the Colab badge at the top of the cell.
