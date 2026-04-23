# rag_lib Build Plan

**Status:** Pre-implementation  
**Target:** `ai_tools/rag_lib/`  
**Last updated:** Revised for local-LLM deployment

**Sign-off criteria:**
- context recall ≥ 0.85 (retrieval quality — model-independent)
- context precision ≥ 0.80 (retrieval quality — model-independent)
- faithfulness ≥ 0.88 (generation quality — calibrated for local 8–32B models)
- answer relevancy ≥ 0.80 (end-to-end quality)
- Validated on 100-doc corpus covering ≥ 2 doc types (narrative + structured)
- All unit tests pass with zero external services
- Measured with stronger judge model than generator (see D9)

---

## Governing decisions (locked before first commit)

### D1 — No LlamaIndex dependency
Implement sentence-window and hierarchical chunking natively. The algorithms
are not complex; LlamaIndex's value is its integration plumbing, which we
don't want. Consistent with rest of stack's zero-heavy-dep policy.
`AutoMerging` behaviour re-implemented in `retrieval/retriever.py`.

### D2 — PyMuPDF + pdfplumber, not pypdf
pypdf reads text in character order, corrupting multi-column layouts and
scanned forms. PyMuPDF `get_text('blocks')` groups text by visual layout
block; sorting by row bucket then x position reconstructs correct reading
order. pdfplumber handles table extraction. pytesseract is OCR fallback when
PyMuPDF returns < 50 words/page (heuristic for scanned documents).

### D3 — Ollama embedder via raw urllib, no llm_engines import
Mirrors OllamaEngine._post_json() exactly. rag_lib must be installable
without llm_engines. Embedding call hits /api/embed with
{"model": model, "input": texts} and reads "embeddings" from the response.

### D4 — Chunking strategy selected per-document by doc_type metadata
doc_type is set by the loader at ingest time, not inferred later. All four
strategies implemented from Phase 1 start so the routing table works
immediately. doc_type heuristic classifier added in Phase 2 so `ingest_directory()`
produces useful defaults rather than universally falling back to fixed-size.

### D5 — Two-stage retrieval: hybrid BM25+dense → cross-encoder rerank
Stage 1: BM25 (rank_bm25) + ChromaDB dense search combined via Reciprocal
Rank Fusion (RRF k=60) → 50 candidates.
Stage 2: CrossEncoder (sentence-transformers ms-marco-MiniLM-L-6-v2) scores
query+doc pairs → top 5. CrossEncoder lazy-loads on first call; runs on RTX
3090. Reranker off by default; requires explicit `reranker.enabled: true` due
to HuggingFace download on first use (see D10).

### D6 — Tables: CSV serialization default, LLaVA opt-in
Flattened table text loses row-column relationships in embedding space. Row
reconstruction to natural-language sentences ("Product: A | Region: EMEA |
Q3 Revenue: 4.2M") is the baseline approach using " | " separator (comma-safe
for values like "EMEA, Middle East, Africa").
For complex tables (>3 headers, merged cells): default is CSV literal
serialization, not LLaVA prose summary. LLaVA hallucination risk with local
models is too high for compliance/financial data. LLaVA is opt-in via
`tables.complex_handler: llava` with an explicit docs warning.

### D7 — text/context_text split is a hard invariant
`TextChunk.text` = what gets embedded (short, precise).
`TextChunk.context_text` = what the LLM sees (expanded window or parent).
These differ for sentence-window and hierarchical strategies. The embedder
receives only `text`. `storage/chroma.py add()` enforces this with a token
count check (max_embed_tokens default 1800, conservative under nomic-embed-text's
2048 limit). Violation raises `ChunkerError` naming the offending source.
`assemble_prompt()` receives only `context_text`.

### D8 — assemble_prompt() requires max_context_tokens; budget-based assembly
Local models have hard context limits that vary by model and llama-server -c
setting (4096 default, up to 32K for Qwen3). `assemble_prompt()` takes
`max_context_tokens` as a required parameter (no default). Fills chunks from
highest-score to lowest until budget is exhausted, then stops. `n_results=5`
in the retriever is a soft ceiling, not a guaranteed count. Config default
is 3000 — conservative across common local model configurations.

