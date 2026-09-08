# Fresh Codex thread handoff

- Prepared: 2026-09-08
- Repository: the checkout containing this file (`git rev-parse --show-toplevel`)
- Current focus: specify and record repository-assessment model comparisons

## Read order

1. `AGENTS.md`
2. `docs/design/VISION.md`
3. `docs/internal/STATUS.md`
4. `docs/internal/ROADMAP.md`
5. `docs/internal/REPOSITORY_ASSESSMENT_HANDOFF_2026-09-02.md`
6. `llm_harness_core/README.md`
7. `docs/projects/RUN-RECORD-00-unified-run-artifacts.md`

Do not read `history/SESSION_HANDOFF.md` end to end; it is a historical log.

## Current selected task

The adaptive-v2.2 Phase 1 campaign is complete. Do not tune the treatment
again on known target `83e1d09`. The next experiment gate is an independently
prepared blinded target set and separate Phase 2 preregistration; no suitable
target is currently retained in this repository. If no blinded oracle can be
obtained, stop this research line rather than substituting more runs on the
development target.

The result may later become a bounded `llm-failure-lab` evidence packet, but do
not mutate the sibling lab until the `ai_tools` artifacts have stable committed
Git identities, disclosure review and independent packet verification are
complete, and the lab maintainer authorizes teaching placement.

A draft next-round recommendation is ready for Claude review at
`docs/projects/repository_assessment/ORNITH-POST-V2-2-NEXT-ROUND-RECOMMENDATION-2026-09-08.md`.
It recommends stopping v2.2 on the known target and, only after acquiring new
targets, separately ablating controller-owned evidence transport,
controller-assigned risk diversity, a defect-shaped promotion schema, and a
three/six scout-verifier budget. It is not an accepted plan or
preregistration.

Continue to implement no production schema until Claude supplies the initial
`repository-assessment/v1` profile. Once supplied, validate every reuse claim
against `llm_harness_core.run_artifacts`, identify fields or adapters that do
not exist, and implement the smallest recorder/backfill slice. Preserve the
resolved rule that a run which did not submit naturally remains
`lifecycle="aborted"`; `completion_mode` in the producer body records whether
the retained report was natural or forced. Do not create a separate forced-run
artifact.

Checkpoint writing, a general evaluation metrics framework, and a distinct
comparison profile are explicitly deferred. The detailed evidence, current
working-tree warning, test record, and pasteable opening prompt are in
`docs/internal/REPOSITORY_ASSESSMENT_HANDOFF_2026-09-02.md`.

## Assessment checkpoints through 2026-09-08

The adaptive staged-v2.2 follow-on completed on 2026-09-08. The valid paired
campaign passed all frozen mechanical gates and independently reproduced every
coverage score, endpoint fingerprint, report, dossier, budget, and grader
result. Against fresh staged-v1 controls, v2.2 median coverage fell from 7/9 to
3/9, concentration rose from 20.0% to 28.9%, calls rose from 30 to 38, and
input grew from 115,521 to 376,075 tokens. Recall remained 0/3 in all six runs;
neither condition accepted a final finding.

V2.2 selected the same symbol per package in all three seeds, so deterministic
orientation became deterministic tunneling. Independent exact-quote replay
invalidated 29/35 evidence records. Controller downgrades and critics prevented
unsupported acceptance, demonstrating evidence control without defect
judgment. All 27 scouts required forced structure; five of eight verifiers
completed naturally. Two prior campaign attempts are retained and excluded:
v2 referenced IDs hidden by Jinja, and v2.1 made a repeated controller-owned
binding abortive. Read
`docs/projects/repository_assessment/ORNITH-ADAPTIVE-STAGED-V2-2-ASSESSMENT-2026-09-08.md`
and its valid campaign directory before any follow-on.

The live Qwen3-Coder 30B-A3B model passed the unchanged basic characterization
campaign 20/20 and the single-turn tool-decision campaign 12/12, then passed
6/12 multi-turn recovery cases. Its frozen repository-assessment pilot scored
0/3 against an independent known-defect grader, spent 42/45 shell calls in
`llm_inspector`, exhausted the turn cap, and required a forced report. The
grader fails 3/3 on target commit `83e1d09` and passes 3/3 on current HEAD.

Exact artifacts, hashes, the grader, and the corrected bounded interpretation
are under `docs/projects/repository_assessment/`. The completed seed-7 run is a
pilot, not a confirmatory repetition.

