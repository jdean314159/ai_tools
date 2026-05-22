# Next Thread Handoff — ai_tools

Last updated: 2026-05-21

Rehydrate the next thread from this file. Read the "Architecture findings"
section before doing any engram work — the direction changed mid-session.

## Current objective

Decide what `engram` / `engram` should be, then run a best-of-breed eval
to pick the winning memory configuration. **Do not keep building the
engram facade (ADR-007 Step 2).** The step-back analysis below concluded
the facade was solving the wrong problem; it is on hold pending the architecture
decision.

Immediate next action: locate the past eval run where engram outscored
engram (judge = Claude or local LLM), then build the ablation matrix
(see "Best-of-breed plan").

## What this session accomplished

Work splits into KEEP (good regardless of architecture decision) and ON HOLD.

### KEEP — engram core improvements (independent of the facade)

- **Option B — embedder injection into engram episodic.** `engram.EpisodicMemory`
  now accepts `embedding_function=`; new `EmbedderEmbeddingFunction` adapter wraps
  any `engram.embeddings.Embedder` (e.g. `OllamaEmbedder`) to ChromaDB's EF
  protocol. `embedder=` threads `ProjectMemory.__init__` → `_build_layers` →
  `EpisodicMemory`. Default path (no embedder) is unchanged (SentenceTransformers).
  Result: episodic memory can run **without torch/sentence-transformers** when an
  Ollama embedder is supplied. Files: `engram/src/engram/memory/episodic_memory.py`,
  `engram/src/engram/project_memory.py`.
- **Bug fix — `find_similar_episodes`** reached into `self.embedding_fn.model.encode`
  (a SentenceTransformers-only attr); now routes through the EF's public
  `embed_query` with explicit unit-normalization (works for any backend, keeps
  dot==cosine). Without this, dedup silently no-ops on the Ollama path.
- **Bug fix — ChromaDB EF reconstruction warning.** `EmbedderEmbeddingFunction`
  `get_config`/`build_from_config` now round-trip the Ollama backend (and install
  a safe stub for other backends), eliminating the "Could not reconstruct
  embedding function … Setting to None" warning.
- **Infra fix — `conftest.py`** still anchored `engram_ui` under `engram/src`
  after it was relocated to its own top-level package; repointed to
  `engram_ui/src/engram_ui` and added `engram_ui/src` to the test source paths.
- **Infra fix — `engram/tests/harness/test_rtrl_signal.py`** had a top-level
  `import torch` that crashed before its own `importorskip` and cascaded through
  the harness `__init__` (which eagerly imports every module), taking
  `test_audit_remediate` down too. Removed the redundant top-level torch/pytest
  imports; torch is imported lazily in `_make_coordinator` and gated per-test via
  `require("torch")`.

### ON HOLD — engram facade (ADR-007 Step 2)

- Wrote `engram/src/engram/project_memory.py` as a ~497-line facade:
  composition over `engram.ProjectMemory`, exactly the 22 contracted public
  methods, defaults to `OllamaEmbedder`, `base_dir=None` → temp dir, RTRL off.
- Re-pointed `engram/__init__.py` and trimmed `interop.py` so
  `describe_memory` / `trace_to_memory_records` re-export from `engram.interop`;
  only `augment_result_to_interop_result` stays local.
- **Status:** `test_public_api_contract.py` passes (AST-verified: 22/22 methods,
  signatures, frozen `__all__`). Smoke test confirmed episodic store/search works
  torch-free via Ollama. 27 of the older lite tests fail because they assert
  lite-v0.1 standalone behavior (LightweightIngestionPolicy specifics, lite
  pairing, JSONL internals) that the facade intentionally drops — these were NOT
  migrated; do not invest in migrating them given the facade is on hold.

### Validation status on Jeff's machine

- `make install` (lightweight) + contract test + engram suite: **48 passed,
  920 skipped, 0.54s** — heavy layers (chromadb/torch/Ollama) skipped, so this
  only proved collection is clean + contract green; it did NOT exercise Option B.
- Option B exercised via smoke test under `engram[episodic]` + Ollama
  (`nomic-embed-text`): episodic initialized as `EpisodicMemory`, store/search
  worked, no warnings. **Dedup did not fire on a paraphrase** — see threshold
  finding below (calibration, not a bug).

## Architecture findings (READ THIS)

### 1. The decomposition was additive, not subtractive

The original monolithic `engram` was never stripped after components were broken
out. The "extracted" libraries run in parallel with the code they were meant to
replace:

