# Engram TODO

## Completed
- [x] Phase 1: Hierarchical pressure valve in `build_prompt()`
- [x] Phase 2: Async event bus + MemoryDaemon (daemon.py, event_bus.py)
- [x] Phase 3: Tier 1 Reflex layer (regex gate, typed ReflexRelations, CPU-side classifier)
- [x] Phase 3b: Tier 2 Cognitive layer (async idle-time extraction, Gemma 4B via llama-server)
- [x] Phase 4: Replace Kuzu graph DB with SQLite semantic backend (three tables: facts, preferences, events; FTS5 full-text search)
- [x] Fix: `episode_threshold` 0.62 → 0.35 (ingestion.py)
- [x] Fix: `bypass_filter=False` → `True` in ingestion apply()
- [x] Fix: `project_type` → `general_assistant` in engine_factory.py
- [x] Fix: `base_url` remove `/v1` suffix for llama_cpp engines in llm_engines.yaml
- [x] Fix: collection_name mismatch in episodic episode count queries
- [x] Fix: Add `source` field to Preference schema (dropped silently in Kuzu; fixed naturally in SQLite)
- [x] Add gemma4_26b_moe engine entry to llm_engines.yaml
- [x] Add `health_check()` to ProjectMemory

## In Progress

- [x] Rewrite semantic_helpers.py with SQL queries — LanguageTutorHelpers, ProgrammingAssistantHelpers fully implemented; graph methods return [] with WARNING
      (ProgrammingAssistantHelpers, LanguageTutorHelpers, etc. — all currently return [])
- [x] Delete semantic_schema.py and semantic_search.py (802 lines dead code removed) after Kuzu removal

## Pending

### Memory
- [x] Cognitive/Reflex cross-tier dedup — CognitiveExtractor._is_duplicate() checks FTS+Jaccard ≥ 0.80 before write
- [x] Cognitive prompt quality — subject extraction rules now forbid pronouns; BAD/GOOD examples in prompt
- [ ] Benchmark Tier 2 cognitive latency on 7950X — current ~17s includes model inference;
      target for typical 3-5 turn window  *(requires hardware — skip in CI)*
- [x] Bounded queue size — 100 slots correct for interactive use (~8 min buffer); documented rationale in event_bus.py; raise to 500 for batch eval runs
- [x] Merge policy — merge() keeps older event's role; warns on cross-session; records merged_roles/merged_count in metadata
- [x] WAL mode audit — all 5 SQLite connections confirmed; experiment_memory.py was the only gap, now fixed
- [ ] ProcessPoolExecutor for heavy extraction (bypass GIL for Tier 2/3)  *(deferred: Tier 2 runs in daemon thread; revisit when latency budget exceeded)*

### Architecture
- [ ] Phase 5: asyncio dispatcher upgrade (replace threading.Thread daemon)
- [x] Entity normalization at write time — to_fact_payload() normalizes subject whitespace in both CognitiveRelation and ReflexRelation
- [x] Demote diagnostic logs to DEBUG — per-turn INFO demoted in daemon.py, ingestion.py, reflex.py, cognitive.py

### UI
- [x] Auto-scroll to bottom — JS injected via st.components.v1.html() after each assistant response
- [x] File upload — collapsible uploader in chat tab; PDF via pypdf, text via UTF-8 decode; injects as user turn in working memory; truncated at 8000 chars
- [x] Graceful shutdown button — sidebar button calls run_lifecycle_maintenance() then close(); nulls pm state
- [x] Session resume — detects prior sessions from working.list_sessions(); offers one-click resume when chat is empty
- [x] Engine selector in chat tab — dropdown above chat history; overrides profile primary engine for next turn; forces pm reload

### Engine / Infrastructure
- [x] Auto-launch llama-server — _auto_launch_llama_server() uses subprocess.Popen; button appears in not-running error banner when gguf_path configured
- [x] n_predict in llm_engines.yaml — added to llama_7b_cpu (1024) and llama_32b_split (2048); threaded through build_llama_cpp_launch_command() as --n-predict

