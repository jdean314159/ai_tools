# Fresh Codex thread handoff

- Prepared: 2026-08-30
- Repository: `/home/cybernaif/repos/ai_tools`
- Current focus: Engram reliability and trust-boundary work complete

## Read order

1. `AGENTS.md`
2. `docs/design/VISION.md`
3. `docs/internal/STATUS.md`
4. `docs/internal/ROADMAP.md`
5. `docs/projects/ENGRAM-TEMPORAL-AND-MEMORY-EVAL-2026-08-30.md`
6. `docs/projects/ENGRAM-MEMORY-SECURITY-2026-08-30.md`
7. `docs/projects/ENGRAM-TRUST-POLICY-LIVE-VALIDATION-2026-08-30.md`
8. `docs/projects/ENGRAM-TRUST-AVAILABILITY-2026-08-30.md`
9. `docs/projects/ENGRAM-TRUST-REVIEW-WORKFLOW-2026-08-30.md`

Do not read `SESSION_HANDOFF.md` end to end; it is a historical log.

## Completed Engram sequence

The work progressed through evidence rather than assuming a design:

1. Temporal memory retained history while suppressing superseded current facts.
2. Item-level prompt packing and staged memory evaluation improved attribution.
3. Clean base and Sentence Transformers/Chroma wheel installations passed.
4. The original five-family security probe found untrusted content crossing
   storage, retrieval, and composition in 5/5 cases, although the model resisted
   all five attacks.
5. `MemoryTrustPolicy` added opt-in trust, tenant, source, and writer enforcement,
   reject/quarantine behavior, external-retriever composition filtering,
   provenance labels, diagnostics, and audit events.
6. The paired DGX Spark validation reduced poison storage/retrieval/composition
   from 5/5 to 0/5. A disclosed citation regression exposed a missing
   `evidence_id` label; the corrected version passed security and exact utility
   gates in 5/5 cases.
7. The availability probe found 0/3 unexpected rejections among fully conforming
   records, while identifying five deliberate workflow blocks and approximately
   37 word-count tokens of prompt overhead.
8. Exact-ID review now supports legacy classification, explicit tenant aliases,
   and quarantine release with persisted review history. The application remains
   responsible for reviewer authentication and authorization.
9. Prompt-pressure validation preserved the first relevant record and exact
   output in 18/18 paired conditions, while trust labels displaced up to four
   otherwise accepted memories in the tested crowded contexts.
10. A deterministic `agent_lib` policy/observability profile exposed and then
    corrected `tool_not_granted` block classification; the corrected profile
    passed enforcement and signal parity in 6/6 cases.
11. The Spark replacement model reported as `Qwen3.8-Flash-Next-UD-IQ4_XS`
    passed the unchanged five-run engine characterization profile in 5/5 runs
    for exact chat, structured output, tool calls, and token log probabilities.
12. Its unchanged tool-decision campaign passed all four cases in three
    repetitions with thinking off and on. Thinking increased median latency in
    every case without changing exact outcomes from the ceiling baseline.
13. Its valid frozen tool-recovery baseline passed all four failure families
    3/3 with zero fabricated success. The ceiling rule stopped the campaign
    before thinking on; version-4 development remains closed.
14. A bounded context-retention profile preserved exact start/end values with
    monotonic server usage at approximately 1K, 8K, and 32K input tokens. It did
    not test the advertised maximum or middle-context retrieval.
15. A real Docker-backed `agent_lib` command-isolation profile passed workspace
    mutation, exact host-marker invisibility, and default network denial in 3/3
    corrected cases without host fallback. The green version-1 artifact is
    retained as infrastructure-invalid because its marker paths differed.
16. Inspector UI can now replay one shared artifact JSON into a read-only
    inspection summary. A supported Flash-Next campaign and an unsupported
    command-isolation profile validate body-summary and envelope-only behavior;
    this does not execute or import the recorded run.
17. Python-quality normalization now has a root Ruff policy and scoped Make/CI
    gate. `llm_harness_core` is the first adopted package; the remaining lint
    and formatting inventory is frozen in
    `docs/internal/PYTHON-QUALITY-ADOPTION.md` for reviewable package passes.
