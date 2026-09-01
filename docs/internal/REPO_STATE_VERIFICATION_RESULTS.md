# Repo-State Verification — Results (2026-06-22)

Companion to [`REPO_STATE_VERIFICATION.md`](./REPO_STATE_VERIFICATION.md). Records the verdict for each item.

**Scope limit (read first):** this pass was run against an uploaded repo *snapshot*, applying steps 1–3 of the
method (NAME grep, CONCEPT grep, READ). **Step 4 (run the tests) was NOT executed** — no working venv/deps in
the review environment. So every "built-and-working" verdict below means *structurally complete and wired, not
a stub* — it does NOT mean the tests pass. Two things must still be done on the live tree:
1. Run the named test files; "exists and is wired" ≠ "passes."
2. Re-confirm the live working tree matches this snapshot — A1 below is direct proof that snapshot-vs-snapshot
   can differ, so a 10-second live `ls`/test re-check is warranted before striking anything permanently.

## Part A — "already built" claims (file-existence is not completion)

- **A1 TurboQuant KV-cache compression — BUILT-AND-WIRED (snapshot); PATH DISCREPANCY RESOLVED.**
  Present at `llm_engines/src/llm_engines/optimizations/turboquant.py` (288 lines, with a `.pyc` → it has been
  imported). `TurboQuantEngine` implements `get_capabilities()` with `kv_cache_compression=True`,
  `kv_cache_compression_modes=["turboquant"]`, plus `generate`/`stream`/`_encode`/`vram_saved_estimate_mb`; and
  `resources.py:316–322` consumes the flag for VRAM estimation. Not a stub. The earlier "`ls` fails — path
  absent" was a **stale/older snapshot** (false-absent); this newer upload has the file. Action: run its tests
  on the live tree, then strike from backlog.
- **A2 vLLM backend — BUILT-AND-WIRED (snapshot).** `backends/vllm.py` (344 lines), `vLLMEngine` implementing
  ChatModel/LogprobModel/AsyncStreamingModel/BatchChatModel (`generate`, `generate_with_logprobs`,
  `stream_async`, `generate_batch`). Wired into the factory registry: `factory.py:65`
  `"vllm": "llm_engines.backends.vllm.vLLMEngine"`. Not orphaned. Action: run `test_vllm_backend.py` live.
- **A3 propose_then_verify — BUILT (snapshot); distinction PRESERVED.** `strategies/propose_then_verify.py`
  (247 lines), `ProposeThenVerifyEngine` = draft N candidates → verifier SELECTS best (`_select_best`, "select
  the single best response verbatim"). It is best-candidate **selection**, explicitly NOT finding-refutation.
  This confirms the A4/B1 distinction: it is not an AdversarialValidator. Action: run `test_propose_then_verify.py`.

## Part B — "absent / deferred" claims (confirm absence by CONCEPT, not name)

- **B1 AdversarialValidator (separate-model debater / finding-refutation) — ABSENT (confirmed by concept).**
  Name-grep empty. The concept-hits (`scripts/compare_adjudication_strategies.py`,
  `adjudicate_neural_memory_probe.py`) are the knowledge-MVP claim-relation adjudication (policy-driven labels
  like `directly_refuted`/`resolved_against` over claim relations, single-model proposal + policy application) —
  NOT a separate-model debater arguing against agent findings. Different capability; absence holds. (Verdict from
  reading structure, not running.)
- **B2 SemanticDeduplicator (collapse equivalent findings from parallel agents) — ABSENT (confirmed).** Dedup in
  engram is storage/episode-level: `dedup_threshold`, `text_similarity(...) >= dedup_threshold`, `dedup_blocked`
  stats, `deduped_retrieval`, `dedupe_ranked_rows`. That is near-duplicate episode/retrieval-row dedup, not
  finding-level semantic collapse from parallel agents. Storage dedup ≠ the claimed capability; absence holds.
- **B3 Deterministic citation verifier (substring quote-check + ungrounded-numeric) — ABSENT (confirmed).** The
  `SubstringMatchEvaluator` in `rag_lib/eval/broken_rag_lab.py` is answer-correctness matching
  (`expected_texts`/`forbidden_texts`) in a broken-vs-repaired demo, not citation-grounding. `ragas_runner.py`
  has no citation/grounded/ungrounded/quote/numeric logic. The substring primitive exists for a different
  purpose; the claimed verifier is absent.
- **B4 Two-step synthesis for engram (analyze call + generate call) — ABSENT / NOT-APPLICABLE (confirmed).**
  engram's only model calls are optional LLM **fact-extraction at ingestion** (`semantic/extractor.py`,
  `enable_llm`-gated, `_extract_with_llm` → `llm_engine.generate`). `contribute_to_prompt` returns a `PromptHint`
  (augmentation / hint-assembly), not a two-call synthesis. engram is not a synthesizer, so the capability does
  not apply — it is not a single-pass synthesis awaiting a split.
- **B5 Gap analysis ("what the memory doesn't know yet") — ABSENT (confirmed).** The `missing`/`not found` hits
  in engram are storage-integrity reconciliation (ChromaDB-vs-JSONL rebuild, lock-file/PID, node-not-found), not
  a retrieval-output coverage/"what's missing" signal. No gap-coverage field in retrieval output.

## Part C — verify-before-acting

- **C1 PipelineStage — a step abstraction ALREADY EXISTS; do NOT add a parallel one without a sufficiency
  check.** `agent_lib` has `AgentStep` (contracts, used across `interop.py`/`programming.py`) and `PlanStep`
  (`programming.py:74`). Before introducing any `PipelineStage`, evaluate whether `AgentStep`/`PlanStep` suffice;
  default is do-not-add (exists-under-other-name).