- **Two engine layers, diverged.** `engram/src/engram/engine/` is ~5,716 lines
  (ClaudeEngine, GeminiEngine, LlamaCppEngine, OllamaEngine, VLLMEngine,
  FailoverEngine, config_loader, model_manager…). `llm_engines/` is its own
  ~10.7k-line suite (AnthropicEngine, OpenAIEngine, …). They do not import each
  other; `engram` does not depend on `llm_engines`. `engram_ui` imports
  `engram.engine`, NOT `llm_engines`. (See the reconciliation note already in
  `engram_ui/.../model_management/STATUS.md`, dated 2026-05-11.)
- **Two memory libraries** — `engram/memory` (mature) and `engram`
  (diverged). Same niche.
- **Two prompt builders inside engram** — `engram/prompt/builder.py` and
  `engram/prompting/builder.py`.

ADR-007 (facade lite over engram) was treating the two-memory-libs symptom while
the larger, identical pattern sat unaddressed in the engine layer.

### 2. Jeff's original intent + the proposed direction

`engram` was meant to BE the memory component — the clean end-state of
decomposing the monolith (engines → `llm_engines`, UI → `engram_ui`, memory →
`engram`). `engram` itself got all the development and became the de-facto
memory lib, so they collided.

Jeff's proposed process: move the memory functions into `engram` and pull
`engram` (the original integrated standalone system) into a separate repo "as it
originally was."

**Unresolved hinge decision:** is the extracted standalone `engram` going to be
**frozen** (archived reference; build forward only on the monorepo components) or
**living** (kept in development)? Frozen → clean, low-risk, endorse. Living → it
must consume `llm_engines`/`engram` or it re-diverges into two memory libs
across two repos, and the solo-dev monorepo workflow (one venv, editable
installs, atomic commits) is lost. This decision sets the whole process.

Note on the hard part: "move memory into engram" requires disentangling the
memory subtree from `engram.engine`, the two prompt builders, telemetry, interop,
and the cognitive layer's LLM calls (repoint to `llm_engines`). That disentangling
is the real work and is unavoidable under any naming/repo choice; the
`git filter-repo` repo split is the easy part. Naming: once the old engram leaves
the monorepo, "engram" will hold the full multi-layer system — decide whether
the monorepo memory lib reclaims the name `engram` or renames honestly.

### 3. engram and engram have largely CONVERGED (key eval finding)

Comparing the 3-week-old standalone lite backup against current engram:

- **Retrieval:** lite does vector+text RRF fusion with recency + importance
  boosts (`retrieval/hybrid.py`). Engram ALREADY does lexical+vector fusion with
  recency (two-scale) and importance in `engram/memory/retrieval.py`
  (`episodic_weight_lexical=0.50`, `episodic_weight_recency=0.16`, FTS5 lexical).
- **Ingestion gate:** lite's `LightweightIngestionPolicy.score_text` (additive
  lexical heuristic, `should_store = importance >= 0.45`). Engram's
  `IngestionPolicy` does the same shape (`score >= episode_threshold and len >= 24`)
  from per-project `ingestion_patterns.yaml`.

So lite's historical wins were probably NOT a better architecture. Most likely
causes, in order: (a) **engram's extra complexity hurting** — neural surprise
filter gating storage, semantic graph, cold layer, multi-layer fusion adding
noise vs lite's working+episodic simplicity; (b) the embedder/threshold confound
(below); (c) method-level differences.

Genuine remaining divergences (treat as eval toggles):
1. Fusion method — lite RRF (rank-based, k=60) + multiplicative boosts vs engram
   weighted linear sum.
2. Ingestion features — lite hand-tuned signals vs engram YAML patterns.
3. Recency shape — lite single 30-day linear vs engram two-scale.
4. **Storage — lite JSONL source-of-truth + optional Chroma + text-only fallback
   (works with no embedder) vs engram Chroma-native.** This is the one true
   architectural divergence and the one aligned with the air-gapped course
   constraint — worth keeping as an engram feature regardless.

### 4. Thresholds are MiniLM-calibrated; they do not transfer to nomic