### Testing
- [ ] Eval harness run: gemma4_26b_moe vs qwen3:32b judge comparison  *(requires hardware)*
- [x] Kuzu mmap test failures — deleted 5 kuzu-gated functions from test_typed_relations.py and 10 blocks from test_semantic_memory.py; 18 live Reflex tests retained
- [x] RTRL flaky test fixed — test_surprise_gate_blocks_low_surprise: switched to constant non-zero input with 30 iterations so EMA reliably decays below threshold
- [x] daemon/event_bus tests — 26 test cases in tests/harness/test_daemon_event_bus.py covering TurnEvent ordering, merge semantics, EventBus drop/merge/priority, MemoryDaemon lifecycle

---

## Backlog

### rag_lib — Standalone RAG library

**Rationale:** RAG is needed by the language tutor (vocabulary/grammar reference retrieval), the LLM applications course (module demos), and any future document-grounded chat. Keeping it as a standalone installable package (`pip install rag-lib`) means it composes with Engram as a retriever without creating a circular dependency. The `RAGPipeline` contract in `llm_engines.contracts.rag` and the `RAGInspector` in `llm_inspector` are already designed to consume it.

**Key insight from article review:** Chunking strategy is the most consequential design decision in a RAG stack — it fails silently, producing plausible but wrong answers. The right strategy depends on document type, not on a single "best" approach. The routing dispatch table is the core of `chunker.py`. Evaluated with RAGAS (context recall, context precision, faithfulness, answer relevancy) before and after every significant chunking change.

**Design decisions:**
- `RAGPipeline` Protocol is canonical in `llm_engines.contracts.rag` — rag_lib implements it
- `Chunk` and `RAGResult` Pydantic models are defined there — rag_lib reuses them
- `llm_inspector.rag.RAGInspector` already has adapter stubs for ChromaDB and Engram
- rag_lib should be independently installable with no Engram dependency; Engram integration is an optional extra
- **No LlamaIndex dependency** — implement sentence-window and hierarchical chunking natively (consistent with rest of stack's zero-heavy-dep policy; the algorithms are not complex, the LlamaIndex integration layer is what's expensive). `AutoMergingRetriever` behaviour re-implemented in `retrieval/retriever.py`.
- **PyMuPDF + pdfplumber replace pypdf for PDF** — pypdf fails on multi-column layouts and scanned documents; PyMuPDF for layout-aware extraction, pdfplumber for table extraction, pytesseract as OCR fallback (triggered when PyMuPDF returns < 50 words/page)

**Chunking strategy routing (core of chunker.py):**

| Document type | Strategy | Rationale |
|---|---|---|
| Policy, HR, guide, FAQ | Sentence window (window=3) | Narrative prose; retrieve at sentence precision, generate with paragraph context |
| Spec, runbook, ADR, contract | Hierarchical [2048/512/128] | Structured headings; auto-merge siblings to parent at query time |
| Unstructured mixed (Notion exports) | Semantic | No reliable structural signal; topic-boundary detection outperforms fixed approaches |
| PDF post-processed, slides, short-form | Fixed-size (512t, 50t overlap) | After format-specific preprocessing; simple baseline |

doc_type metadata comes from loaders at ingest time — tag at load, retrofitting across an existing index is painful.

**Tables are first-class, not an edge case:**
Tables are the most common cause of silent retrieval failure in enterprise RAG. Flattened table text loses row-column relationships; the embedding model has no idea what the numbers mean relative to each other. Treatment:
- Each table row reconstructed as a natural-language sentence preserving header-value relationships (`Product: A, Region: EMEA, Q3 Revenue: 4.2M`) before entering the chunking pipeline
- Complex tables (pivot, merged cells, multi-level headers) get a model-generated prose summary at index time (LLaVA via Ollama for fully local stack)
- Implemented in `ingestion/tables.py` as a distinct module called before chunking

