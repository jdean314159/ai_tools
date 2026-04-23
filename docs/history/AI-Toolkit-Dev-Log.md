# AI Toolkit - Development Log

**Started:** 2026-04-13
**Status:** Active
**Location:** ~/ai_tools/ai-toolkit/

---

## Project Overview

Three-library toolkit built on lessons from Engram, Spanish tutor, and ASC.

| Library | Layer | Status |
|---------|-------|--------|
| `llm-engines` | Foundation (1) | Design phase |
| `engram` | Core capabilities (2) | v0.1.19+ existing |
| `llm-inspector` | Observability (3) | Design phase |

Dependency direction: `llm-engines → Engram → llm-inspector`

---

## ADR Index

| ADR | Topic | Status |
|-----|-------|--------|
| ADR-001 | Engine Capability Model | ✅ Accepted 2026-04-13 |
| ADR-002 | Engine Response Schema | ✅ Accepted 2026-04-13 |
| ADR-004 | Engram Retrieval Policy | ✅ Accepted 2026-04-13 |
| ADR-005 | Persistence & Migration (Minimal) | ✅ Accepted 2026-04-13 |

Phase 2 ADRs (deferred): ADR-003 Tool Execution, ADR-006 Config Precedence, ADR-007 Trace Redaction, ADR-008 Sandbox Hardening, ADR-009 Secret Storage, ADR-010 Agent Session Lifecycle, ADR-011 Concurrency, ADR-012 Provenance.

---

## Decisions

### 2026-04-13 - Contract architecture established

**Decision:** Replace the informal `LLMEngine` ABC (returning `str`) with Protocol-based contracts returning `GenerationResponse`.

**Rationale:** The `llm-engines-design.md` ABC and the `contracts-design-corrected.md` Protocols were incompatible. The Protocol approach is adopted as normative. No code should be written against the old ABC.

**Files:** `contracts/engine.py`, `contracts/tools.py`, `contracts/discovery.py`, `contracts/__init__.py`

---

### 2026-04-13 - Exception hierarchy added

**Decision:** Defined `LLMEngineError` base plus six subclasses in `contracts/engine.py`.

**Hierarchy:**
```
LLMEngineError
├── BackendUnavailableError   (Ollama not running, API unreachable)
├── ModelNotFoundError        (model not loaded / not in catalog)
├── ContextLengthExceededError
├── RateLimitError            (cloud APIs)
├── GenerationError           (OOM, CUDA error mid-generation)
└── EngineConfigError         (bad constructor arguments)
```

**Rationale:** Without this, each backend raises different exceptions and callers can't handle failures uniformly.

---

### 2026-04-13 - Async streaming added as separate Protocol

**Decision:** Added `AsyncStreamingModel` (yields `AsyncIterator[str]`) alongside `StreamingModel` (yields `Iterator[str]`).

**Rationale:** The Spanish tutor and any FastAPI backend need async streaming. Synchronous `Iterator` blocks the event loop. Backends declare which variant they support. `OllamaEngine` implements sync; `AnthropicEngine` and `vLLMEngine` implement async.

---

### 2026-04-13 - `UsageStats.latency_ms` changed to `float`

**Decision:** Changed from `int` to `float`.

**Rationale:** Fast local inference (Ollama, llama.cpp) can return in under a millisecond. Integer truncation loses meaningful precision.

---

### 2026-04-13 - `GPU.compute_capability` changed to `list[int]`

**Decision:** Changed from `tuple[int, int]` to `list[int]` with `min_length=2, max_length=2`.

**Rationale:** Pydantic v2 will serialize `tuple` to a JSON array, but deserialization reconstructs a `list`, not a `tuple`. Using `list[int]` directly avoids the round-trip mismatch. Documented constraint enforces exactly two elements.

---

### 2026-04-13 - `ModelRegistry` note on VRAM data source

**Decision:** VRAM requirements (`min_vram_mb`, `recommended_vram_mb`) must come from a bundled `model_catalog.yaml`, not the Ollama API.

**Rationale:** Ollama's `/api/tags` endpoint returns model name and disk size only, not VRAM requirements. A static catalog is required. Implementation must merge live backend data (available models) with static catalog data (VRAM requirements). `ModelNotFoundError` is raised if a model is in Ollama but absent from the catalog.

**Status:** `llm_engines/data/model_catalog.yaml` created (277 lines, Ollama + HuggingFace entries).

---

### 2026-04-13 - TurboQuant package selection

**Decision:** Use `turboquant` (0.2.0, `pip install turboquant`) as the primary KV cache compression package. Also note `turboquant-vllm` for the vLLM backend.