18. Both loop-guard packages and `mail_lib` are now formatted and included in
    that gate. Their combined focused test set passed 84 tests without behavior
    changes; `llm_inspector_ui` is the next adoption package.
19. `llm_inspector_ui` is now lint-clean, formatted, and included in the shared
    gate. Its 44 package tests and the full repository gate passed;
    `agent_lib` is the next adoption package.
20. `agent_lib` is now lint-clean, formatted, and included in the shared gate.
    Its compatibility adapter and two scenario helpers were added to their
    existing `__all__` surfaces and locked by a public-API regression test. The
    full gate now reports 1,268 passed; `llm_inspector` is next.
21. `llm_inspector` is now lint-clean, formatted, and included in the shared
    gate. Dynamic re-export lists were replaced by explicit `__all__` literals,
    and its local Ruff policy now matches the root baseline. Inspector and
    targeted integration tests passed; `rag_lib` is next.
22. `rag_lib` is now lint-clean, formatted, and included in the shared gate.
    Its lazy evaluation import boundary remains intact through a
    type-checking-only return-type import. Package and targeted integration
    tests passed 128 with one skip; the full gate remains at 1,268 passed.
    `llm_engines` is next.
23. `llm_engines` is now lint-clean, formatted, and included in the shared
    gate. Structural-protocol imports were removed while explicit public-import
    smoke checks were retained with narrow annotations. Engine and targeted
    cross-package tests passed 320 with 14 skips; the full gate remains at
    1,268 passed. `engram` is next.

Key commits, oldest to newest:

- `6ae80ff` — temporal memory reliability tooling
- `1b9ec11` — clean packaging validation
- `d58a7cb` — persistent-memory trust-boundary characterization
- `493cfde` — trust-policy enforcement
- `728d766` — paired DGX trust-policy validation and citation correction
- `aebd394` — availability/false-positive characterization
- `b7f7cda` — audited trust-review workflow

## Current evidence boundary

- Live model: llama.cpp-hosted `Qwen3.8-27B-UD-Q4_K_M.gguf` on the DGX Spark.
- Security and availability probes used thinking off, temperature zero, and
  exact judge-free scoring. No oracle or LLM judge was used.
- Results are bounded synthetic characterizations, not general security or
  field false-positive-rate claims.
- The review workflow has deterministic persistence tests but no separate live
  model experiment because it changes metadata enforcement, not inference.
- JSONL review history is inspectable but not tamper-evident. Compliance use
  requires a protected external telemetry/audit sink.
- Working-session turns remain outside the persistent-memory trust policy.

## Recommended next assignment

Do not extend the policy from this bounded matrix. Choose one next validation:

1. Run the deferred thinking-on version of the frozen paired security profile,
   preserving all cases and scorers; or
2. Return to the broader `ai_tools` capability inventory and select the next
   unvalidated package capability one at a time.

The Engram prompt-budget choice, first bounded `agent_lib` policy/trace
characterization, and Flash-Next core, tool-decision, and valid recovery
baselines plus a conservative context-retention gate are complete. Do not
generalize the policy/trace result to OS isolation, or the bounded Docker result
to general container security; do not generalize the recovery ceiling to
arbitrary failures, or the 32K retention result to the advertised maximum.
Further model testing should require a new concrete question rather than
extending these ceiling profiles. Inspector/UI single-artifact replay is now
complete. The active maintenance sequence is Python-quality adoption, next
through `engram`. A deeper
command-sandbox project would first need
a new concrete question around the still-missing resource limits,
`no-new-privileges`, capabilities, or seccomp controls.

## Verification posture

The latest repository gate passed with 1,268 tests, 304 skips, and three existing
multiprocessing/fork deprecation warnings. Focused trust, temporal, security, and
availability tests also pass. Use the root invocation documented in `AGENTS.md`
with explicit source paths and plugin autoload disabled when reproducing this
environment.

## Working-tree posture

At handoff preparation, the Engram commits above were complete. The separate
`llm_engines` tool-recovery version-4 change set was validated and committed as
`d3dba83`. The final documentation checkpoint should leave the tracked worktree
clean; inspect `git status` before starting new work.
