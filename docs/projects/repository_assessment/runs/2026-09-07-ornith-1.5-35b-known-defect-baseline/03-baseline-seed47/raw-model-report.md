# Repository Assessment: `ai_tools`

## Executive Verdict

The repository is a large, well-documented modular LLM harness. I found **one high-confidence, currently actionable defect** in the `engram` package: the public `ProjectMemory.get_facts()` method bypasses the application-assigned `MemoryTrustPolicy`, returning untrusted/cross-tenant "poison" facts that the composition-time filter (`build_prompt`) and retrieval filter (`search_episodes`) both reject. This is a genuine security-boundary gap in a fail-closed trust system, and it is reachable through the public API. It matches the exact finding the repo's own verification handoff (`CLAUDE_THREAD_HANDOFF.md`) flagged as **OPEN** — it has never been independently reproduced by running code, and no test exercises it.

All other inspected areas (trust policy enforcement, packaging, agent sandboxing, loop guard, interop contracts) held up under inspection; those hypotheses are recorded as rejected/downgraded below.

---

## Validated Finding

### F1 — `ProjectMemory.get_facts()` bypasses the trust policy (Security / Data Integrity)

- **Severity:** High (medium blast radius: only when a trust policy is enabled AND the semantic graph is in use AND the caller reads facts via `get_facts`).
- **Location:** `engram/src/engram/project_memory.py`, `ProjectMemory.get_facts` (lines ~1691–1733), which calls `SemanticGraph.query_facts` (`engram/src/engram/semantic/graph.py`, lines ~102–146) with no `recall_decision`/tenant/trust check.
- **Impact:** With a `MemoryTrustPolicy` configured, `get_facts()` returns facts from other tenants, below-minimum-trust, quarantined, or disallowed-source records. The documented boundary ("an external retriever cannot bypass the policy") is true only of `build_prompt` composition; `get_facts` is an unfiltered public escape hatch that can feed untrusted data into downstream consumers (reports, downstream prompts, other systems).
- **Evidence (empirically reproduced):**
  - `get_facts()` calls `self.semantic.query_facts(...)` directly — no trust call anywhere in the method (confirmed by reading lines 1691–1733).
  - `search_episodes` (line ~1543) and `_apply_composition_trust_policy` (line ~1871) both call `self.trust_policy.recall_decision(...)`; `get_facts` does not.
  - Reproducer (`/tmp/repro_getfacts4.py`) with a policy (`tenant_id=acme`, allowed sources/writers set) storing one `tenant=acme` fact and one `tenant=other` fact directly into the semantic graph:
    ```
    get_facts() poison present: True
    ```
    The cross-tenant fact is returned. The same facts are filtered out by `build_prompt` (`build_prompt contains 'poison': False`).
- **Remediation direction (minimal):** In `get_facts`, after `query_facts`, apply `self.trust_policy.recall_decision(fact.get("metadata"))` filtering when `self.trust_policy is not None` (fail closed), mirroring `search_episodes`. Because extracted facts carry only `{role, session_id}` (no inherited trust/tenant), also address F2. Prefer a shared helper so retrieval and fact-reads share one boundary.

---

## Rejected / Downgraded Hypotheses

- **F2 (downgraded, related to F1):** `_extract_and_store_facts` writes `metadata={"role":..., "session_id":...}` without inheriting the source episode's trust/tenant (handoff item 2). This is real but lower severity: it means enabling a policy silently drops extracted facts from *prompts* (composition covers the `semantic` origin), and separately, `get_facts` returns them unfiltered. The fix (inherit from source episode) is correct for extraction but asserts a verified fact is verified — an inference the handoff correctly notes belongs in an ADR, not the extractor. I did not validate this as a separate defect because it composes with F1 and is best fixed together; it is documented here for the same remediation.
- **`get_facts` coverage gap (downgraded):** No test in `test_trust_policy.py` touches `semantic`/`get_facts`; the only `get_facts` test is in `test_semantic.py` with no policy. This is a test-gap observation (same shape as the repo's own INC-017 note), not a code defect. Recommend adding a regression test alongside the F1 fix.
- **Agent sandbox / command isolation (`agent_lib`):** Inspected `programming_workspace.py` (`_resolve_command_isolation_backend`, `_build_container_command`, `_command_allowed`, `_path_matches_allowlist`, env allow/deny). Docker/podman isolation with `--network none`, `--rm`, user mapping, and host fallback is correctly gated; host fallback requires `command_isolation_fallback_to_host=True`. No bypass found. The handoff itself notes this is *not* a general container-security audit (resource limits, seccomp, escape resistance unvalidated) — correctly scoped. **Rejected as a defect.**
- **Packaging / publication hygiene:** `pyproject.toml`, `conftest.py` (monorepo bootstrap), `pytest.ini` (pythonpath), and the handoff's verified fail-closed publication gate all appear sound. **Rejected.**
- **`action_trajectory_loop_guard`:** `detect_and_redirect`/`assess_trajectory` use deterministic novelty + near-duplicate detection with documented thresholds; no logic defect found. **Rejected.**
- **`llm_engines` interop / `tool_not_granted` classification:** The handoff notes Inspector misclassifies `tool_not_granted` as a generic invocation failure, but states this was corrected in version-2 (6/6 parity). I did not re-verify the current classification code (budget exhausted); downgraded to "reported, not re-verified."

---

## Commands / Tests Run

1. `cat` of `AGENTS.md`, `AGENT.md`, `README.md`, `docs/design/VISION.md`, `docs/internal/STATUS.md`, `docs/internal/CLAUDE_THREAD_HANDOFF.md` — established architecture, posture, and the OPEN finding list.
2. Read `engram/src/engram/project_memory.py` (`get_facts`, `search_episodes`, `build_prompt`, `_apply_composition_trust_policy`, `_extract_and_store_facts`), `engram/src/engram/semantic/graph.py` (`query_facts`), `engram/src/engram/trust.py` (`recall_decision`), `engram/docs/trust_policy.md`.
3. `python3 /tmp/repro_getfacts4.py` — **confirmed** `get_facts()` returns a cross-tenant fact while `build_prompt` filters it.
4. `python3 /tmp/repro_compare.py` — confirmed the same: `get_facts() poison present: True`; `build_prompt contains 'poison': False`.
5. Inspected `agent_lib/src/agent_lib/programming_workspace.py`, `tools.py`, `runtime.py`, `action_trajectory_loop_guard/detector.py`, `llm_harness_core` contracts.

Note: Per the repo's own testing policy and the handoff's constraint, I did **not** run the full pytest suite (no network; `engram`/chromadb tests are gated behind `--run-engram`). The reproductions above import `engram` directly from `engram/src` and ran successfully (only a benign `tiktoken` word-count warning).

---

## Remaining Uncertainty

- **Medium.** The single validated defect (F1) is reproduced and high-confidence. Remaining uncertainty is around (a) whether `get_facts` is reachable in the active product path (it is a public method but the repo states "No application campaign is currently active"), and (b) the un-re-verified `tool_not_granted` classification claim. The repository gate is reported at 1,254 passed / 305 skipped, but I did not run it. No new defects beyond F1 were found in the areas inspected.