### D9 — RAGAS judge_llm is required; stronger than generator
`ragas_runner.py` `judge_llm` parameter has no default. Raises `EvalError`
with a clear message if not provided. Prevents silent self-evaluation
(a model judging its own outputs measures self-consistency, not quality).
Recommended: Claude Haiku as judge for eval runs (~$0.50 per 100 queries).
Acceptable alternative: Qwen3:32b judging Qwen3:8b outputs. Temperature=0
for judge. Run eval 3× and take median when scores are near a threshold.
Faithfulness threshold is 0.88 not 0.90 — calibrated for local 8–32B models.

### D10 — All optional model downloads are explicit, never automatic
Cross-encoder model downloads from HuggingFace on first instantiation.
Default is `reranker.enabled: false`. `scripts/setup_models.py` pre-downloads
all optional models to HuggingFace cache; documents cache path for manual
transfer to air-gapped machines. When reranker is enabled and model is absent,
`RerankerError` includes cache path and manual download instructions.

### D11 — Embedding model versioning tracked per collection
Collection metadata stores `embed_model` and `embed_dimensions` at creation.
Every `retrieve()` call verifies configured model matches stored model.
Mismatch raises `StorageError` with clear migration instructions. Prevents
silent cross-space comparison when model is changed in config.

### D12 — BM25 index rebuilt on every ingest; persisted to disk
BM25 index is written to `{storage.path}/bm25/{collection}.pkl` after each
ingest. Loaded from disk on startup; rebuilt if file absent or stale relative
to ChromaDB metadata timestamp. This keeps BM25 and ChromaDB in sync across
process restarts and incremental ingestion.

### D13 — ChromaDB collections always use cosine distance
All collections created with `metadata={"hnsw:space": "cosine"}`. L2
(Euclidean) distance is ChromaDB's default but is unbounded, making
`1.0 - distance` meaningless. Cosine distance with unit-normalized vectors
maps cleanly to [0,1] similarity. Collection-creation-time decision — cannot
be changed after the fact.

### D14 — Re-ingest deduplication via content-addressed source IDs
Chunk IDs are `sha256(file_path + chunk_index + file_content_hash)[:16]`.
Re-ingesting a modified file: delete all chunks with matching file_path
prefix, then insert new chunks. Re-ingesting an unchanged file is a no-op
(same IDs, ChromaDB upsert). Prevents corpus bloat and stale content from
accumulating over time.

### D15 — Ollama keep_alive managed to prevent model-switch latency
Three models may be needed: embed model, LLaVA (optional), generation model.
Each Ollama model switch can cost 30–90s of load time. Config exposes
`embedder.keep_alive` (default 600s) and `tables.llava_keep_alive` (default 60s).
`ingest_directory()` docstring explicitly warns: process all documents before
querying, so embed model stays warm through the full ingestion pass.

### D16 — Concurrent write safety via explicit serialization
ChromaDB embedded mode does not support concurrent writes. All write paths
(ingest, prune, delete) acquire a single threading.Lock in `storage/chroma.py`.
`ingest_directory()` is always single-threaded for writes. Documented
explicitly — not left as implicit behavior.

### D17 — Sentence splitting via NLTK punkt, not str.split(".")
`str.split(".")` breaks on abbreviations ("Dr.", "e.g.", "Fig. 3.2"),
decimal numbers, and version strings. NLTK `punkt_tab` tokenizer handles
these cases. Added as a declared core dependency. On first use, downloads
punkt model via `nltk.download('punkt_tab')` if absent; the setup script
handles this pre-emptively.

### D18 — Semantic chunking cost is bounded
Semantic chunking embeds every sentence before determining boundaries
(4–5× slower than other strategies). Config adds `chunker.semantic_max_sentences`
(default 500). Documents exceeding this limit fall back to sentence-window
with a logged WARNING naming the source file. Prevents silent multi-minute
hangs on large mixed-format documents.

### D19 — Query expansion off by default; query-level caching when enabled
Each expansion call adds 1–3s of local LLM inference per query. Default:
`expander.enabled: false`. When enabled, expansions are cached by query hash
in an in-memory LRU cache (max 256 entries). Repeated identical queries pay
the expansion cost only once per process lifetime.

---

## Package structure