Measured nomic-embed-text cosines: identical = 1.00, tight paraphrase = 0.81,
unrelated = 0.41. Engram's defaults assume MiniLM's scale: `dedup_threshold=0.92`
(unreachable for nomic — paraphrases live ~0.78–0.85), `vector_similarity_threshold=0.4`
(below nomic's 0.41 noise floor → filters nothing). Any historical engram-vs-lite
comparison across different embedders is confounded by tuning. A fair eval must
tune each arm for its own embedder first. Two levers, deferred to the eval:
embedder-aware threshold defaults; nomic task prefixes (`search_query:` /
`search_document:`) — the latter is invasive because ChromaDB embeds `query_texts`
through the EF `__call__`, so prefixes need `query_embeddings=` plumbing in
engram's `search`.

## Found eval results — engram vs engram comparison

Source: "AI tools repository assessment and review" thread (~early May 2026).

| Metric | engram | engram |
|--------|--------|-------------|
| Decoy resistance baseline | 50–53% ❌ | **80%** ✓ |
| Decoy resistance stress | 58% | **82%** ✓ |
| Recall direct (baseline / stress) | 98% / 83% | 98% / 83% |
| Recall paraphrase baseline | **98%** | 92% |
| Contradiction bleed stress | **13–17%** | 18% |

**Overall: engram 12 better, engram 6 better, 18 within 5pp.**

**Root cause of the gap (already identified at the time):** The 27pp decoy
resistance difference was traced to a single missing feature —
`vector_similarity_threshold` filtering. engram had a tuned 0.4 threshold;
engram lacked it (ChromaDB collection not set to `hnsw:space: cosine`, no
similarity floor on returned results). The fix was estimated at 1–2 hours and
listed as an open item but was not completed before this session. When the
threshold approach was applied to engram and re-evaluated, the assessment
became "essentially tied, most differences within 5pp."

**Implication for the best-of-breed plan:** The historical lite win was tuning,
not architecture — confirming the convergence finding above. The ablation question
(does engram's extra complexity hurt?) is still worth measuring but the urgency
is lower. The immediate actionable: apply `vector_similarity_threshold` +
`hnsw:space: cosine` to engram (Lever 1 deferred from this session), tuned
per-embedder (MiniLM-calibrated for the sentence-transformers path;
nomic-calibrated for the Ollama/lite path — see threshold findings above). Then
re-run `compare_backends.py` to confirm parity and proceed to the complexity
ablation.

## Best-of-breed plan (next thread)

Reframe from "port lite into engram" to **ablation on engram**: approximate lite
inside engram by turning layers/filters off (surprise filter off, neural off,
semantic/cold off, episodic-only, RRF fusion mode), embedder + per-embedder
thresholds held constant, and sweep complexity on/off against the eval corpus.
This directly tests whether engram's extra layers earn their keep. Port only the
genuinely useful lite-only options: RRF fusion as a mode (cheap) and the
text-only/JSONL fallback (a real feature for air-gapped). The winning ablation
becomes an engram preset; lite becomes a configuration, not a package.

The pending input: the eval run where lite won, ideally with per-query/per-metric
results, to target which toggle (complexity, fusion, or tuning) to interrogate
first instead of sweeping all four blind.

## Open decisions blocking progress

1. **Freeze vs living** for the extracted standalone engram (sets the whole
   process — see finding 2).
2. **Consolidate on engram** as the single memory library (lite → config)? The
   convergence finding (3) supports this; confirm before disentangling.
3. **Fate of this session's facade** — keep as the "lite = engram config"
   entry point, or revert in favor of an `engram.simple` facade / preset inside
   engram. Likely the latter given the direction.
4. **Engine reconciliation** (`engram.engine` vs `llm_engines`) — the larger
   refactor; deserves its own ADR. Sequence after the memory consolidation.

## First commands in the next thread

```bash
cd ~/ai_tools
git status --short --branch
git log --oneline --decorate --max-count=8
# Confirm which of this session's changes are applied / committed:
git diff --stat
```

Then, to resume the best-of-breed work once eval results are located, trace the
real dependency map (was deferred this session):

```bash
# Who imports the duplicate engine layer (blast radius for consolidation)?
grep -rn "engram.engine\|from engram import.*Engine" --include=*.py \
  engram_ui/src language_tutor llm_engines 2>/dev/null
# What does the language tutor import for memory — engram, engram, or engram.engine?
grep -rn "import engram" --include=*.py language_tutor 2>/dev/null | head
```

## Artifacts produced this session (in case re-applying is needed)

Patches (git-apply-able) and full files were delivered as downloads:
`engram_option_b.patch`, `episodic_embedder_fixes.patch`,
`conftest_engram_ui_path.patch`, `test_rtrl_signal_torch_guard.patch`,
`project_memory.py` (the facade shim), `dedup_diagnostic.py`.
The 3-week-old standalone engram backup is the reference for lite's
distinctive ingestion/retrieval (Tier-2 material overwritten in the live tree).