**Findings:**
- Multiple independent community implementations on PyPI (all Alpha, Development Status 3)
- Google's official implementation expected Q2 2026
- `turboquant` targets HuggingFace models: `TurboQuantCache` is a drop-in for `past_key_values`
- `turboquant-vllm` uses fused Triton kernels with reported 3.7x faster decode on RTX 4090

**Risk:** All packages are community-authored Alpha implementations. Validate benchmarks on RTX 3090 (24GB) before committing the optimization layer to the design. If behavior is unstable, TurboQuant support can be gated behind an optional install extra without breaking the base engine contracts.

**Deferral option:** If TurboQuant proves unstable before Week 3, the `OptimizedEngine` hierarchy can be dropped entirely without touching the Protocol contracts. Speculative decoding via `transformers`' built-in `AssistantModel` API remains viable independently.

---

### 2026-04-13 - RAGPipeline canonical location

**Decision:** `RAGPipeline` Protocol is defined in `contracts/` only. `llm-inspector` imports from `contracts`, not the reverse.

**Rationale:** Having both `contracts/` and `llm_inspector/adapters.py` define `RAGPipeline` was identified as an interface drift risk. The contracts module is normative.

**Action:** Add `contracts/rag.py` when llm-inspector Phase 1 begins (Week 7).

---

### 2026-04-13 - Bug review findings and fixes applied

Ten issues found in systematic review. Five fixed immediately; five required manual patches. Critical bugs:

1. `_detect_gpus_nvidiasmi` — `[[line.split(",")]]` double-nested list. `parts[0]` was a list, not a string. Fixed to explicit loop.
2. `_extract_usage` / `_debug_payload` — `getattr(dict, ...)` always returns None. Fixed to `dict.get(...)`.
3. `MockEngine.generate()` — didn't reject empty messages. Conformance test would fail. Fixed.
4. `_post_json` — missing `raise AssertionError("unreachable")` after `_handle_http_error`. Fixed.
5. `_verify_model` — prefix match `qwen3` matched `qwen3:8b` when requesting `qwen3:27b`. Fixed to exact-match-first with single-match prefix fallback.
6. `FailoverEngine.generate()` — `last_error=None` when all engines in cooldown. Fixed with early exit.
7. `contracts/__init__.__all__` — `LogprobModel`, `CompressionStrategy`, `TokenLogprob`, `LogprobResult` absent. Fixed.
8. `pyproject.toml` — `openai` not listed as dependency for Ollama logprobs. Added `ollama-logprobs` extra.
9. `test_config_loader.py` — unused `user_config_path` import after our path edit. Fixed.
10. `test_ollama_backend.py` (GPT) — mocked `_FakeClient` (ollama package) but our engine uses urllib. Rewritten to patch `urllib.request.urlopen`.

---

### 2026-04-13 - vLLMEngine model resolution strategy

**Decision:** `vLLMEngine._resolve_model()` queries `/v1/models` at startup and resolves the best match, because vLLM reports its own model ID (e.g. `Qwen/Qwen2.5-32B-Instruct-AWQ`) which may differ from the short alias configured in YAML (e.g. `qwen-32b-awq`). Suffix match is used as fallback. If discovery fails, the configured name is used — this allows the engine to be constructed even when vLLM isn't running yet, and will fail naturally on the first generate() call.

---

### 2026-04-13 - vLLMEngine batch via asyncio gather

**Decision:** `generate_batch()` fans out all requests via `asyncio.gather()` rather than submitting them to vLLM's batch endpoint. vLLM's continuous batching handles this automatically server-side. The client-side `gather` simply maximises concurrent inflight requests. `nest_asyncio` / thread pool fallback handles the case where `generate_batch()` is called from inside an already-running event loop (e.g. from a FastAPI endpoint).

---

### 2026-04-13 - Spanish tutor integration approach confirmed

**Decision:** Tutor integration is a 2–3 hour hands-on task, not automated. The integration guide (`docs/tutor-integration.md`) covers all touch points. Key architectural point: `OllamaEngine` implements `StreamingModel` (sync), not `AsyncStreamingModel`. For FastAPI SSE streaming, the sync iterator must be run in a thread pool via `loop.run_in_executor()`. If true async streaming becomes a bottleneck, switching the executor to `vLLMEngine` (which implements `AsyncStreamingModel`) eliminates the thread pool overhead.

---



**Findings:**

1. `engram/engine/discovery.py` uses raw urllib (no ollama package). Adopted this approach in `llm_engines/discovery.py`. Added `ensure_ollama_model()`, `check_ollama_logprobs_support()`, `available_engines()`.