```
rag_lib/
  src/
    rag_lib/
      __init__.py               # Public API surface
      pipeline.py               # RAGPipeline — the single entry point
      config.py                 # YAML loader; mirrors llm_engines pattern
      errors.py                 # RagLibError hierarchy

      ingestion/
        __init__.py
        loader.py               # Format dispatch; sets doc_type metadata
        chunker.py              # Strategy routing; all 4 strategies; NLTK sentences
        tables.py               # Table → NL sentences (row reconstruction)
                                #   or CSV literal (complex); LLaVA opt-in
        slides.py               # python-pptx; speaker notes; image caption flag
        embedder.py             # Ollama /api/embed via urllib; keep_alive mgmt

      storage/
        __init__.py
        base.py                 # VectorStore Protocol; StoredChunk dataclass
        chroma.py               # cosine distance; versioning; pruning;
                                #   embed model version guard; write lock

      retrieval/
        __init__.py
        retriever.py            # Hybrid BM25+dense; RRF; parent context expansion;
                                #   BM25 disk persistence; token budget enforcement
        reranker.py             # CrossEncoder; lazy load; off by default
        expander.py             # Query expansion; LRU cache; off by default

      eval/
        __init__.py
        ragas_runner.py         # RAGAS wrapper; judge_llm required; median of 3 runs

  data/
    rag_lib.yaml                # Packaged default config

  scripts/
    setup_models.py             # Pre-download NLTK punkt, CrossEncoder
    benchmark.py                # 100-doc benchmark runner; RAGAS report

  tests/
    conftest.py                 # Port probes; Ollama skip marker; tmp fixtures
    test_chunker.py
    test_tables.py
    test_slides.py
    test_loader.py
    test_embedder.py
    test_retriever.py
    test_reranker.py
    test_storage.py
    test_pipeline.py
    test_eval.py

  pyproject.toml
  README.md
```

---

## `rag_lib.yaml` — default config (annotated)

```yaml
embedder:
  host: http://localhost:11434
  model: nomic-embed-text        # max 2048 tokens; enforced in chunker
  timeout: 120
  batch_size: 32
  keep_alive: 600                # seconds; keep model warm during ingestion

storage:
  backend: chromadb
  path: ~/.rag_lib/chroma        # persistent; hnsw:space=cosine enforced
  collection_prefix: rag_
  bm25_path: ~/.rag_lib/bm25     # BM25 index persistence dir

chunker:
  max_embed_tokens: 1800         # hard ceiling; conservative under 2048 limit
  semantic_max_sentences: 500    # fallback to sentence_window above this
  defaults:
    strategy: fixed_size
    chunk_size: 512
    chunk_overlap: 50
  doc_types:
    policy:    {strategy: sentence_window, window_size: 3}
    hr:        {strategy: sentence_window, window_size: 3}
    guide:     {strategy: sentence_window, window_size: 3}
    faq:       {strategy: sentence_window, window_size: 3}
    spec:      {strategy: hierarchical, chunk_sizes: [2048, 512, 128]}
    runbook:   {strategy: hierarchical, chunk_sizes: [2048, 512, 128]}
    adr:       {strategy: hierarchical, chunk_sizes: [2048, 512, 128]}
    contract:  {strategy: hierarchical, chunk_sizes: [2048, 512, 128]}
    mixed:     {strategy: semantic, breakpoint_percentile: 92}

retriever:
  n_candidates: 50               # Stage 1 hybrid retrieval count
  n_results: 5                   # Soft target after reranking/budget
  bm25_weight: 0.4               # RRF: 0.4 BM25 / 0.6 dense
  parent_window: 3               # Context sentences around retrieved sentence
  max_context_tokens: 3000       # Budget for assemble_prompt(); adjust for model

reranker:
  enabled: false                 # Requires explicit opt-in; HuggingFace download
  model: cross-encoder/ms-marco-MiniLM-L-6-v2
  device: auto                   # auto | cpu | cuda

tables:
  complex_threshold: 3           # Header count above which CSV is used
  complex_handler: csv           # csv (default, faithful) | llava (opt-in, risks hallucination)
  llava_model: llava:13b
  llava_keep_alive: 60           # Short; only needed during ingest
  row_separator: " | "           # Separates header:value pairs; comma-safe

expander:
  enabled: false                 # Adds 1-3s LLM latency per query when enabled
  cache_size: 256                # LRU cache entries

eval:
  # judge_llm: required at runtime — no default
  # Recommended: Claude Haiku (cheap, strong judge)
  # Acceptable: qwen3:32b judging qwen3:8b outputs
  judge_temperature: 0.0
  n_eval_runs: 3                 # Take median; reduces LLM judge variance
  context_recall_threshold: 0.85      # retrieval quality — model-independent
  context_precision_threshold: 0.80   # retrieval quality — model-independent
  faithfulness_threshold: 0.88        # calibrated for local 8-32B models
  answer_relevancy_threshold: 0.80    # end-to-end quality
```

---