**Slides need their own path:**
- `python-pptx` for text extraction; speaker notes always indexed alongside slide body (notes are often more information-dense)
- Images with < 30 words surrounding text flagged for multimodal captioning (LLaVA via Ollama)
- Implemented in `ingestion/slides.py`

**Proposed package structure:**
```
rag_lib/
  src/rag_lib/
    ingestion/
      loader.py       # Format dispatch: DOCX/HTML via Docling; PDF via PyMuPDF+pdfplumber+pytesseract
      chunker.py      # Strategy routing by doc_type: sentence-window, hierarchical, semantic, fixed-size
      tables.py       # Table extraction → natural-language rows; complex tables → LLaVA summary
      slides.py       # python-pptx extraction; speaker notes; image captioning via LLaVA
      embedder.py     # Ollama embedder via raw HTTP (no llm_engines import)
    storage/
      base.py         # VectorStore Protocol
      chroma.py       # ChromaDB backend (versioning, pruning)
    retrieval/
      retriever.py    # Hybrid retrieval: BM25 (rank_bm25) + ChromaDB dense; Reciprocal Rank Fusion; 50 candidates
      reranker.py     # Cross-encoder reranking (sentence-transformers ms-marco-MiniLM-L-6-v2); 50→5
      expander.py     # Query expansion via local LLM (Phase 3; generates synonym/specific/related variants)
    pipeline.py       # RAGPipeline implementation (contracts.rag.RAGPipeline)
    config.py         # YAML-driven config (mirrors llm_engines pattern)
  tests/
  pyproject.toml
```

**Retrieval architecture (two-stage):**
Stage 1 — hybrid retrieval (BM25 + dense vector): BM25 catches exact keyword matches (product names, IDs, acronyms, version numbers) that dense retrieval misses; dense retrieval catches semantic matches. Reciprocal Rank Fusion combines scores. Retrieves 50 candidates.
Stage 2 — cross-encoder reranking: bi-encoder (dense search) is fast but imprecise; cross-encoder scores query+doc as a pair, producing higher precision. `cross-encoder/ms-marco-MiniLM-L-6-v2` runs comfortably on RTX 3090. Returns top 5.

```
query → [BM25 + ChromaDB dense] → 50 candidates → [CrossEncoder rerank] → 5 results → [parent context expansion] → LLM
```

**Dependency boundary:**
- Core: `chromadb`, `pyyaml`, `pydantic`, `PyMuPDF`, `pdfplumber`, `rank_bm25`
- Reranking: `sentence-transformers` (cross-encoder/ms-marco-MiniLM-L-6-v2; local, RTX 3090 capable)
- Ingestion extras: `[ocr]` → pytesseract, `[docx]` → docx2txt + python-docx, `[html]` → beautifulsoup4, `[docling]` → docling, `[slides]` → python-pptx
- Embedding: Ollama via raw HTTP (same urllib pattern as OllamaEngine; no llm_engines import)
- Multimodal captioning: `[vision]` → Ollama with LLaVA model (local); optional cloud path via llm_engines
- Engram integration: `rag_lib` exposes `retrieve()` returning `list[Chunk]`; Engram calls it as an optional fourth retrieval source

