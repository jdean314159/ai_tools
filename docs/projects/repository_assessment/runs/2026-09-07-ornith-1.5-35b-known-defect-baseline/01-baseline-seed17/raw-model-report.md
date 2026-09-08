# Repository Assessment: `ai_tools`

## Executive Verdict

The repository is a large, well-documented modular LLM-harness suite. I performed a read-only, code-level audit focused on the trust/security boundary of the `engram` package (project memory). I **validated two real, currently actionable defects** in the `engram` trust-policy surface, both confirmed by independent reproducers run against the shipped source. Both are consistent with findings already flagged as OPEN in `docs/internal/CLAUDE_VERIFICATION_HANDOFF_2026-09-01.md` (i.e., reported by a prior verification thread but never independently re-verified or fixed). No new defect classes were introduced by the post-handoff code I inspected.

Severity: **Medium** (fail-closed direction; no exploitability without an attacker who can already inject memory; the real harm is that a documented security guarantee is silently violated, undermining trust in the boundary).

---

## Validated Findings

### F1 — `ProjectMemory.get_facts()` bypasses the configured trust policy entirely

- **Symbol / location:** `engram/src/engram/project_memory.py`, `ProjectMemory.get_facts()` (lines ~1691–1737), which calls `self.semantic.query_facts()` directly with no `recall_decision` / tenant / trust check.
- **Impact:** With a `MemoryTrustPolicy` configured, `get_facts()` returns untrusted / cross-tenant / quarantined extracted facts. This contradicts the documented guarantee in `engram/docs/trust_policy.md` line 42: *"an external retriever cannot bypass the policy"* — which is only true of `build_prompt` (composition-time filtering at `project_memory.py:1871-1932`). `search_episodes` and `build_prompt` filter; `get_facts` does not.
- **Evidence (reproducer run):** With `min_ingest_trust=min_recall_trust=VERIFIED`, a stored correction fact `password = hunter2` (trust untrusted, tenant `other`) is returned by `get_facts(subject="password")` — 1 fact, `trust=None`. The same content is filtered out of `build_prompt` (`composition trust filtered_count` excludes it). So the two recall paths diverge: `build_prompt` → no facts; `get_facts` → unfiltered facts.
- **Remediation direction:** Route `get_facts` through the same `recall_decision` filter used by `search_episodes`/`_apply_composition_trust_policy` (fail closed on missing trust/tenant), and/or document that `get_facts` is explicitly policy-unfiltered. Prefer the filter; the doc currently implies uniform enforcement.

### F2 — Extracted facts carry no trust/tenant/source/writer metadata

- **Symbol / location:** `engram/src/engram/project_memory.py`, `_extract_and_store_facts()` (lines ~968–1019), `add_fact(..., metadata={"role": role, "session_id": session_id})`.
- **Impact:** Facts derived from a verified source episode inherit no trust metadata. When a trust policy is enabled, composition-time filtering silently drops **every** extracted fact from prompts (fail-closed, so safe, but undocumented and surprising). Conversely, via `get_facts` (F1) the facts are returned unfiltered. The two compose in opposite directions.
- **Evidence (reproducer run):** After extraction, `get_facts(...)[0]["metadata"]` == `{'role': 'user', 'session_id': 's1'}` — no `trust`/`tenant`/`source`/`writer`. With a policy on, these fail the recall trust check and are dropped from prompts.
- **Remediation direction:** Inherit trust/tenant/source/writer from the source episode at the extraction call site (the `source_episode_id` is already available). Note: this asserts a derived fact is as trustworthy as its source — a policy/ADR decision, not something to bake into the extraction function unilaterally (the handoff flags exactly this boundary).

### F3 — Coverage gap (supporting, lower severity)

- **Location:** `engram/tests/test_trust_policy.py` — no test exercises `semantic`/`get_facts`; the single `get_facts` test lives in `test_semantic.py` with no policy configured.
- **Impact:** The exact failure surface in F1/F2 is unexercised, so regressions to the trust boundary here would not be caught.
- **Remediation direction:** Add a policy-enabled test asserting `get_facts` filters untrusted facts (and documents the intended behavior).

---

## Rejected / Downgraded Hypotheses

- **`get_facts` returning untrusted facts via the public `store_episode`/`add_turn` auto-ingest path:** Downgraded. The auto-ingest path in `add_turn` (line ~838) applies the ingestion policy and rejects untrusted turns, so fact extraction is gated behind a successful, policy-passing store. I confirmed the extraction is only reachable through a passing store (or the internal `_extract_and_store_facts` call). This narrows F1/F2's *default* reachability but does not remove them: the public `get_facts` API still has no filter, and the internal extraction path still writes untrusted metadata. The finding stands as a public-API contract gap.
- **Any defect in `llm_engines` / `llm_inspector` / `rag_lib` / `agent_lib`:** No validated defect found in the packages I inspected. The handoff notes (e.g., `tool_not_granted` misclassification) are disclosed as already-fixed in a later tree.
- **Git-history-based findings:** Not applicable — no `.git` present in this checkout (consistent with the handoff's note that the publication gate fails closed without `.git`).

---

## Commands / Tests Run

1. `cat` of `AGENTS.md`, `README.md`, `docs/design/VISION.md`, `docs/internal/STATUS.md`, `docs/internal/CLAUDE_THREAD_HANDOFF.md`, `docs/internal/CLAUDE_VERIFICATION_HANDOFF_2026-09-01.md` — established scope and the OPEN findings.
2. `grep -rn "get_facts\|query_facts\|_extract_and_store_facts" engram/src/` — located the call sites.
3. Read `engram/src/engram/project_memory.py` (lines 820–1020, 1430–1580, 1680–1740, 1860–1998), `engram/src/engram/semantic/graph.py` (`query_facts`), `engram/src/engram/trust.py`, `engram/docs/trust_policy.md`, `engram/src/engram/semantic/extractor.py`, `engram/src/engram/memory/quality.py` — traced the trust-filtering paths and confirmed `get_facts`/extraction bypass them.
4. Reproducers in `/tmp` (against read-only `/workspace` source, scratch only in `/tmp`):
   - `repro_engram10.py` — **passed.** With a VERIFIED policy, `get_facts(subject="password")` returns the untrusted fact `password = hunter2` (`trust=None`), and the extracted fact metadata is `{'role': 'user', 'session_id': 's1'}` (no trust fields). `build_prompt` filters the same content.
   - `repro_engram9.py` / `repro_engram8.py` — confirmed the auto-ingest path rejects untrusted turns (so extraction is gated), narrowing default reachability.
   - `repro_engram3.py` / `repro_engram4.py` — characterized the extractor's correction-pattern requirements (single-word subject).

---

## Remaining Uncertainty & Uninspected Areas

- **Uncertainty: medium.** F1/F2 are confirmed by direct execution against shipped source, but I could not run the repo's pytest suite (no `.git`; the handoff confirms Claude's container had no pytest/pydantic/ruff/mypy and no network). Reachability through the *default* public API is narrowed because auto-ingest enforces the ingestion policy before extraction.
- **Uninspected:** `llm_engines` engine backends and their `not_declared`/thinking plumbing (only confirmed present, not executed end-to-end); `agent_lib` sandbox/command-isolation; `rag_lib` ingestion; `llm_inspector` rendering/interop; packaging/`Makefile` publication gate; concurrency/`fork` behavior. These were not exercised.
- The documented docstring claim in `trust_policy.md` (line 42) may itself be the artifact to correct even if `get_facts` is intentionally unfiltered — i.e., the fix could be documentation-only. I could not determine intent from code alone.