The subsequent frozen six-run comparison is complete. Baseline and planner
conditions both had median recall 0/3; independently corrected substantive
coverage was baseline 1/9 versus planner 0/9, and natural completion was
baseline 3/3 versus planner 1/3. The planner prevented
low-uncertainty reports under the coverage threshold but otherwise contradicted
the coverage and termination predictions. All exact transcripts, reports,
temporary metadata, independent adjudication, invalid development attempts,
and the maintained harness are retained. The adjudication discloses that the
harness undercounted two baselines by excluding relevant root-level tests and
callers permitted by the preregistration. See
`docs/projects/repository_assessment/QWEN3-CODER-30B-A3B-PLANNER-COMPARISON-2026-09-07.md`.

The separately preregistered Q4_0/Q8_0 cache comparison is complete. Both
conditions scored 0/3 recall in all three paired seeds and corrected median
coverage 1/9. All six runs terminated naturally. Q8_0 changed every transcript
and concentrated all seeds on Engram, but produced three false positives versus
two under Q4_0 and did not improve median whole-run time. Read
`docs/projects/repository_assessment/QWEN3-CODER-30B-A3B-KV-CACHE-COMPARISON-2026-09-07.md`.
Cache precision is user-reported, and the blocked restart design limits causal
attribution. No follow-on is selected; a 90-turn condition, F16 cache,
counterbalanced restart design, and redesigned planner remain separate work.

The subsequent Ornith 1.5 35B campaign is also complete. The model passed
basic capabilities 20/20, tool decisions 12/12, and tool recovery 12/12, then
scored 0/3 frozen repository-defect recall in each of three preregistered seeds.
All three bound the 45-turn cap and required forced reports; corrected coverage
was 1/9, 2/9, and 1/9. Seeds 17 and 47 did correctly reproduce two Engram trust
defects after reading an internal handoff that named them explicitly. An
independent reproducer confirms both are still present on HEAD: `get_facts()`
bypasses recall-policy filtering, and extracted facts omit trust provenance.
Treat those as verified supplied leads, not new discovery. See
`docs/projects/repository_assessment/ORNITH-1.5-35B-KNOWN-DEFECT-BASELINE-2026-09-07.md`.
Ornith used active draft MTP, so its sequential comparison with the
non-speculative Qwen baseline is not a model-weights-only causal estimate.

A subsequent preregistered staged treatment reused the same Ornith endpoint,
target, grader, and seeds while replacing one growing autonomous context with
nine fresh package scouts, fresh candidate verifiers, an evidence critic, and
constrained synthesis. Historical handoff and experiment documents were
masked. Coverage improved from baseline scores 1/9, 2/9, 1/9 to 7/9, 6/9,
8/9; median concentration fell from 62.2% to 11.1%; median input fell 94.6% to
89,359 tokens. Recall remained 0/3 in every seed. Two seed-47 candidates were
both independently adjudicated non-defects and filtered before the report.
Every scout and verifier still needed a forced structured-summary request, and
one synthesis used a controller fallback. See
`docs/projects/repository_assessment/ORNITH-1.5-35B-STAGED-ASSESSMENT-2026-09-07.md`.
Do not describe this as prompt wording alone improving performance: the tested
treatment bundles prompt, fresh-context decomposition, fixed budgets, gates,
and controller-owned uncertainty.

## Current cleanup checkpoint

Commits `7d37920` through `0d0b0c3` complete the structural cleanup, root-doc
consolidation, private-endpoint correction, and distribution-wide privacy gate.
The offline gate is 1,254 passed and 305 skipped. Claude independently closed
the endpoint/root cleanup and re-verified the three post-reformat behavioral
closures. No broad cleanup campaign is active; require a concrete burden or
failing consumer before further structural work.

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
24. `engram` is now lint-clean, formatted, and included in the shared gate. Its
    standalone runner now uses an explicit import registry instead of dynamic
    `locals()` harvesting. The fallback runner passed 71 of 72 checks with one
    Ollama skip, and the full gate remains at 1,268 passed. All active libraries
    are adopted; examples, scripts, and root tests remain for classification.
25. `examples/diagnostics_agent` is the first adopted maintained example. It
    was already lint-clean; Ruff formatted 15 files, its dedicated suite passed
    167 tests with 8 skips, and the full gate remains at 1,268 passed. Remaining
    examples require per-project classification.
26. `examples/language_tutor` is now adopted. Its direct-checkout bootstrap
    requires delayed sibling-package imports, now documented with narrow `E402`
    annotations. Its 3 dedicated tests passed, the shared gate covers 417 files,
    and the full gate remains at 1,268 passed.
