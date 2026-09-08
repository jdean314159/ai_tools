# Repository Assessment: `ai_tools`

## Executive Verdict

`ai_tools` is a modular, local-first LLM harness + observability suite. I reviewed the canonical architecture/status docs and inspected the core stable/beta packages end-to-end: `llm_harness_core` (contracts), `llm_engines` (all five backends + router + factory), `engram` (project memory, trust policy, semantic graph, prompt builder), `llm_inspector`, `agent_lib` (runtime/tools), `rag_lib`, and `mail_lib`.

**No high-confidence, currently-actionable defect was found.** The code is well-structured, defensive, and internally consistent. The test suite passes cleanly (28 harness-core, 458 llm_engines+agent_lib, 217 engram+rag+inspector+ui; the remainder are optional-tier skips). The many "defects" flagged in the repo's own STATUS.md are historical, already-fixed, and disclosed — not current. I therefore report **low remaining uncertainty** and no validated defect.

## What I inspected (and confirmed healthy)

- **`llm_engines/backends/openai.py`** — tool-call history replay uses `json.dumps` (valid JSON, not Python `str(dict)`); logprobs/streaming/tool-call reassembly are bounded and typed. `is_cloud` policy correctly gates cloud sanitization.
- **`llm_engines/backends/llamacpp.py`** — chat/embedding mode is mutually exclusive via constructor flag; `/no_think` suppression and think-block stripping are consistent.
- **`llm_engines/backends/ollama.py`** — capability reporting (`embeddings=True`) matches the actual `/api/embed` path; logprobs gated behind version check.
- **`llm_engines/backends/vllm.py`** — model resolution, OOM classification, batch generation via asyncio.
- **`llm_engines/router.py`** — FailoverEngine circuit-breaking, OOM token reduction, cloud sanitization all consistent; `_classify` error taxonomy is reasonable.
- **`engram/trust.py`** — `MemoryTrustPolicy` fails closed on missing tenant/trust; `parse` guards against bool-as-int coercion.
- **`engram/project_memory.py`** — ingestion + composition + recall trust enforcement is coherent; temporal filtering suppresses superseded predecessors; storage paths are single-component + 0700/0600.
- **`engram/prompting/builder.py`** — token-budget compression is bounded and deterministic; evidence provenance is attributed.
- **`engram/storage/chromadb_store.py`** — dimension validation, metadata sanitization, atomic-ish writes.
- **`engram/semantic/graph.py`** — JSON persistence uses atomic `os.replace`.
- **`agent_lib/runtime.py` + `tools.py`** — tool invocation is exception-bounded; policy/observability classification matches the documented agent_lib probe.

## Rejected / downgraded hypotheses

- **Ollama `embed()` dimension claim**: `OllamaEngine.get_capabilities()` reports `embeddings=True` and `embed()` calls `/api/embed` — consistent, not a lie. (Downgraded.)
- **`check_ollama_logprobs_support` optimistic `return True` on failure**: documented as "cannot check → optimistic"; not a current defect, a deliberate conservative default. (Downgraded.)
- **STATUS.md "invalid exact-text scorer", "tool_not_granted misclassification", "archive defect", "version-1 infrastructure-invalid"**: all historical, withdrawn, and disclosed. Not current. (Discarded.)
- **`is_cloud` sanitization gaps**: sanitization is intentionally minimal (marker-based) and documented; not a correctness defect in the harness. (Downgraded.)

## Commands / tests run

```
cd /workspace
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 /venv/bin/python -m pytest llm_harness_core/tests/ -q   -> 28 passed
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 /venv/bin/python -m pytest llm_engines/tests/ agent_lib/tests/ -q  -> 458 passed, 14 skipped (3 fork DeprecationWarnings)
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 /venv/bin/python -m pytest engram/tests/ rag_lib/tests/ llm_inspector/tests/ llm_inspector_ui/tests/ -q  -> 217 passed, 254 skipped
```
Note: the repo's own `.venv` is broken (its `python` symlink resolves to a missing `/home/cybernaif/repos/ai_tools/.venv/bin/python3.13`); I used the system `/venv` (Python 3.13.15, pytest 9.1.1) instead.

## Remaining uncertainty & uninspected areas

- **Optional-tier code not executed**: GPU/torch, sentence-transformers, neural-memory (RTRL), and any backend requiring live servers were skipped by design; behavior there is unverified.
- **Live/networked paths** (real OpenAI/Anthropic/vLLM/Ollama servers) could not be exercised in this offline sandbox.
- **`mail_lib`/`examples`** were lightly skimmed, not deep-reviewed; the mail_assistant is a retired case study.
- **Packaging/publication hygiene** (`scripts/`, `THIRD_PARTY_NOTICES.md`) was reviewed only at a high level.
- I did not attempt to construct adversarial inputs against the trust policy or path-validation beyond reading the code; the enforcement looks correct but is not empirically proven here.

**Overall: no validated current defect. Low remaining uncertainty.**