## Error hierarchy

```python
# errors.py

class RagLibError(Exception):
    """Base for all rag_lib errors."""

class EmbedderError(RagLibError):
    """Ollama unreachable, model not loaded, or token limit exceeded."""

class StorageError(RagLibError):
    """ChromaDB operation failed; includes embedding model version mismatch."""

class LoaderError(RagLibError):
    """Document could not be loaded or format is unsupported."""

class ChunkerError(RagLibError):
    """Chunking produced invalid output (empty doc, token limit violated)."""

class RerankerError(RagLibError):
    """CrossEncoder not available or model download failed."""

class EvalError(RagLibError):
    """RAGAS evaluation failed; includes missing judge_llm error."""
```

All public methods catch internal exceptions and wrap in the appropriate
subclass. Callers never see urllib, sqlite3, chromadb, or
sentence_transformers internals.

---

## Module specifications (critical design details only)

### `ingestion/chunker.py` — sentence splitter

Uses `nltk.tokenize.sent_tokenize()` (punkt_tab model). Wraps in a
`_sentences(text) -> list[str]` helper that falls back to `re.split(r'(?<=[.!?])\s+', text)`
if NLTK is unavailable, with a logged WARNING. The setup script runs
`nltk.download('punkt_tab')` pre-emptively; this fallback handles the
edge case where NLTK data was not pre-downloaded.

```python
def _sentences(text: str) -> list[str]:
    try:
        from nltk.tokenize import sent_tokenize
        return sent_tokenize(text)
    except Exception:
        logger.warning("NLTK punkt unavailable; using regex sentence splitter")
        return re.split(r'(?<=[.!?])\s+', text.strip())
```

Semantic chunking: before calling the sentence embedder, check
`len(sentences) > config.semantic_max_sentences`. If exceeded, log WARNING
with source path and fall back to sentence_window. Never silently hang.

### `ingestion/embedder.py` — keep_alive and token guard

```python
class OllamaEmbedder:
    def embed(self, texts: list[str], *, validate_tokens: bool = True) -> list[list[float]]:
        if validate_tokens:
            for i, t in enumerate(texts):
                if len(t.split()) > self._max_embed_tokens:
                    raise EmbedderError(
                        f"Text at index {i} exceeds max_embed_tokens "
                        f"({len(t.split())} words > {self._max_embed_tokens}). "
                        "Check that chunker.text (not context_text) is being embedded."
                    )
        # ... batch and POST
```

keep_alive is passed as `"keep_alive": self.keep_alive` in the /api/embed
payload. Ollama respects this to keep the model resident in VRAM between calls.

### `storage/chroma.py` — model version guard and content-addressed IDs

```python
class ChromaStorage:
    def _get_or_create_collection(self, name: str) -> chromadb.Collection:
        full_name = f"{self._prefix}{name}"
        existing = self._client.list_collections()
        if full_name in [c.name for c in existing]:
            coll = self._client.get_collection(full_name)
            stored_model = coll.metadata.get("embed_model")
            if stored_model and stored_model != self._embed_model:
                raise StorageError(
                    f"Collection '{name}' was built with embed_model='{stored_model}' "
                    f"but config specifies '{self._embed_model}'. "
                    "Delete the collection and re-ingest, or restore the original model."
                )
            return coll
        return self._client.create_collection(
            name=full_name,
            metadata={
                "hnsw:space": "cosine",     # D13: always cosine
                "embed_model": self._embed_model,
                "embed_dimensions": self._embed_dimensions,
                "created_at": time.time(),
            },
        )

    @staticmethod
    def chunk_id(file_path: str, chunk_index: int, file_hash: str) -> str:
        key = f"{file_path}:{chunk_index}:{file_hash}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]
```

Write lock wraps all `add()`, `delete()`, `prune()` calls:
```python
self._lock = threading.Lock()

def add(self, chunks, embeddings):
    with self._lock:
        # ... chromadb upsert
```

### `retrieval/retriever.py` — BM25 persistence and budget enforcement

