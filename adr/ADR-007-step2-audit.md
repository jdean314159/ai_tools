# ADR-007 Migration — Step 2 Audit

Classification of every `engram_lite` public symbol against its `engram`
equivalent, to drive the facade migration. Verb key:

| Tag | Meaning | engram change? |
|-----|---------|----------------|
| **re-export** | engram exports it as-is | none |
| **direct** | engram method, matching signature; adapter delegates 1:1 | none |
| **shim-sig** | engram has the capability but signature/param names drift; adapter translates | none |
| **alias** | engram has equivalent under a different name and/or return shape; adapter maps both | none |
| **shim-only** | lite-specific framing, no engram home; adapter implements against engram primitives | none |
| **lift** | genuine capability engram lacks; implement in engram, then delegate | yes (Step 3) |

The migration vehicle is an **adapter shim**: `engram_lite/project_memory.py`
becomes a thin `ProjectMemory` class wrapping an internal `engram.ProjectMemory`,
configured for SQLite + ChromaDB defaults. engram stays frozen for Step 2.
The six **lift** rows become a Step 3 backlog — initially shim-implemented
against engram's internal layers (`self._em.episodic`, `self._em.semantic`,
etc.), promoted to first-class engram methods later.

## ProjectMemory methods (22)

| # | lite method | engram counterpart | tag | translation notes |
|---|-------------|--------------------|-----|-------------------|
| 1 | `describe_component()` | — | shim-only | lite introspection; synth from engram stats |
| 2 | `new_session(session_id)` | `new_session(session_id)` | direct | identical |
| 3 | `get_recent_turns(session_id, limit)` | `get_recent_turns(n=10)` | shim-sig | map `limit`→`n`; engram is single-session, drop/validate `session_id` |
| 4 | `add_turn(role, text, session_id)` | `add_turn(role, content, metadata)` | shim-sig | `text`→`content`; set instance session if `session_id` differs |
| 5 | `add_turns_batch(turns, session_id)` | — | lift | loop `add_turn` in shim now; real batch path in engram later |
| 6 | `store_episodes_batch(episodes)` | — | lift | loop `store_episode` in shim now; bulk write later |
| 7 | `store_episode(text, metadata, importance, bypass_filter, bypass_dedup)` | identical | direct | identical signature — confirmed |
| 8 | `search_episodes(query, n, min_importance, days_back, min_relevance, vector_similarity_threshold)` | `search_episodes(query, n, min_importance, days_back, vector_similarity_threshold)` | shim-sig | engram lacks `min_relevance`; post-filter in shim, or minor additive lift |
| 9 | `get_facts(query, fact_type, subject, include_superseded, limit)` | — (semantic layer, no accessor) | lift | shim via `self._em.semantic`; promote to engram accessor later |
| 10 | `get_paired_exchanges(query, n)` | — | lift | distinct from `search_episodes`; shim via episodic w/ pair metadata |
| 11 | `reconcile_chromadb()` | — | lift | genuine maintenance op; shim against `self._em.episodic` store |
| 12 | `build_prompt(...)` | matching superset | direct | engram adds `semantic_query`; contract params all present |
| 13 | `build_prompt_trace(user_message)` | `build_prompt_trace(user_message, ...)` | direct | engram has extra internal kwargs; contract param present |
| 14 | `build_interop_events(user_message)` | `build_prompt_interop(user_message)` | alias | name map only |
| 15 | `augment(request)` | — (covered by `build_prompt`+`PromptAugmenter`) | shim-only | compose; `AugmentRequest/Result` already re-exported |
| 16 | `delete_episode(episode_id)` | — | lift | small; shim via `self._em.episodic` delete; promote later |
| 17 | `forget_session(session_id)` | `clear_session()` | alias | + session translation + build lite return dict |
| 18 | `forget_user_data()` | `clear_all()` | alias | + synthesize `{episodes_removed, sessions_removed}` from layer stats |
| 19 | `index_text(text)` | `index_text(text, document_index, config)` | direct | engram superset; contract param present |
| 20 | `run_lifecycle_maintenance()` | `run_lifecycle_maintenance()` | direct | identical |
| 21 | `get_stats()` | `get_stats()` | shim-sig | both dict; reconcile keys if NB04/tests assert specific shape |
| 22 | `close()` | `close()` | direct | identical |