2. `engram/engine/ollama_engine.py` has `num_gpu` for CPU layer split-offload and `ensure_model_pulled()`. Both incorporated into our `OllamaEngine`. `num_gpu=40` is the proven config for Qwen 32B on the RTX 3090.

3. `LogprobResult` / `TokenLogprob` from `engram/engine/base.py` promoted to `contracts/engine.py` as a new `LogprobModel` Protocol. Engram's RTRL surprise filter depends on these.

4. `engram/engine/router.py` + `config_loader.py` have a mature failover/circuit-breaker/profile system. Ported to `llm_engines/router.py` + updated `factory.py`.

5. `engram/memory/retrieval.py` `UnifiedRetriever` is substantially more sophisticated than ADR-004 described: multi-weight scoring (lexical 0.50, importance 0.28, recency 0.16, density 0.06), synonym expansion before ChromaDB embedding query, neural affinity integration, near-duplicate suppression. ADR-004 documents the *policy surface*; UnifiedRetriever is the *implementation authority*.

6. `engram/engine/llm_engines.yaml` profile format adopted as canonical config format for `llm_engines`. Packaged default written to `llm_engines/data/llm_engines.yaml` with RTX 3090, RTX 2070, laptop, and tutor profiles.

---

### 2026-04-13 - FailoverEngine: OOM does not trip circuit breaker

**Decision:** On OOM, `FailoverEngine` reduces `max_tokens` and retries rather than recording a circuit breaker failure.

**Rationale:** OOM is not an engine health failure — the engine is working correctly; the request was too large. Tripping the breaker would incorrectly remove a healthy engine from rotation. The `reduce_output_on_oom=True` policy halves `max_tokens` on each OOM up to `min_max_tokens`.

---

### 2026-04-13 - Cloud sanitisation: memory blocks stripped before cloud engines

**Decision:** `FailoverEngine` applies `_sanitise_for_cloud()` to any engine flagged `is_cloud=True`. Markers like `--- retrieved context ---` are detected and stripped per `cloud_policy`.

**Rationale:** Engram retrieves personal/project memory into the prompt. Sending that to cloud APIs violates the local-first privacy posture. This is consistent with Engram's existing `utils/privacy.py` approach.

---



**Decision:** OllamaEngine calls the native Ollama `/api/chat` endpoint, not the OpenAI-compatible `/v1/chat/completions`.

**Rationale:** The OpenAI-compat endpoint ignores the `think: false` flag required to disable chain-of-thought on Qwen3 and other reasoning models. This was a previously discovered production issue. The native endpoint honours all options including `keep_alive=0` for multi-model VRAM management.

---

### 2026-04-13 - ModelRegistry falls back gracefully when Ollama is offline

**Decision:** `recommend_model()` sets `available_names = None` when Ollama is unreachable, then falls back to catalog-only filtering without raising.

**Rationale:** Hardware detection and model recommendation should work in offline/CI environments. The test harness exercises this path explicitly with `ollama_host="http://localhost:9"`.

---

### 2026-04-13 - pynvml preferred over torch.cuda for GPU detection

**Decision:** `detect_hardware()` tries pynvml first, torch.cuda second, CPU-only last.

**Rationale:** pynvml gives accurate VRAM readings without loading the full PyTorch runtime. On the RTX 3090 system, torch is always available, but pynvml is lighter for the discovery use case. Both are optional; the function never raises.

---



**Issue identified:** `engram-design.md` shows `EngramLLMAdapter.extract_entities()` calling `self.engine.generate(prompt)` and treating the return as `str`. This must be updated to use `GenerationRequest` / `GenerationResponse` when the adapter is implemented.

**Correct pattern:**
```python
request = GenerationRequest(
    messages=[ChatMessage(role="user", content=prompt)],
    max_tokens=512,
)
response = self.engine.generate(request)
return json.loads(response.message.content)
```

**Action:** Flag in Engram v0.2.0 work when implementing the LLM adapter.

---

## Known Gaps (Open Items)

| # | Gap | Blocking | Target |
|---|-----|----------|--------|
| G-001 | `agent-library-design.md` not written | Phase 2 agents | Phase 2 |
| G-002 | No ADRs written | ADR-001 review | Week 1-2 |
| G-003 | `contracts/rag.py` not written | llm-inspector Phase 1 | Week 7 |
| G-004 | ~~`llm_engines/data/model_catalog.yaml` not created~~ | ModelRegistry impl | ✅ Done |
| G-005 | `ai-toolkit-architecture-revised-corrected.md` not in repo | Architecture ref | Needs upload |
| G-006 | `MigrationRunner.self.db` undeclared class attribute | Migration contracts | Before ADR-005 |