```python
class HybridRetriever:
    def _load_or_build_bm25(self, collection: str) -> BM25Okapi:
        pkl_path = self._bm25_path / f"{collection}.pkl"
        chroma_mtime = self._get_chroma_mtime(collection)
        if pkl_path.exists():
            bm25_mtime = pkl_path.stat().st_mtime
            if bm25_mtime >= chroma_mtime:
                with open(pkl_path, "rb") as f:
                    return pickle.load(f)
        # Rebuild from ChromaDB
        bm25 = self._build_bm25(collection)
        pkl_path.parent.mkdir(parents=True, exist_ok=True)
        with open(pkl_path, "wb") as f:
            pickle.dump(bm25, f)
        return bm25

def assemble_prompt(
    self,
    query: str,
    chunks: list[Chunk],
    max_context_tokens: int,       # required; no default
    system_prompt: str = "",
) -> str:
    budget = max_context_tokens
    if system_prompt:
        budget -= len(system_prompt.split())
    budget -= len(query.split())
    budget -= 50   # prompt template overhead

    selected: list[Chunk] = []
    for chunk in chunks:   # already sorted by score descending
        cost = len(chunk.content.split())
        if cost <= budget:
            selected.append(chunk)
            budget -= cost

    if not selected:
        logger.warning("No chunks fit within max_context_tokens=%d", max_context_tokens)

    parts = []
    if system_prompt:
        parts.append(system_prompt)
    if selected:
        context = "\n\n".join(f"[{i+1}] {c.content}" for i, c in enumerate(selected))
        parts.append(f"Context:\n{context}")
    parts.append(f"Question: {query}\n\nAnswer:")
    return "\n\n".join(parts)
```

### `eval/ragas_runner.py` — judge_llm required

```python
def run_eval(
    pipeline: RAGPipeline,
    test_queries: list[dict],   # [{"question": str, "ground_truths": list[str]}]
    *,
    judge_llm,                  # required — no default
    n_runs: int = 3,            # take median to reduce variance
    collection: str = "default",
) -> EvalReport:
    if judge_llm is None:
        raise EvalError(
            "judge_llm is required. Using the same model as generator measures "
            "self-consistency, not quality. Recommended: Claude Haiku (~$0.50/100 queries) "
            "or a model larger than the generator (e.g., qwen3:32b judging qwen3:8b)."
        )
    # ... run RAGAS n_runs times, return EvalReport with per-metric median
```

---

## Testing strategy

### Unit tests (zero external services)
All fakes use `unittest.mock` and in-memory ChromaDB client.
Must pass in CI with no Ollama, no HuggingFace, no network.

Critical tests to write first (they catch the most expensive mistakes):

```
test_storage.py
  - model_version_guard: StorageError when embed_model changes
  - cosine_distance: collection created with hnsw:space=cosine
  - content_addressed_ids: same file same index same hash → same ID
  - re_ingest_dedup: second ingest of same file produces same chunk count, not 2×

test_chunker.py
  - token_limit_enforcement: ChunkerError when chunk exceeds max_embed_tokens
  - text_vs_context_text: text is short; context_text is longer (sentence-window)
  - sentence_splitter: "Dr. Smith" not split; "Fig. 3.2" not split; "v2.4.1" not split
  - semantic_max_sentences: falls back to sentence_window above limit with WARNING

test_retriever.py
  - bm25_sync: BM25 rebuilt after ingest; new chunks retrievable immediately
  - bm25_staleness: stale pickle triggers rebuild
  - budget_enforcement: assemble_prompt stops at budget; partial chunk list returned
  - budget_zero: logs WARNING when nothing fits; returns prompt with query only

test_eval.py
  - judge_llm_required: EvalError when judge_llm=None
  - median_of_runs: median taken correctly across 3 runs
```

### Integration tests (marked `@pytest.mark.ollama`)
Skip when Ollama not running. Run manually before Phase 3 sign-off.

```
test_pipeline.py
  - txt ingest → retrieve: relevant chunks returned
  - PDF ingest: table rows appear as NL sentences in retrieval
  - re_ingest: corpus size stable after re-ingesting same file
  - model_switch: StorageError when model changed between ingest and retrieve
  - context_budget: chunks fit within max_context_tokens
  - mixed doc types: policy file → sentence_window; spec file → hierarchical
```

### Benchmark script
`scripts/benchmark.py` — ingest 100-doc test corpus, run RAGAS with specified
judge model, print report. Requires `--judge-model` argument (no default).
Run 3 times; prints per-run and median scores.

---

## Dependency and extras