**Tally:** direct 7 · shim-sig 4 · alias 3 · shim-only 2 · lift 6.
16 of 22 require no engram change.

## Non-ProjectMemory exports

| symbol group | source | tag |
|--------------|--------|-----|
| `AugmentRequest`, `AugmentResult`, `PromptAugmenter` | `engram.memory.augment` | re-export (done) |
| `describe_memory` | `engram.interop` | re-export |
| `trace_to_memory_records` | `engram.interop` | re-export |
| `augment_result_to_interop_result` | lite-only | shim-only / lift to `engram.interop` |
| `Embedder`, `EmbeddingResult`, `BatchEmbeddingResult`, `OllamaEmbedder`, `EmbeddingService`, `EmbeddingCache`, `CachedEmbedder` | `engram.embeddings` | re-export (done) |
| `ChromaDBStore`, `DimensionMismatchError`, `SchemaManager` | `engram.storage` | re-export (done) |
| `SemanticGraph`, `SemanticExtractor`, `ExtractedFact`, `ExtractionResult` | `engram.semantic` | re-export (done) |
| `ForgettingConfig`, `ForgettingPolicy` | `engram.memory.semantic_forgetting` | re-export (done) |
| `detect_contradiction` | `engram.memory.contradiction` | re-export (done) |
| `Telemetry`, `TelemetryEvent`, `log_sink`, `json_file_sink` | `engram.telemetry` | re-export (done) |
| `__version__` | `engram_lite.version` | local (facade discipline — keep) |

## Step 2 work order

1. Write `engram_lite/project_memory.py` as the adapter shim:
   - `__init__(**lite_kwargs)` maps lite constructor kwargs onto an internal
     `engram.ProjectMemory` configured for SQLite + ChromaDB defaults, RTRL
     disabled, advanced retrieval policy off. Store as `self._em`.
   - Implement the 7 **direct** + 4 **shim-sig** + 3 **alias** + 2 **shim-only**
     rows by delegating to `self._em`.
   - Implement the 6 **lift** rows against `self._em`'s internal layers
     (clearly marked `# Step 3 lift candidate`).
2. Replace `engram_lite/__init__.py` interop imports:
   `describe_memory`, `trace_to_memory_records` → `from engram.interop import ...`;
   keep `augment_result_to_interop_result` local until lifted.
3. Delete the reconciled subpackages: `embeddings/`, `storage/`, `semantic/`,
   `retrieval/`, `prompting/`, `memory/`, `cli/`, `config/`, `contracts.py`,
   `concurrency.py`, `telemetry.py`, `inspection.py`, plus the old
   `interop.py` body once re-pointed.
4. Run, in order: `test_public_api_contract.py`, full `engram_lite` suite,
   full `engram` suite, `integration_tests/`, then NB04 end-to-end.
5. Update `PACKAGE_ROLES.md` and `VISION.md`.

## Lite-invariant enforcement

The shim must **not** expose engram's advanced methods (`respond`,
`synthesize_now`, `audit_memory`, `get_context`, `export_dataset`,
`run_strategy`, etc.). `test_no_unexpected_public_methods` in the contract
test already guards this — the shim's public surface is exactly the 22 rows above.

## Step 3 backlog (lift candidates, deferred)

`add_turns_batch`, `store_episodes_batch`, `reconcile_chromadb`,
`get_paired_exchanges`, `get_facts`, `delete_episode`,
`augment_result_to_interop_result`. Promote from shim-implemented to
first-class engram features when there's reason to; each is shim-covered
in the interim so the lite contract holds regardless.