27. `examples/mail_assistant` is now adopted. Its one lint finding was resolved
    with explicit exception chaining, Ruff formatted 12 files, and the focused
    mail/public-API set passed 102 tests. The shared gate covers 432 files and
    the full gate remains at 1,268 passed.
28. `examples/agent_coordination_teaching` is now classified as maintained
    public-API teaching code and adopted. Ruff formatted 5 files, its 3 offline
    tests passed, the shared gate covers 439 files, and the full gate remains at
    1,268 passed.
29. `examples/language_tutor_reference_app` is now adopted after separating its
    maintained generator implementation from the external target tree it emits.
    Ruff formatted 33 files; its dedicated suite passed 118 tests with 33 skips,
    both entry scripts compiled, and the shared/full gates remain green.
30. The maintained `examples/asc_probe` harness is now adopted while generated
    `runs/` evidence remains excluded. Both harness scripts compiled, the 3
    fixture tests passed, the shared gate covers 481 files, and the full gate
    remains at 1,268 passed.
31. Top-level example probes are now adopted as maintained characterization
    tooling; recorded evidence was untouched and live experiments were not
    rerun. Ruff expanded compact statements across 16 files, all modules
    compiled, the shared gate covers 498 files, and the full gate remains green.
32. Repository `scripts/` are now adopted. The cleanup restored Python 3.10
    parse compatibility in the knowledge-review script, all 60 script tests
    passed, Ruff's `py310` parser accepts the scope, the shared gate covers 525
    files, and the full gate remains green.
33. Root unit and integration tests are now adopted. Ruff formatted 38 files,
    the shared gate covers 571 files, and the full repository result remains
    1,268 passed, 304 skipped, with the same three warnings.
34. Repository-wide Python-quality adoption is complete. Root `conftest.py` was
    the final formatting holdout, and the Make scope is now consolidated to `.`.
    Ruff covers 572 tracked files; generated evidence and configured build
    outputs remain excluded.

Key commits, oldest to newest:

- `c0cf400` — temporal memory reliability tooling
- `987d743` — clean packaging validation
- `38a6099` — persistent-memory trust-boundary characterization
- `22d7c14` — trust-policy enforcement
- `2307988` — paired DGX trust-policy validation and citation correction
- `4122f45` — availability/false-positive characterization
- `60c1df2` — audited trust-review workflow
- `d4c4aec` — repository-wide Ruff adoption complete
- `7d37920` — structural simplification checkpoint
- `cda69ca` — packaged private-endpoint correction
- `b3d2abe` — root governance and document consolidation
- `0d0b0c3` — distribution-wide privacy hygiene

## Current evidence boundary

- Current live model: llama.cpp-hosted `Ornith-1.5-35B-Q4_K_M.gguf` on the DGX
  Spark. The endpoint reports llama.cpp build `b10679-50f068fff`; the remote
  model digest and server-executable digest remain unavailable. Slot records
  reported active draft MTP with a three-token user-reported draft limit.
- Security and availability probes used thinking off, temperature zero, and
  exact judge-free scoring. No oracle or LLM judge was used.
- Results are bounded synthetic characterizations, not general security or
  field false-positive-rate claims.
- The review workflow has deterministic persistence tests but no separate live
  model experiment because it changes metadata enforcement, not inference.
- JSONL review history is inspectable but not tamper-evident. Compliance use
  requires a protected external telemetry/audit sink.
- Working-session turns remain outside the persistent-memory trust policy.

## Completed structural cleanup sequence