---

## File Map

```
contracts/
├── __init__.py          ✅ 2026-04-13
├── engine.py            ✅ 2026-04-13
├── tools.py             ✅ 2026-04-13
├── discovery.py         ✅ 2026-04-13
├── rag.py               ⏳ Week 7
├── memory.py            ⏳ Phase 2
├── agent.py             ⏳ Phase 2
├── trace.py             ⏳ Phase 2
├── config.py            ⏳ Phase 2
├── migration.py         ⏳ Before ADR-005
├── concurrency.py       ⏳ Phase 2
└── provenance.py        ⏳ Phase 2

adr/
├── ADR-001-engine-capability-model.md   ✅ 2026-04-13
├── ADR-002-engine-response-schema.md    ✅ 2026-04-13
├── ADR-004-engram-retrieval-policy.md   ⏳ Week 2
└── ADR-005-persistence-migration.md     ⏳ Week 2

├── adr/
│   ├── ADR-001-engine-capability-model.md   ✅
│   ├── ADR-002-engine-response-schema.md    ✅
│   ├── ADR-004-engram-retrieval-policy.md   ✅
│   └── ADR-005-persistence-migration.md     ✅

llm_engines/
├── __init__.py          ✅ (exports StructuredOutputHandler, config_loader)
├── factory.py           ✅
├── router.py            ✅
├── token_counter.py     ✅
├── config_loader.py     ✅ (from GPT; path-corrected)
├── discovery.py         ✅
├── backends/
│   ├── mock.py          ✅ (empty-messages guard added)
│   ├── ollama.py        ✅ (dict.get fixes; normalize_host; verify_model fix)
│   ├── anthropic.py     ✅
│   ├── openai.py        ✅ (cloud + OpenAI-compat endpoints)
│   └── vllm.py          ✅ (model resolution; batch via asyncio.gather; logprobs)
├── utils/
│   └── structured_output.py  ✅ (from GPT; JSON extraction + schema prompts)
└── data/
    ├── model_catalog.yaml    ✅
    └── llm_engines.yaml      ✅

contracts/
├── engine.py            ✅
├── tools.py             ✅
├── discovery.py         ✅
└── rag.py               ✅ (Chunk, RAGResult, RAGPipeline Protocol)

engram/
├── adapters/
│   ├── __init__.py      ✅
│   └── llm_adapter.py   ✅ (EngramLLMAdapter; ExtractionResult schema)
└── (existing v0.1.19+)  ✅

llm_inspector/
├── __init__.py          ✅
└── rag.py               ✅ (RAGInspector, EngramRAGAdapter, ChromaDBRAGAdapter)

tests/
├── contract_tests/
│   ├── conftest.py          ✅
│   ├── test_chat_model.py   ✅
│   ├── test_mock_engine.py  ✅
│   ├── test_embedding_model.py ✅
│   └── test_anthropic_engine.py ✅
├── test_discovery.py        ✅
├── test_router.py           ✅
├── test_factory.py          ✅
├── test_config_loader.py    ✅
├── test_ollama_backend.py   ✅
├── test_structured_output.py ✅
├── test_llm_adapter.py      ✅
└── test_rag_inspector.py    ✅

engram/
└── (existing v0.1.19+)  ✅ active

llm_inspector/
└── (not started)        ⏳ Week 7
```

---

## Week-by-Week Plan

| Week | Focus | Status |
|------|-------|--------|
| 1-2 | ADR-001–005; contracts; llm-engines skeleton | ✅ Complete |
| 3-4 | OllamaEngine; discovery; FailoverEngine; factory profiles | ✅ Complete |
| 5-6 | AnthropicEngine; structured_output; config_loader; bug review | ✅ Complete |
| 7-8 | EngramLLMAdapter; RAGInspector v0.1; contracts/rag.py | ✅ Complete |
| 9-10 | OpenAIEngine; vLLMEngine; tutor integration guide; bug fixes | ✅ Complete |
| Next | Tutor integration (hands-on); course module drafts; Phase 2 planning | ⏳ |

---

## TurboQuant Reference

| Package | PyPI | Target | API |
|---------|------|--------|-----|
| `turboquant` 0.2.0 | ✅ | HuggingFace | `TurboQuantCache(bits=4)` |
| `turboquant-vllm` | ✅ | vLLM | Triton kernels |
| `turboquant-py` 0.1.0 | ✅ | NumPy/vectors | `TurboQuant(dim, bit_width)` |

Google official: expected Q2 2026. All current packages are community Alpha.

---

## Tags

#ai-toolkit #llm-engines #engram #llm-inspector #contracts #active