**Eval framework (RAGAS) — ship nothing without a baseline:**
Four metrics diagnosing distinct failure layers. Target thresholds for v0.1 sign-off:
- **Context recall ≥ 0.85** (below = chunking is losing information — boundary splits; baseline with fixed-size is ~0.72)
- **Context precision ≥ 0.80** (below = retriever surfacing irrelevant chunks — chunk size too large)
- **Faithfulness ≥ 0.90** (below = LLM hallucinating beyond context — generation problem, not chunking)
- **Answer relevancy ≥ 0.80** (below = retrieved context doesn't address the query — embedding or retrieval problem)
Run before and after every significant chunking or retrieval change. Realistic query set, not hand-picked demos. Metrics tell you *which layer* is failing — don't treat them interchangeably.

**Explicitly not building (v0.1):**
- **Contextualized embeddings** (voyage-context-3 etc.) — API dependency; hierarchical chunking achieves similar results locally
- **ColBERT multi-vector** — high complexity, marginal improvement over cross-encoder; use cross-encoder first
- **Matryoshka embeddings** — requires specific models; premature optimization; standard embeddings work fine
- **HyDE** (Hypothetical Document Embeddings) — requires LLM call per query (latency); benefit unclear vs query expansion; evaluate after basics work
- **Graph RAG** — only needed for multi-hop/relationship queries (org charts, supply chains); Engram's semantic layer handles this for Engram-integrated use cases; rag_lib stays flat

**Query expansion (Tier 3, Phase 3):**
For vague queries, generate 3 related search variants (synonym, specific example, related concept) via a local LLM call. Improves recall for voice queries and imprecise user input. Not in v0.1 — adds latency to every query; validate basic retrieval first.

**Implementation phases:**
- [ ] Phase 1 (Days 1–2): `loader.py` (PDF via PyMuPDF+pdfplumber+pytesseract; DOCX/HTML/txt via Docling) + `chunker.py` (all four strategies + routing dispatch by doc_type) + ChromaDB storage + hybrid retriever (BM25 + dense) + parent document retrieval (sentence-window retrieve → paragraph context return) → working pipeline for text documents
- [ ] Phase 2 (Days 3–4): `tables.py`, `slides.py`, cross-encoder reranker, Ollama embedder, versioning/pruning, config loader, pyproject.toml
- [ ] Phase 3 (Day 5): RAGAS eval harness — measure context recall/precision/faithfulness/answer relevancy on 100-doc test corpus; tune chunking window sizes per doc type; query expansion (optional)
- [ ] Phase 4: Engram retrieval integration (`rag::` namespace prefix in Engram cold storage); auto-merge retrieval for hierarchical docs
- [ ] Phase 5: llm_inspector adapter (ChromaDBRAGAdapter stub already exists)

**v0.1 sign-off criteria:** context recall ≥ 0.85, faithfulness ≥ 0.90, validated on 100-doc test corpus with at least two doc types (narrative + structured).

**Prerequisite:** None. Can start independently of other backlog items.

---

### llm_inspector — Mentor pipeline tracing

**Rationale:** When a local LLM (Ollama/llama.cpp) hands off to an enterprise LLM (Claude/GPT-4) acting as a mentor — reviewing, correcting, or augmenting the local response — the interaction is a causal two-step that the current single-`Trace` schema cannot represent. Adding this makes `llm_inspector` useful for the local+cloud hybrid workflow.

**Design decisions:**
- Two `Trace` objects linked by `parent_trace_id`, not a single `Trace` with multiple `RunMetrics`. Cleaner for export and independent inspection; fits existing compare-mode pairing.
- Orchestration (`MentorPipeline`: when to call mentor, retry logic) belongs in `llm_engines`, not `llm_inspector`. The inspector observes; it does not drive.
- Three schema additions to existing types — minimal surface:

```python
# llm_inspector/core/trace.py

@dataclass(frozen=True)
class RunMetrics:
    ...
    tier: str = "local"              # "local" | "mentor"
    cost_estimate_usd: float | None = None  # None for local; actual for cloud

@dataclass(frozen=True)
class Trace:
    ...
    parent_trace_id: str | None = None  # set on mentor Trace to link to local Trace
```

- Two new `TraceEvent.kind` values: `"mentor_request"` (local output handed off, fields include local response text) and `"mentor_response"` (critique/revision received, fields include mentor response and revision flag).

**Implementation phases:**
- [ ] Phase 1: schema additions (3 fields + 2 event kinds) + `MentorPipeline` in `llm_engines`
- [ ] Phase 2: `llm_inspector` adapter that captures both sides of an exchange
- [ ] Phase 3: UI diff view showing pre/post-mentor response comparison (reuses existing compare mode)
- [ ] Phase 4: cost tracking report (total mentor API cost per session)

**Prerequisite:** `MentorPipeline` in `llm_engines` must exist before the adapter is worth building.