```toml
[project]
dependencies = [
    "chromadb>=0.5",
    "pyyaml>=6.0",
    "pydantic>=2.0",
    "PyMuPDF>=1.24",
    "pdfplumber>=0.11",
    "rank_bm25>=0.2",
    "nltk>=3.8",
    "llm_engines",              # contracts.rag types only; no backends loaded
]

[project.optional-dependencies]
ocr     = ["pytesseract>=0.3"]
docx    = ["docx2txt>=0.8", "python-docx>=1.1"]
html    = ["beautifulsoup4>=4.12", "lxml>=5.0"]
slides  = ["python-pptx>=1.0"]
rerank  = ["sentence-transformers>=3.0"]    # pulls PyTorch; off by default
eval    = ["ragas>=0.2", "datasets>=2.0"]
docling = ["docling>=2.0"]
all = [
    "pytesseract>=0.3",
    "docx2txt>=0.8", "python-docx>=1.1",
    "beautifulsoup4>=4.12", "lxml>=5.0",
    "python-pptx>=1.0",
    "sentence-transformers>=3.0",
    "ragas>=0.2", "datasets>=2.0",
]
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.0",
    "ragas>=0.2",
    "datasets>=2.0",
]
```

---

## Build sequence (phase-by-phase)

### Phase 1 — Working text pipeline (2 days)
Order follows D7 (no forward-reference issues):

1. `errors.py`
2. `pyproject.toml`, `data/rag_lib.yaml`
3. `ingestion/embedder.py` + `test_embedder.py`
4. `storage/base.py`
5. `ingestion/chunker.py` (all 4 strategies; NLTK; token guard) + `test_chunker.py`
6. `ingestion/loader.py` (txt, HTML, basic PDF) + `test_loader.py`
7. `storage/chroma.py` (cosine; version guard; write lock; content-addressed IDs) + `test_storage.py`
8. `retrieval/retriever.py` (hybrid; BM25 persistence; budget enforcement) + `test_retriever.py`
9. `config.py`
10. `pipeline.py` (ingest + retrieve + assemble_prompt) + `test_pipeline.py`
11. `scripts/setup_models.py` (NLTK punkt download)
12. `__init__.py`, `README.md`

Sign-off: all unit tests pass. Manual smoke: ingest a text file, retrieve a
query, chunks fit within max_context_tokens, BM25 pickle written to disk.

### Phase 2 — Format coverage + reranking (2 days)
1. `ingestion/tables.py` + `test_tables.py`
2. `ingestion/slides.py` + `test_slides.py`
3. Full PDF path in `loader.py` (PyMuPDF blocks; pdfplumber tables; OCR)
4. Full DOCX path (docx2txt prose + python-docx table extraction)
5. `retrieval/reranker.py` + `test_reranker.py`
6. ChromaDB versioning + pruning in `storage/chroma.py`
7. `pipeline.ingest_directory()` with doc_type_map + heuristic classifier
8. `scripts/setup_models.py` updated (CrossEncoder download)

Sign-off: ingest policy PDF + spec DOCX, retrieve produces correctly routed
chunks, tables appear as NL sentences, re-ingest produces stable corpus size.

### Phase 3 — Eval + tuning (1 day)
1. `eval/ragas_runner.py` (judge_llm required; median of 3 runs) + `test_eval.py`
2. `retrieval/expander.py` (LRU cache; off by default)
3. `pipeline.evaluate()` wired to RAGAS
4. `scripts/benchmark.py` (requires --judge-model; 100-doc run)
5. Tune window_size and hierarchical chunk_sizes per doc_type against RAGAS output

Sign-off: `scripts/benchmark.py --judge-model claude-haiku-4-5` produces
context_recall ≥ 0.85, faithfulness ≥ 0.88.

### Phase 4 — Engram integration (1 day)
1. `rag::` namespace prefix in Engram cold storage retrieval path
2. Engram `retrieval.py` calls `rag_lib.pipeline.retrieve()` when installed
3. Graceful skip when rag_lib absent (optional dep)
4. `integration_tests/test_rag_engram.py`

### Phase 5 — llm_inspector adapter (half day)
1. `ChromaDBRAGAdapter` in `llm_inspector/rag.py` updated to use rag_lib
2. `RAGLibAdapter` added for full pipeline
3. `llm_inspector` integration test

---

## Scope boundary (not building in v0.1)

- Contextualized embeddings — API dependency; hierarchical chunking equivalent locally
- ColBERT multi-vector — marginal gain over cross-encoder; use cross-encoder first
- Matryoshka embeddings — premature optimization; standard embeddings sufficient
- HyDE — LLM call per query adds latency; validate basics first
- Graph RAG — Engram's semantic layer handles multi-hop; rag_lib stays flat
- Web UI — llm_inspector_ui handles this
- Fine-tuned domain embeddings — Phase 2+ concern
