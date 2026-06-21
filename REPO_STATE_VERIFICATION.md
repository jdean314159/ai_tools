# Repo-State Assessment — Verification Checklist

**Purpose:** convert the article-assessment thread's repo claims from filename-inspection
into verified facts. The assessment made errors in BOTH directions and must be checked
symmetrically:

- **False-present:** asserting a capability is "already built, remove from backlog" based
  on a file/class name existing. (A file existing is not a feature working.)
- **False-absent:** asserting a capability is "absent / still deferred" based on a name
  grep returning nothing. (A capability can exist under a different name.)

**Both classes of claim get the same standard:** grep for the CONCEPT and the BEHAVIOR,
not the identifier; then read the code; then run its tests. A filename is a lead, not a
fact — the same discipline the NetFlow campaign applied (a high rank is a lead, not a
detection; a spec mentioning a function is not the function working).

**Live spot-check already invalidated two claims** (recorded here so they aren't re-trusted):
- `llm_engines/optimizations/turboquant.py` — asserted "already built." **`ls` fails in the
  current repo copy — path absent.** Resolve before striking TurboQuant from backlog
  (wrong path? moved? this copy stale? assessment erred?).
- "AdversarialValidator absent" / "SemanticDeduplicator absent" — name-grep empty, but
  CONCEPT-grep hits: `scripts/compare_adjudication_strategies.py`,
  `adjudicate_neural_memory_probe.py` (adversarial/auditor concept);
  `engram/memory`, `rag_lib/storage/chroma.py`, `chunker.py` (dedup concept). Must read
  these to confirm they are NOT the claimed capability under another name.

---

## Method (apply to every item below)

```
1. NAME grep:    grep -ril "<ClassName>" --include="*.py" .
2. CONCEPT grep: grep -ril "<behavior synonyms>" --include="*.py" .
3. READ:         view the candidate files; confirm the capability does/doesn't do the thing.
4. TEST:         run the associated tests; "exists" != "passes". Note pass/fail/absent-tests.
5. VERDICT:      built-and-working | partial/stub | absent | exists-under-other-name
```

A claim is only resolved when steps 1-4 agree. Name-grep alone resolves nothing.

---

## Part A — "Already built, remove from backlog" claims (CONFIRM, do not assume)

These were asserted as done. File-existence is not completion. Read + test each.

### A1. TurboQuant KV-cache compression
- **Claim:** full `TurboQuantEngine` at `llm_engines/optimizations/turboquant.py`,
  `kv_cache_compression` in `EngineCapabilities`.
- **STATUS: path failed live `ls`.** First task: locate it. `grep -rl "TurboQuant\|turboquant\|kv_cache_compression" --include="*.py" .`
- If found: read it, confirm KV compression + VRAM estimation + streaming are implemented
  (not stubbed), run its tests. Only then strike from backlog.
- If not found: the "already built" claim is FALSE for this repo state; TurboQuant returns
  to the backlog (or the repo copy is stale — determine which).

### A2. vLLM backend
- **Claim:** first-class backend at `llm_engines/backends/vllm.py`, recommendation already done.
- Evidence-for: `llm_engines/tests/test_vllm_backend.py` exists in this copy.
- Verify: read `backends/vllm.py`; confirm it implements the backend Protocol (not a stub);
  run `test_vllm_backend.py`. Confirm it's wired into the backend registry/factory, not
  orphaned.

### A3. propose_then_verify
- **Claim:** exists at `llm_engines/strategies/propose_then_verify.py`; response-level
  draft/verify; explicitly NOT token-level speculative decoding.
- Evidence-for: `test_propose_then_verify.py` exists in this copy.
- Verify: read it; confirm the draft/verify-select behavior; run the test.
- **CRITICAL distinction to preserve:** confirm it is best-candidate-SELECTION, and is NOT
  the same as AdversarialValidator (finding-REFUTATION). If verification shows it already
  does auditor-style argue-against-findings, that changes the A4 negative claim. If it only
  selects best candidate, the distinction holds and AdversarialValidator stays genuinely
  deferred.

---

## Part B — "Absent / still deferred" claims (CONFIRM ABSENCE by concept, not name)

The mirror error. Each was called absent on a name grep. Re-check by concept; read the
concept-hits to confirm they are not the capability under another name.

### B1. AdversarialValidator (separate-model debater / finding-refutation, MDASH pattern)
- Name-grep: empty (confirmed).
- **Concept-grep hits to READ:** `scripts/compare_adjudication_strategies.py`,
  `scripts/adjudicate_neural_memory_probe.py` — these implement adjudication/auditor
  strategies. Determine whether either already IS a separate-model debater arguing against
  findings. If yes → not absent, exists under another name. If they're best-candidate or
  single-model adjudication → absence confirmed, correctly deferred.
- Additional concept terms: `debate`, `critic`, `challenge`, `rebut`, `counter-argument`,
  `second model`, `auditor model`.

### B2. SemanticDeduplicator (collapse equivalent findings from parallel agents)
- Name-grep: empty (confirmed).
- **Concept-grep hits to READ:** `engram/src/engram/memory/`, `rag_lib/storage/chroma.py`,
  `rag_lib/ingestion/chunker.py`, `engram/interop.py`, `project_memory.py`. These contain
  dedup logic — but likely STORAGE/vector dedup (near-duplicate chunks), NOT finding-level
  semantic collapse from parallel agents. Read to confirm the distinction. Storage dedup ≠
  the recommended capability; if only storage dedup exists, B2 absence holds.
- Additional terms: `collapse`, `merge`, `equivalent`, `near-duplicate`, `cluster findings`.

### B3. Deterministic citation verifier (substring quote-check + ungrounded-numeric)
- Claim: absent from `rag_lib/eval/ragas_runner.py`.
- Concept-grep across rag_lib eval: `grep -ril "citation\|quote.*verif\|substring\|ungrounded\|grounded\|numeric.*check" rag_lib/ --include="*.py"`
- Read `rag_lib` eval harness (`broken_rag_lab.py`, eval/) — confirm whether grounding/quote
  verification exists in any form. Note: `validate_decision_history.py` in scripts/ does
  deterministic validation for a DIFFERENT artifact (ADR decision-history); confirm it's not
  being conflated with citation verification.

### B4. Two-step synthesis for engram (separate analysis call + generation call)
- Claim: not visible; engram may do single-pass synthesis.
- Read `engram/src/engram/` synthesis path directly. Concept: does any synthesis routine
  make TWO model calls (analyze, then generate) or one? Two calls inside one function won't
  show as a class name — must read the call sites.
- `grep -rn "synthesi\|def.*synth\|analyze.*generate\|two.step\|two.pass" engram/ --include="*.py"`

### B5. Gap analysis ("what the memory system doesn't know yet")
- Claim: not apparent in engram retrieval.
- Concept, not class: a `GapAnalysis` type is unlikely; look for a coverage/missing/unknown
  signal in retrieval output. `grep -rn "gap\|coverage\|missing\|unknown\|not.*found\|absent" engram/src/engram/ --include="*.py"`
- Read retrieval return types — is there any "what's missing" field, or only "what's found"?

---

## Part C — Verify-before-acting items (the assessment already flagged these; same method)

### C1. PipelineStage base class
- Before adding: read `agent_lib/src/agent_lib/runtime.py` and `planners.py`. Does a stage/
  step abstraction already exist (the assessment lists `AgentStep`, `PipelineStage`-like
  Protocols in contracts.py)? `grep -rn "class.*Stage\|PipelineStage\|AgentStep\|def step" agent_lib/ --include="*.py"`
- Verdict: if a stage abstraction exists and is sufficient, do NOT add a parallel one.

### C2. Cache observability (TTFT, cache-hit rate, prefix reuse)
- Before assuming the gap: read `llm_inspector` trace/event model. `grep -rni "ttft\|time.to.first\|cache.hit\|prefix.reuse\|cache.*rate" llm_inspector/ --include="*.py"`
- Verdict: present in trace events already / partially / absent.

### C3. (folds into B4) engram synthesis path — same read as B4.

---

## Part D — Reframe the deferred backlog by FORCING FUNCTION (the missing discipline)

The assessment sorted items by built-status. The repo's governing rule is: **build a
capability only when a concrete run fails without it.** Re-sort every still-deferred item
(confirmed-absent in Part B) by its forcing function:

For each: **name the concrete run that fails without it, and state whether that run has
occurred.**

| item | forcing run | has it happened? | disposition |
|---|---|---|---|
| AdversarialValidator | a diagnostics/agent run that produces a finding needing independent refutation | ? | defer until run exists |
| SemanticDeduplicator | a parallel-agent run producing duplicate findings pre-synthesis | ? | defer / may never need |
| citation verifier | a rag_lib eval run surfacing ungrounded citations | ? | defer until eval shows the failure |
| two-step synthesis | an engram synthesis producing conflated analysis+generation errors | ? | defer until single-pass fails |
| gap analysis | a retrieval run where "what's missing" is needed and absent | ? | defer until needed |

**Disposition rule:** an item with an identifiable, imminent forcing run → keep on backlog,
note the trigger. An item where you cannot name a failing run → candidate to CUT, not carry.
Carrying speculative backlog indefinitely is its own drift. The point isn't to build these;
it's to know which are approaching their trigger and which are perpetual maybes.

---

## Done criteria for the verification pass

- [ ] A1-A3 each resolved to built-and-working | partial | absent (with test results), not
      assumed. TurboQuant path discrepancy resolved first.
- [ ] B1-B5 absence confirmed by CONCEPT grep + reading the concept-hits, not name grep.
      Any "exists under another name" findings recorded.
- [ ] C1-C3 checked against existing code before any addition.
- [ ] propose_then_verify vs AdversarialValidator distinction confirmed by reading both
      (or confirming the latter's absence), so neither is duplicated nor wrongly skipped.
- [ ] Part D table filled: every deferred item has a named forcing run and a keep/cut
      disposition.
- [ ] The three "remove immediately" claims are struck ONLY after Part A confirms them by
      test, not by file-existence.

The asymmetry that motivated this: the original recommendations erred false-absent
(recommended what existed); the assessment erred false-present-of-absence (declared absent
what wasn't name-matched). One grep pair (name + concept) plus a read plus a test resolves
both. Filename inspection resolves neither.
