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

Do not extend the policy immediately. First choose one bounded validation:

1. Run the deferred thinking-on version of the frozen paired security profile,
   preserving all cases and scorers; or
2. Measure trust-label prompt-budget pressure with many accepted memories and a
   predeclared exact-answer/citation gate; or
3. Return to the broader `ai_tools` capability inventory and select the next
   unvalidated package capability one at a time.

The leading Engram-specific choice is prompt-budget pressure because the
availability run measured a 37-token overhead per one-item prompt but did not
test displacement under crowded context.

## Verification posture

The latest repository gate passed with 1,234 tests, 305 skips, and three existing
multiprocessing/fork deprecation warnings. Focused trust, temporal, security, and
availability tests also pass. Use the root invocation documented in `AGENTS.md`
with explicit source paths and plugin autoload disabled when reproducing this
environment.

## Working-tree posture

At handoff preparation, the Engram commits above were complete. The separate
`llm_engines` tool-recovery version-4 change set was validated and committed as
`d3dba83`. The final documentation checkpoint should leave the tracked worktree
clean; inspect `git status` before starting new work.