Repository-wide style normalization and generated-artifact cleanup are
complete. The read-only language-tutor overlap assessment is recorded in
`docs/internal/LANGUAGE_TUTOR_OVERLAP_ASSESSMENT.md`. The selected consolidation
is complete: the small duplicate and stale embedded generator are retired, and
`examples/language_tutor_reference_app` is the sole tutor implementation. The
unreliable, unintegrated `reasoning_loop_guard` experiment was retired. Contract
ownership is now documented in `docs/internal/CONTRACT_BOUNDARY_ASSESSMENT.md`;
Inspector's duplicate trace-event subclass was removed, while agent and engine
tool contracts remain distinct. The next structural candidate is priority 6:
split an oversized module only along proven responsibilities. Its first bounded
step is complete: navigation ground-truth loading and snapshot validation now
live in `agent_lib.eval.navigation_ground_truth`, with compatibility re-exports
from `repo_navigation`. The second bounded split is also complete: tokenizer
and native llama-server transport classes live in
`agent_lib.eval.navigation_model_transport`, and the shared configuration
exception lives in `agent_lib.eval.navigation_contracts`. Compatibility exports
remain unchanged. Assess the next cluster independently before moving it.
The third split is complete: workspace confinement/tools/telemetry live in
`navigation_workspace`, while no-write history compaction lives independently
in `navigation_context`. `repo_navigation` remains the compatibility facade.
The fourth split is also complete: prompt/schema construction, budget state,
planner behavior, constrained finalization, and the planner lifecycle hook live
in `navigation_planner`, with identity-preserving facade exports.
The fifth split is complete as well: scoring lives in `navigation_scoring`, and
environment manifests, tree digests, and run-record serialization live in
`navigation_artifacts`. `repo_navigation` now retains harness assembly and the
compatibility facade.
The Pythonic-simplification assessment is in
`docs/internal/PYTHONIC_SIMPLIFICATION_ASSESSMENT.md`. Engram's redundant custom
test runner is gone, and navigation planner history/usage duplication is
consolidated. The next grounded candidate is workspace/lease ownership inside
`agent_lib.programming`; do not split its persisted contracts casually. That
extraction is now complete in `agent_lib.programming_workspace`, with
compatibility exports and focused identity tests. The next possible programming
seam is durable task state and lifecycle tracking.
That follow-up is complete: value objects are in `programming_contracts`, and
durable state plus lifecycle tracking are in `programming_state`. The old module
re-exports identical objects, and focused tests cover the facade identities.
The first `ProjectMemory` state map did not justify a large split because its
persistence and retrieval clusters share mutable episode state. A narrow cleanup
moved canonical `TokenBudget` ownership to `engram.types`, retained
`PromptBudget` as an identity alias, and corrected obsolete live `engram-lite`
command and extra guidance.
The direct Engram pytest shadowing issue is also fixed: root `conftest.py` now
anchors `engram` to its src-layout package. A direct `engram/tests` run with
`--run-engram` passes 241 tests with seven skips.
The first UI split is complete: submission readiness policy lives in
`services.submission`, and readiness/submission rendering lives in
`panels.submission_panel`. `app.py` imports those functions unchanged and keeps
application composition.

No further structural split is queued. Select future work from a concrete
failure or maintenance burden rather than continuing cleanup by momentum.

Do not combine this maintenance work with command-isolation experiments or
model characterization.

Do not extend the Engram policy or model-ceiling profiles from their bounded
matrices. Any return to capability validation should select one unvalidated
package capability at a time.

Do not restart action-guard enforcement as a simple repeated-tool experiment.
Deterministic enforcement is already covered, live enforcement failed its
quality gates, NAV-STRUCT-00 failed completeness, and the frozen paired
NAV-VERIFIABLE-00 campaign was inconclusive. Its predeclared rule does not
support broader shadow testing.

The clearest next bounded candidate is command-isolation hardening, but it is a
new scope and must be selected explicitly. A first profile should test one
concrete boundary—preferably `no-new-privileges` plus dropped Linux
capabilities—before separately considering resource limits or seccomp.

The Engram prompt-budget choice, first bounded `agent_lib` policy/trace
characterization, and Flash-Next core, tool-decision, and valid recovery
baselines plus a conservative context-retention gate are complete. Do not
generalize the policy/trace result to OS isolation, or the bounded Docker result
to general container security; do not generalize the recovery ceiling to
arbitrary failures, or the 32K retention result to the advertised maximum.
Further model testing should require a new concrete question rather than
extending these ceiling profiles. Inspector/UI single-artifact replay and
repository-wide Python-quality adoption are complete. A deeper command-sandbox
project still needs an explicitly selected question around resource limits,
`no-new-privileges`, capabilities, or seccomp controls.

## Verification posture

After ignored build copies were removed, the canonical-source repository gate
passed with 1,250 tests, 305 skips, and three existing multiprocessing/fork
deprecation warnings. The explicitly excluded integration tree passed 48 tests
with one skip. The former 1,268 count included 14 tests collected from ignored
build copies and must not be used as the canonical baseline. The one-test
reduction from the interim 1,254 baseline was the net result of
retiring the small tutor's three tests and adding public-export and voice-config
tests to the canonical app. Retiring `reasoning_loop_guard` then removed ten
package/public-surface tests from collection, and the navigation ground-truth
split and later cleanup coverage added seven tests. Focused trust, temporal,
security, and availability tests also pass.

## Working-tree posture

At handoff preparation, the Engram commits above were complete. The separate
`llm_engines` tool-recovery version-4 change set was validated and committed as
`31cfdb0`. The final documentation checkpoint should leave the tracked worktree
clean; inspect `git status` before starting new work.