- **C2 Cache observability (TTFT, cache-hit, prefix-reuse) — ABSENT from `llm_inspector` traces (confirmed); raw
  hook exists upstream.** No `ttft`/`cache.hit`/`prefix.reuse` in `llm_inspector/src`. But
  `llm_engines/contracts/engine.py:177` notes cache data "populated by backends that expose cache data (vLLM,
  some llama.cpp …)". So the inspector-level observability is a genuine gap; the raw cache data may be available
  upstream in the engine contract. If the gap is acted on, surface the existing engine cache field into the
  inspector trace rather than inventing a new source.
- **C3** folds into B4 (resolved above).

## Part D — forcing-function reframe (SETTLED 2026-06-22)

**Meta-finding (the dominant disposition driver was absence-of-USE, not absence-of-design).** Four of the five
items below could not be forced because nothing has exercised the foundations enough to fail. The maintainer's
own framing: `ai_tools` has been a forcing function on *learning* — building the kinds of capabilities described
in articles, to learn LLMs and local hosting by constructing them — but nothing built so far provides
functionality the maintainer would *use every day*. So the binding constraint on the backlog is not more
capability; it is use. Every CUT below was cut because no run exists to force it, not because the capability is
unsound. The highest-leverage next move is therefore to run the existing foundations against real, daily work
until they fail in specific ways — which both forces real backlog items and fills the self-improvement substrate
(`SELF_IMPROVEMENT_DESIGN_NOTE.md`). Read the cuts as "no forcing run yet," not "bad idea."

Disposition vocabulary: **KEEP-DORMANT** = forcing run is on the maintainer's path and nameable but has not
fired (don't build until it does); **CUT / revive-on-trigger** = no qualifying run exists yet, with a predeclared
revival condition; **CUT** = forcing run belongs to a different architecture, or the capability does not apply.

| item | forcing run that fails without it | status | disposition |
|---|---|---|---|
| citation verifier | a RAGAS eval (rag_lib + dissertation ground truth) surfacing an ungrounded/numeric-hallucinated citation | run is on-path, NOT yet fired (tool not used at volume) | **KEEP-DORMANT.** Trigger: first ungrounded citation in a RAGAS run. Build as a *deterministic extension* of the existing `SubstringMatchEvaluator` (substring quote-presence + ungrounded-numeric); never an LLM grounding-judge. |
| AdversarialValidator (component) | a run producing a finding needing independent refutation | not fired | **CUT (component).** The MDASH separate-model refuter is not built. |
| context isolation between evaluating agents (the invariant under AdversarialValidator) | same-context vs artifact-only critic against a deliberately flawed input; measure false-ratification delta | probe not run | **PROMOTED (invariant).** Recorded as a gated hypothesis, not a feature — see note below. Substance of the typed-critic contract (ASC gap #4) and Lesson 6. |
| gap analysis | a retrieval *consumer* producing a wrong/overconfident answer traceable to undetected missing coverage | consuming run does not exist yet | **CUT / revive-on-trigger.** Revive when such a consumer is built and fails this way. |
| SemanticDeduplicator (finding-level) | parallel agents producing duplicate findings pre-synthesis | belongs to parallel-agent topology (sibling system), not this one | **CUT.** Not this architecture's problem. |
| two-step synthesis | n/a — engram is not a synthesizer (B4) | n/a | **CUT.** Capability does not apply. |

**Promoted invariant — context isolation between evaluating agents (gated hypothesis).** When one agent
evaluates, reviews, verifies, or critiques another agent's output, the evaluator should receive the *artifact*,
not the producing agent's context/transcript. Rationale: a shared context pulls the evaluator toward ratifying
the producer's reasoning (Lesson 6, observed in the sibling system's single-vs-per-agent-window result). Scope:
touches the typed-critic contract (ASC gap #4), the LIVE coordinator/worker wiring (currently isolated by
construction via separate `ExternalAgentSession` contexts, but not *required* to be — a future change threading
worker reasoning into the coordinator would silently break it), and any future reviewer/verifier. Status:
single qualitative observation, NOT yet reproduced locally — treat as a hypothesis with a predeclared gate, not a
rule. Falsification probe: same-context vs artifact-only evaluation against a deliberately flawed input; if
isolation does not measurably reduce false ratification on local models, drop it (clean-null discipline). If it
does, encode it as a wiring rule / ADR and an assertion in the LIVE harness (coordinator never receives worker
transcripts). Do not build a critic or validator component to test this — the probe needs only the isolation
boundary and a flawed input.

## Net

- Part A: all three built-and-wired in the snapshot, not stubs. A1's false-absent is resolved (stale snapshot).
  Remaining: run the three test files live, and re-confirm the live tree matches.
- Part B: all five absences confirmed by concept-grep + read. B4 is not just absent but not-applicable.
- Part C: C1 already-exists (don't duplicate); C2 inspector-gap real, upstream data present.
- Part D: SETTLED. citation verifier = KEEP-DORMANT (deterministic extension, trigger on first ungrounded
  citation); AdversarialValidator component = CUT, with the context-isolation invariant PROMOTED as a gated
  hypothesis; gap analysis = CUT/revive-on-trigger; SemanticDeduplicator + two-step synthesis = CUT. Dominant
  driver was absence-of-use, not absence-of-design (see Part D meta-finding): the next high-leverage move is
  using the foundations until they fail in forcing ways, not building more capability.

The asymmetry the checklist warned about held in practice: the one error found was a **false-absent** (A1,
caused by a stale snapshot), and the absence claims (Part B) all survived concept-level scrutiny. No
false-present-of-built was found — the "already built" claims were real.
