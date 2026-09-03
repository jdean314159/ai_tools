# ai_tools — Session Handoff (historical log)

**Latest standing handoff:** `docs/internal/CLAUDE_THREAD_HANDOFF.md`
(`docs/internal/CODEX_THREAD_HANDOFF.md` is the concise Codex entry point.)
**This file:** historical session log; do not read it end-to-end for a fresh
thread.

**Read order for any new thread:** `AGENTS.md`, `docs/design/VISION.md`,
`docs/internal/STATUS.md`, then
`docs/internal/CLAUDE_THREAD_HANDOFF.md`. For a neural-memory thread also read ADR-016 and
`docs/projects/engram/NEURAL-07-RTRL-OUTPUT-EVALUATION.md`. For mail_lib: this file →
`docs/projects/mail_lib/mail_lib_status_v0.1.md` →
`docs/projects/mail_lib/mail_lib_system_parameters.md` →
`docs/projects/mail_lib/SPEC-MAIL-02-assistant-app.md` →
`docs/projects/mail_lib/SPEC-MAIL-01-personal-rules.md` →
`docs/projects/mail_lib/SPEC-MAIL-00-triage.md` →
`docs/projects/mail_lib/mail_lib_scoping_note.md`.
STATUS.md is the standing state. The Claude handoff records the latest completed
campaign and next-decision boundary. Entries below predate that handoff and are
retained only as historical context.

---

## TL;DR

## Update — 2026-08-13 (RUN-RECORD-00 Phase 2 complete)

Phase 0 inventory and ADR-021/022 are complete. Phase 2 added dependency-free
run-artifact envelope/read/validate primitives to `llm_harness_core` and
lossless NAV-v1/ASC adapters to `agent_lib`; legacy producers and NAV replay
consumers remain unchanged. Package-local checkpoints: 17 core tests and 153
agent tests passed. Phase 3 generation/agent cross-kind proof is next.

## Update — 2026-08-12 (RUN-RECORD-00 selected; planning only)

RUN-RECORD-00 is the next bounded project. It will inventory and reconcile the
existing NAV `run-record.json`, ASC `record.json`, engine response, inspector
trace, and campaign artifact shapes. This is not greenfield: NAV already has a
schema-v1 producer and a counterfactual consumer. No common schema
implementation is authorized before the inventory and ADR gates in
`docs/projects/RUN-RECORD-00-unified-run-artifacts.md`.

Fresh threads should read `docs/internal/CLAUDE_THREAD_HANDOFF.md` and the new
project document. Preserve the dirty tree and do not infer that a “RunRecord”
is itself a command-line program.

## Update — 2026-07-24 (NAV campaign closed)

NAV-VERIFIABLE-00 is complete at `f151893`. Its frozen verdict is
`inconclusive`: the task-goal ledger improved exploratory termination from 0/6
to 3/6 and relation correctness from 0/6 to 2/6 while reducing aggregate
tokens, but exact correctness remained 0/6 in both arms. Over-citation was the
repeated residual defect. Do not extend or reinterpret the frozen campaign.

Fresh threads should stop here and continue with
`docs/internal/CLAUDE_THREAD_HANDOFF.md`; the older updates below are superseded
as current-state guidance.

## Update — 2026-07-11 (MAIL assistant closed)

MAIL-02 adoption observation is complete. The local mail assistant should no
longer be treated as the active product direction. The post-mortem is
`docs/projects/mail_lib/POSTMORTEM-MAIL-ASSISTANT.md`.

Conclusion: the assistant failed adoption because it competed with
Thunderbird/Gmail on their mature reading, sync, and state-management surface.
The LLM features were not the bottleneck. State duplication, stale local cache
rows, account/folder drift, and incumbent-client ergonomics dominated. Keep
`mail_lib` and `examples/mail_assistant` as harvested code and a case study;
do not expand the assistant into a general mail client.

What was harvested: deterministic Thunderbird ingestion, personal rules,
snapshot/cache patterns, reviewed config mutation, section-summary boundaries,
and IMAP safety lessons. The next daily-tool candidate should avoid replacing a
mature incumbent's main surface and should target a workflow with no coherent
existing tool.

For a new Claude thread, read `docs/internal/STATUS.md` first, then the
post-mortem above. Older mail updates below are historical context, not current
next actions.

## Update — 2026-07-07 (MAIL-02 post-MVP hardening)

MAIL-02 remains the active application. Work after the original MVP added
age-filtered views, cached background refresh, sender/domain statistics,
bounded rendering and summaries, selectable message groups, and confirmed
single/batch IMAP Move-to-Trash. The Trash path now uses post-auth IMAP
capability refresh, Gmail `X-GM-RAW` Message-ID lookup with SPECIAL-USE All
Mail fallback, read-only proposal preflight, and one IMAP session per selected
account during proposal and commit. IMAP mutation is opt-in through a separate
account mapping and password environment variables; it fails closed on unsafe,
missing, ambiguous, or stale-server mappings and requires server-side `MOVE`.
Thunderbird mbox and Gloda access remains read-only.

The next action is continued private adoption observation and recording of
structural failures without committing real mail, private rules, credentials,
or model output. No result for the planned two-week adoption run is recorded in
the repository. F1 chat, F2 `\Seen` propagation, F3 `rag_lib`, F4 `engram`, and
F5 interest scoring remain dormant.

## Update — 2026-07-03 (MAIL-02 MVP complete; live validation pending)

**MAIL-02 is ratified and implemented.** The localhost FastAPI/Jinja/HTMX app,
app-owned read and summary state, deterministic action-aware classification,
bounded local-model section summaries, and reviewed atomic personal-rule commits
are complete. Automated gates use synthetic mail and a mock model; the focused
MAIL-02 suite passes (`16 passed`). Existing hand-authored TOML bytes are
preserved when a validated rule block is appended.

**Next action is private live validation, not more implementation:** run the first
refresh against the real Thunderbird profile and record only size/latency; assess
the first real section summary with qwen3:8b and the 12k input budget; and commit
the first rule against the hand-edited personal-rules file. Do not commit real
mail, rule values, or model output. Then use the app before Thunderbird for two
weeks. Failures observed during that period define the next specification.

F1 chat, F2 IMAP `\Seen` propagation, F3 `rag_lib`, F4 `engram`, and F5 interest
scoring remain dormant until their named triggers in SPEC-MAIL-02 fire. Nothing
else is queued for `mail_lib`.

## Update — 2026-07-01 (NEURAL-07 complete; RTRL output isolated)

Follow-up RTRL experiments are complete. Affinity is inactive because neural
recall contribution remains disabled. A seeded, calibrated surprise-threshold
finalist reduced neural updates but failed the full six-trial gate. Direct
inspection found the expected episode in 0/180 prompt hints; a direct-latent
variant still missed 76.1%. A held-out candidate-utility scorer with balanced
hard-negative replay produced no decoy or stale improvement across three seeds.

Decision: RTRL may collect telemetry when explicitly enabled, but it does not
affect recall by default. Retrieval reranking remains absent; prompt advisory
and surprise-based episode-importance adjustment require separate experimental
opt-ins. The durable evidence and reactivation gate are in the NEURAL-07 report.
Do not reconnect output without a real usefulness-feedback source available
outside the test set.

## Update — 2026-06-27 (MAIL-01 implemented + live-validated; digest traceability next)

**MAIL-01 is implemented and maintainer-live-validated under revision 4 of
`docs/projects/mail_lib/SPEC-MAIL-01-personal-rules.md`.** The live-validation follow-up sets the
bare-link prose threshold to **40 non-whitespace characters** and leaves subject-tag promotion
optional. Real mail, private rule values, and digest content were not recorded in the repository.

The implementation adds a strict TOML personal-rule loader (`sender` or `domain`, optional
`subject`, explicit priority), deterministic most-specific/file-order selection, XDG-aware rule
location, `--rules` and mail-free `--validate-rules` CLI modes, and fail-closed whole-file rejection.
Invalid configuration renders a built-in fallback digest but cannot mutate the index; an explicitly
missing rule path exits before profile/index access. Effective personal results are created in one
per-message loop and are shared by persistence and rendering.

The built-in self-mail floor is graduated: URL-shaped self-mail surfaces at `normal`; other
self-mail stays `low`. HTML anchor URLs survive body conversion with entity decoding. Development
and automated validation by Codex remained synthetic-only; no real mail, private rules, or live
digest output was provided to Codex or recorded.

Validation: MAIL-00/01 tests pass (`46 passed`); the combined mail, import-provenance, and public-API
gate passes (`56 passed`); Ruff passes; fixture validation and triage CLI runs pass; the
no-model/no-network grep is empty.

**Next queued item:** draft a thin digest-traceability follow-on before changing code. The live run
showed that the digest needs enough deterministic provenance to distinguish why a message remained
at `Default normal priority`—for example, whether self-mail detection did not fire (including the
known Bcc-to-self blind spot) or a body-shape threshold did not match. Define only the smallest
synthetic-fixture-backed output needed to expose applied built-in/personal rule tokens and relevant
classification signals. Do not include behavioral instrumentation, models, `engram`, `rag_lib`, UI,
or mail actions. The earlier 120-character tuning question is closed at **40**; reopen it only if a
future private run produces a structural forcing result.

## Update — 2026-06-27 (historical pre-MAIL-01 state; superseded above)

**MAIL-00 v0 is complete and validated on the maintainer's real Thunderbird profile.** Real mail
content remains private and is not recorded in this repository. The post-run status is
`docs/projects/mail_lib/mail_lib_status_v0.1.md`; the longer-term dependency order and settled
parameters are in `docs/projects/mail_lib/mail_lib_system_parameters.md`.

Three post-run corrections landed after `9f9125f`:

- `a80c45c` — self-addressed mail demotes to `low`;
- `2191e09` — only the Gloda star flag, not Gmail folder membership, can promote, and only within
  `URGENT_MAX_AGE_DAYS=183`;
- `c7f2d89` — calendar/appointment subjects promote only within
  `CALENDAR_MAX_AGE_DAYS=31`.

Current validation: `tests/test_mail_lib.py` passes (`10 passed`); the combined mail_lib,
import-provenance, and public-API gate passes (`20 passed`); the fixture CLI still runs; the
no-model/no-network grep remains empty.

**Forcing result at that point:** deterministic global heuristics could not encode personal interest.
They correctly de-flooded urgency but also buried wanted automated/publication/event mail. This led
to the MAIL-01 draft, subsequently revised, ratified, and implemented as recorded in the update
above. Model classification, summarization, behavioral instrumentation, `engram`, `rag_lib`,
drafting, and UI remained out of MAIL-01.

## Update — 2026-06-25 (MAIL-00 v0 implemented)

**MAIL-00 v0 is implemented script-first.** The ratified spec is
`docs/projects/mail_lib/SPEC-MAIL-00-triage.md`; it supersedes the earlier package/UI-first draft
and follows `docs/projects/mail_lib/mail_lib_scoping_note.md` for scope and privacy. v0 contains
only deterministic, fixture-backed code: synthetic Thunderbird/Gloda fixtures, an mbox-first
reader, a local SQLite indexer, rules-layer triage, a CLI digest, and fixture-only tests. No model,
network, package promotion, Streamlit UI, `engram`, or `rag_lib` path is present.

Key implementation rule: the reader matches mbox messages to Gloda metadata by bracket-stripped
`Message-ID`; it never seeks by `messageKey`. The reader iterates mbox as the spine and treats Gloda
as lagging enrichment, yielding mbox-only messages with reduced metadata when no Gloda row exists.
Synthetic fixtures cover contact/identity resolution, bool Gloda flags, extensionless mbox +
`.msf` discovery, `.sbd` recursion, Gmail signal-folder dedupe, and mbox-only messages.

Validation: `tests/test_mail_lib.py` passed (`7 passed`); the fixture CLI
`python scripts/mail_triage.py --profile tests/fixtures/mail_lib --no-index` prints a fake digest;
the no-model/no-network grep over `mail_lib/` and `scripts/mail_triage.py` returned no matches;
root-adjacent tests passed (`17 passed` with mail_lib/import/public API tests).

## Update — 2026-06-25 (SPEC-EXEC-00 command fail-closed)

**SPEC-EXEC-00 is implemented.** The ADR-020 agentic-execution follow-on audit found the
`EnforcingToolRuntime.invoke()` dispatcher boundary intact: `run_command` still requires an exact
`runnable_commands` allowlist match and passes the real `WorkspacePolicy` into command execution.
The one gap was the direct helper default: `execute_workspace_command(..., workspace_policy=None)`
self-allowlisted its input. That fail-open path was reachable through
`examples/programming_task.py`.

The helper now fails closed with `error == "no_workspace_policy"` when called without an explicit
policy, and the example passes its in-scope policy. Regression tests cover no-policy refusal,
explicit allowlisted execution, and unchanged dispatcher denial for unlisted commands.

Validation: production caller grep shows all `agent_lib/src` call sites pass `workspace_policy`;
focused programming/interop tests passed (`30 passed`); full `agent_lib` tests passed (`75 passed`);
`python -c "import agent_lib"` succeeded.

## Update — 2026-06-25 (ADR-020 data-only artifact loading)

**Repository state at handoff:** `ai_tools` is clean on `codex-cleanup-pass` at
`011d049` (`fix(rag_lib): replace pickle BM25 cache with JSON`).

**ADR-020 is accepted and enforced.** The real exposure was the `rag_lib` BM25
cache: `pickle.load` on a cache path would become arbitrary code execution if a
future multi-agent workflow made that path attacker-writable. Commit `011d049`
replaces the BM25 cache with data-only JSON (`corpus` + `ids`) and rebuilds
`BM25Okapi` on load, removes the dead `storage/chroma.py` pickle import, and
deletes both current `.json` and legacy `.pkl` cache files on collection deletion.

**Validation:** `rg "trust_remote_code|pickle\.(load|dump)|torch\.load" --glob
'*.py' .` returned no matches. `rag_lib` tests passed: `94 passed, 4 skipped`.

**Open follow-on:** ADR-020 intentionally leaves the agentic-execution boundary
audit open: confirm no `agent_lib` tool-dispatch path executes model-proposed code
outside the sandbox/tool boundary. This is a separate verification pass, not a
blocker for the BM25 cache fix.

## Update — 2026-06-24 (LIVE campaign completion lessons)

Three reusable process lessons came out of LIVE-00/LIVE-01 and ADR-019:

- **Obligation vs mechanism:** ADR-019 accepted a recovery contract because FX-CONTENTION forced an
  unreleased-holder failure, but implemented only the forced release slice. Owner-death detection
  remains a named backlog trigger rather than an xfail obligation. Reuse this pattern whenever a
  gap is real but only part of its possible solution space has been forced by a run.
- **Probe pass is not ledger validity:** two green-but-false interpretations were caught by checking
  the emitted surface signal against the actual state. Predicate D did not fire for Finding 1 because
  its done-check was satisfied; the old COORD-00 probe could pass while emitting a ledger that claimed
  post-COORD capabilities were absent. Validate a probe's classification/ledger separately from its
  pass status, especially after the system it describes evolves.
- **Drafts require code/result grounding:** the durable division of work was draft/review versus
  implementation/verification. Substantive corrections came from reading the actual control path,
  deterministic fixtures, and live transcript rather than accepting design assertions. Preserve that
  loop for future specs and ADRs.

## Update — 2026-06-24 (LIVE-01 and ADR-019 implemented)

**LIVE-01 is complete.** `computer_helper` commit `7c0aa60` makes the authoritative done-check
the sole termination authority; model `{"done": true}` is informational only. A fresh local
`qwen3:8b` run recorded in `fb033f8` retrieved at step 2, satisfied the predicate at step 4, and
terminated `done` at step 4 with no trailing routes. Evidence is committed under
`runs/live_01_termination_20260624/`.

**ADR-019 v1 is implemented.** `ai_tools` commit `f8fd116` exposes the owned, idempotent
`release_patch_lease` action and records `released_at`; `computer_helper` FX-RELEASE now proves
no-op holder → explicit release → contender progress. Owner-death detection, TTL, and automatic
reclaim remain backlog triggers, not work in progress.

## Update — 2026-06-22 (LIVE-00 planning complete; implementation pending)

`SPEC-LIVE-00` v8 is canonical at `14ac320` (`docs: revise LIVE-00 multi-agent probe spec`). It is a
revision-and-rebase specification: `computer_helper` branch `codex/live-00` is pre-v7 and non-conforming, so it
must be updated rather than merged unchanged. The required implementation work is targeted worker routing,
FX-CONTENTION, the full predicate-D deadlock classifier, semantic replay comparisons with fresh isolated state,
and explicitly pinned workspace policy. The eventual `computer_helper` implementation commit MUST reference
`14ac320`; this spec requires the reciprocal cross-reference before either change is considered complete.

**Cross-repository delivery rule:** a spec in `ai_tools` and its probe in `computer_helper` cannot share an atomic
Git commit. Land them as coordinated commits in their respective repositories, each cross-referencing the other
commit. Do not substitute timing or a shared branch name for a commit-level link.

**Specification invariant rule:** state each behavioral invariant exactly once, in its canonical section; tests,
fixtures, assertions, and observations reference that source rather than restating it. This single-source
discipline prevents the contradiction drift that affected early LIVE-00 revisions. Preserve it in SPEC-LIVE-01
and later campaigns.

The durable evidence/planning policy is committed in `ee5b14a` (`docs: add specification evidence policy`).

## Update — 2026-06-21 (COORD campaign closed; checkout workflow)

**Repository state at handoff:** `ai_tools` is clean on `codex-cleanup-pass` at
`58e07a0` (`WIP: accumulated multi-thread work pre-curation`), following:

- `4a5c671` — coordination control plane;
- `e71c9b0` — unified atomic path ownership; and
- `58e07a0` — deliberate multi-thread WIP consolidation.

`backup/pre-curation-20260621` anchors `e71c9b0`. Nothing in this campaign has
been pushed. `computer_helper` contains the matching probe commits, including
`c0a416e` (`test(probe): verify unified path ownership`), but its worktree still
has pre-existing staged/untracked probe-state changes; inspect it before making
any unrelated commit there.

**COORD campaign: CLOSED.** All four ledger gaps are closed. ADR-017 established
capability routing, per-session tool grants, and the coordinator deny-all guard.
ADR-018 then unified path ownership: manager-backed coordination uses one
cross-process-locked lease authority for both reservations and write enforcement;
the no-manager mailbox remains explicitly advisory-only for compatibility. The
library and probe commits are separate. Targeted `agent_lib` tests (73) and
`computer_helper` tests (6) passed, as did compile and diff checks.

**Open threads (none urgent):**

- Neural evaluation now has a tracked digest in
  `docs/projects/engram/NEURAL-07-RTRL-OUTPUT-EVALUATION.md`; raw run artifacts
  remain intentionally ignored.
- The thematic curation of `58e07a0` is intentionally deferred unless a future
  bisect or revert needs it.
- A deterministic control plane and unified ownership now make a live
  multi-agent run the natural next campaign. It remains out of scope until a
  new mandate.

**Workflow rule:** do not run multiple work streams in one checkout. Create a
branch (and, when concurrent, a separate worktree) per stream; it prevents
staged/index overlap and preserves independently reviewable commits.

**Specification process fix:** apply the `AGENTS.md` spec-and-planning policy
(lines 22–28) before review: cite every reuse claim from its actual call path,
separate unverified assumptions from confirmed facts, and name machinery that
must be built because it does not exist. This turned LIVE-00 from repeated
design corrections into clean review passes; carry it into every future spec.

Two threads closed this session, both landing on "don't build the big thing."

1. **Neural memory campaign is COMPLETE and the layer is PARKED.** The
   RTRL/TITANS layer (NEURAL-01 -> 07) was fully implemented, evaluated, and
   parked default-off as a research artifact. It did not earn core-feature
   status: re-ranking was rejected on catastrophic recall loss, and the
   TITANS-style prompt synthesis returned a clean null, and NEURAL-07 later
   demonstrated that its episode guidance was unrelated. All recall-affecting
   outputs are now default-off.
   ADR-016 is the decision record.
2. **Knowledge-curation MVP resolved AGAINST a wiki/adjudicator subsystem.** A
   three-phase probe showed an LLM adjudicator is untrustworthy and the value
   lives entirely in structured metadata. The shipped capability is a small
   deterministic decision-history schema + validator, NOT a memory subsystem.

Nothing is mid-flight in code. Remaining items are backlog.

## Update — 2026-06-15 (latest session)

No repo code changed this session. Two things happened:

1. **The two open verification items (see Next action) were checked — both
   pass.** The CI decision gate skips (not fails) ADRs without a
   decision-history block (`validate_decision_history.py`: `if payload is None:
   continue`), and `DECISION_HISTORY_SCHEMA.md` states the opt-in adoption rule
   explicitly. Both prior "Next action" items are now closed.
2. **Netflow campaign extracted:** `netflow_behavior_lab` now lives in the
   sibling repo `../netflow_behavior_lab`; it is no longer an `ai_tools`
   example. Deterministic flow-metadata
   host-behavior pipeline, local LLM as grounded interpreter only (never the
   trust surface). Dataset sequence **CTU-13 -> NF-UNSW-NB15 -> NPS** (two
   public benchmarks first for direct comparison with other researchers; NPS
   local-only, for the OS/behavioral claims its labels uniquely support).
   Not a novel-algorithm project; paper, if any, via survey / education /
   constraint-driven systems framing. Full detail:
   `../netflow_behavior_lab/notes/PLAN_netflow_behavior_lab.md` +
   `../netflow_behavior_lab/notes/HANDOFF_netflow_behavior_lab.md`.

## Thread 1 — Neural memory: landed, then parked

All specs implemented by Codex and validated green. Final disposition in
ADR-016. The arc:

- **NEURAL-01** — additive `MemoryLayer` protocol + 4 seams in `ProjectMemory`
  (observe / contribute_to_recall / contribute_to_prompt / persist+close),
  advisory-only, default-empty registry. Four existing layers untouched.
- **NEURAL-02a/02b** — vendored RTRL/TITANS core into `engram/neural/`; numpy
  default, torch optional via `[neural-accel]`. `NeuralMemoryLayer` as first
  MemoryLayer; `enable_neural=False` default.
- **NEURAL-04** — affinity made scale-invariant (spread-relative); affinity
  weight moved to config (0.15 default).
- **NEURAL-05** — **re-ranking disabled** after two clean runs showed
  catastrophic direct-recall loss at every weight. Surprise repurposed to
  write-side episode-importance (bounded, advisory, never suppresses); this
  influence was later made default-off by NEURAL-07.
- **NEURAL-06** — TITANS-style prompt-hint synthesis: value-projector
  pseudoinverse -> episode alignment -> template `[Neural context]` hint.
  `value_dim` 16->64 attempted but **reverted to 32 on RTRL overflow**
  (600-step stability test); `hidden_dim` stays 32 (P-matrix overflow).
  Config versioned (now v3); non-finite neural state fails closed (halts
  reads/writes/hints).
- **NEURAL-07** — seeded affinity/threshold/advisory/utility follow-up. Affinity
  confirmed inactive; threshold finalist failed full confirmation; 0/180 hints
  named the expected episode; feedback-free utility scoring failed across three
  seeds. Prompt and episode-importance outputs are now separately default-off.

**NEURAL-06 generation-mode eval (2026-06-11): clean null.** qwen3:8b
generator, qwen3.6:27b judge, 60-fact corpus, 6 trials, 1 warmup replay,
baseline vs neural_on. Hints emitted 180/180 per trial, warmup at 120 steps —
**mechanism confirmed working end-to-end** — but every metric delta within 1-2
judgments of baseline (recall_direct 0.878->0.872, paraphrase 0.861->0.858,
decoy 0.250->0.239, bleed unchanged). Decoy is structurally uninformative in
generation mode (unconstrained generator answers from parametric memory
regardless of hints).

**Decision: layer PARKED** (ADR-016 final section). Default-off behind the
NEURAL-01 seam, output-isolated, and not actively developed. A reframe was identified but NOT
pursued: the layer's distinctive output is its label-free surprise signal,
which suits novelty/anomaly use (agent-loop derailment, memory-poisoning
detection, surprise-based segmentation) rather than retrieval. **Reactivation
requires a concrete safety/observability need plus a predeclared falsifiable
gate. Do not re-run retrieval evals without a new mandate.**

## Thread 2 — Knowledge-curation MVP: resolved against a subsystem

Question explored: could conversation history (conversations.json, ~10.7k
messages) be curated into an evidence-linked memory that preserves *how
conclusions changed*? Three probes settled it empirically:

- **First extraction** (323 candidate claims): mechanically fine (parsing,
  provenance to message UUIDs) but a competent index, not a memory — uniformly
  agreeable claims, no contradiction detection, `source_material` label
  masquerading as an authority signal.
- **Phase 5B** (adjudication probe, pre-declared gate): LLM adjudicator FAILED
  — collapsed nuance toward single labels, both over-killing live claims
  (`historical`) and over-crediting unsupported ones (`qualified`).
- **Phase 5C** (strategy comparison): zero-shot 6 errors, few-shot 4 errors
  (but MORE unsupported links), few-shot+policy 0 errors / 6 unsupported links,
  **deterministic-only 0 errors / 0 unsupported links**. The deterministic path
  dominated on every axis.

**Decision: no LLM adjudicator.** Value lives in structured metadata, not
interpretation. Shipped capability:

- `docs/design/DECISION_HISTORY_SCHEMA.md` — YAML front-matter schema for ADRs.
- `scripts/validate_decision_history.py` — strict validator.
- ADR-016 carries the proof case: four scoped `(id, application_scope)` records.
- `make check-decisions` + CI doc gate. Knowledge-MVP suite: 43 passed.

**Schema invariants (do not relax):** closed enums + paths drive logic; free
text (`basis`, `current_guidance`) is display-only; keys are
`(hypothesis, application_scope)` not bare hypotheses; `mechanism_status`
(operational/not_demonstrated/not_applicable) records *did it function*,
orthogonal to `resolution_status` (*did it help*); `mechanism_evidence`
required iff `operational`; heading fragments must resolve to exact
GitHub-style slugs; contradiction detection is exact-key collision only;
validator confirms references resolve, NOT that claims are true.

**Adoption is incremental and opt-in:** a decision-history block is added when
an ADR records a superseded hypothesis or split-application resolution — NOT
required on every ADR. The CI gate must skip ADRs without the block, not fail
them. (VERIFY this is how the gate is scoped.)

## Decisions closed (do NOT re-litigate)

- **Neural re-ranking: rejected** (catastrophic recall loss, two clean 27b
  runs). `contribute_to_recall` returns None.
- **Neural layer: parked, default-off.** Not core. Reactivation needs a new
  concrete need + predeclared gate. The promising-looking reframe
  (novelty/anomaly via surprise signal) is untested and explicitly NOT a
  mandate to build.
- **Neural output: isolated from recall.** Reranking is absent; prompt advisory
  and surprise-based importance adjustment are explicit experimental opt-ins.
- **value_dim stays 32, hidden_dim stays 32.** 64 caused RTRL/P-matrix
  overflow; reverted. Documented in ADR-016 as a superseded parameter change.
- **No LLM knowledge adjudicator.** Phase 5C proved deterministic metadata
  strictly dominates. LLM may assist *ingestion* but its evidence links are
  untrusted candidates only.
- **The decision-history schema is the knowledge capability** — a metadata
  convention with no trust surface, not a subsystem. The arc-preservation value
  (why a hypothesis was tried + how it resolved) is captured at decision time,
  deterministically.

## NetFlow campaign — done and recorded:

Phases 0–5 complete. Mechanism: rare external-destination breadth of malicious activity drives the rank — not C2 concentration (rejected via cc_only, 7 scenarios), not a same-host artifact (refuted by subtractive collapse + three independent hosts co-ranking in Sc.12). Validated across Neris/Rbot/Virut/DonBot + NSIS.ay (P2P). Blind spot characterized empirically: narrow-fan-out C2 (the cc_only profile, ranks 60–349).
SPEC-NETFLOW-00 through 05 now live in `../netflow_behavior_lab/specs/`, results recorded in each.

## Open / queued:

SPEC-NETFLOW-06 (NPS real-network) — extracted to `../netflow_behavior_lab/specs/`; operating under the §2a conservative fallback (NPS internal ranges + VPN-partner subnets not authoritatively known). Hard gates before ranking: internal-range list, adjudication authorization, NAT confirmation. Outside-firewall capture identified NPS public space (205.155.65.x, 204.102.229.x); blocked_fraction from the firewall-policy dataset folded in as an adjudication evidence line, not a ranking input.
`../REPO_STATE_VERIFICATION.md` — checklist queued, not executed. First task flagged: the turboquant.py path discrepancy (asserted built, failed ls in the snapshot — resolve real-absence vs stale-copy first).

Two unverified facts the next thread must not inherit as settled:

The repo snapshot I was reading may lag your working tree — the turboquant discrepancy could be that.
Everything in the repo-state assessment is lead-not-fact until the verification checklist runs.

## Deferred backlog (none blocking)

- **Course-repo extraction** — teaching material (course/, docs/learning/)
  moves to a separate repo; severs library<->course cross-references. Library
  READMEs must never link to course material (dependency direction is
  course->library). Gated behind public-API stability.
- **TOPOLOGY-01 conversion** — single-distribution decision (Option A) made;
  ADR-015 + conversion deferred until after course-repo extraction.
- **Neural backlog (only if reactivated under a new mandate):** torch-accel
  parity test; SurpriseFilter (needs logprob engine); novelty/anomaly reframe
  probe; corpus expansion (`fact_generator.py` is a stub) if a future retrieval
  mandate appears.
- **SPEC-CLASSIFY-01/02** — engram conftest import trap; diagnostics test
  isolation. Parked.

## Standing context

- Workflow: Claude writes specs/reviews; Codex implements + runs evals on the
  RTX 3090 workstation. ADRs + this handoff are the cross-thread memory.
- ADR-016 is the neural layer's decision record AND the decision-history schema
  proof case. Both threads converge there.
- Recovery bundles (if needed): neural subsystem + eval harness were recovered
  from git history at `345f3bd~1`. Live repo contains the adapted versions.

## Update — 2026-06-22 (cont.) — SPEC-LIVE-01 fork scoped; OPCOM sibling-system lessons captured

Continues the same-day LIVE-00 update below. No `ai_tools` code changed this session; one doc added
(`docs/internal/LESSONS_FROM_OPCOM.md`, committed as `832591a`).

**Finding 1 status (termination contract):** **CONFIRMED** by the fresh v8 `qwen3:8b` run in `computer_helper`
commit `7e40b36`: retrieval succeeded at step 2; `config.toml` was updated at step 4 with `done_check` satisfied;
the coordinator then issued four more `replace_text` routes; the run reached `step_cap` at step 12 rather than
`done`. The in-tree transcript, results, and ledger are in `runs/live_00_v8_20260624/`. Cause is code-confirmed:
`termination="done"` is set only when the coordinator volunteers `{"done":true}` and `_done()` validates it; a
satisfied predicate alone never terminates.

**SPEC-LIVE-01 fork — scoped, NOT written, decision not formally ratified.** Grounded fact:
`agent_lib/src/agent_lib/coordination.py` has NO execution loop (no `run`/`step`/`terminate`/`done`);
`ManagedCoordination` is a dataclass container (`coordinator` + `worker_runtimes`). The probe builds the entire
loop and owns the termination decision. Consequence: "predicate-driven termination as an `agent_lib` change" is
incoherent in isolation — there is no in-library caller, so it would be a consumerless primitive
(anti-probe-first). The fork:
- **Option 1 (recommended):** fix Finding 1 PROBE-SIDE — the probe loop consults `_done()` each step and
  terminates when satisfied; model `{"done":true}` demoted to an early-exit hint. `agent_lib` untouched; "no
  library loop / no termination contract" recorded as a standing gap.
- **Option 2:** move orchestration into `agent_lib` (a minimal team loop, termination as its first feature).
  Closes Finding 1 + Observation 2 together, but is an architectural commitment for which only the termination
  slice has been forced by a concrete run.

Design conclusion (informed by the OPCOM read, NOT yet ratified — the user stepped back to review the sibling
system before deciding): later multi-agent projects (novel tool, language tutor, computer_helper) will each need
*a* loop but NOT the *same* loop — topologies differ (capability-routed alternation vs critique pipeline vs
plan-then-execute). What generalizes is the **termination contract** (authoritative predicate drives the stop;
model signal is a hint), not the loop. Extract a shared termination primitive into `agent_lib` only on the
**second** consumer, not the first. Until then: Option 1. The new thread should ratify or revise this with the
OPCOM evidence in hand.

**OPCOM / dev-team-six sibling-system read → `docs/internal/LESSONS_FROM_OPCOM.md`.** Read (not run) a related
multi-agent system by another author: dev-team-six (Claude Code worker framework, evolution of
`super-claude-kit`) + OPCOM (out-of-process Postgres/MCP/WebSocket coordination backbone, successor to
`mcp_agent_mail`) + Beads (external task authority) + capsules (TOON-format externalized memory). Its architecture
is the opposite of `agent_lib`: thin workers, with coordination, task authority, and memory all pushed OUT of the
agent into services. Five lessons recorded; transfer is selective (out-of-process service vs in-process library).
The actionable one:
- **Lesson 1 (lease lifecycle — DIRECTLY PORTABLE):** both `mcp_agent_mail` (`models.py:88`, `storage.py`) and
  OPCOM (`reservation-service.ts`) carry `exclusive` / `expires_ts` (TTL) / `released_ts` + reclaim
  (owner-process-death + age in the local Python version; TTL-expiry-at-query-time in the out-of-process TS
  version). It SURVIVED a full Python→TS reimplementation = load-bearing. It is exactly the "no TTL / owner-death
  reclaim / release-on-failure" gap LIVE-00 predicted (#2) and that `WorkspaceIsolationManager` lacks (its record
  is `{owner_id, status, created_at, …}`, with `created_at` unconsumed). When forced in-tree: add `expires_ts` +
  explicit release + exclusive/shared, treat expired as free; because `agent_lib` is IN-PROCESS, owner-liveness
  reclaim is available (not TTL-only).
Lessons 2–4 are loop-fork orientation (externalization by example; external/singular task authority as the clean
form of Finding 1; wake-on-event vs a scheduler loop). Lesson 5: capsules ≈ `engram` (confirmation, not a borrow).

**Next action (new thread / Codex):** unchanged execution path — rebase `codex/live-00` to v8 (targeted routing,
FX-CONTENTION, full predicate-D classifier, semantic replay comparison with fresh isolated state, pinned
workspace policy), re-run the live probe to bring Finding 1 in-tree, and land the probe commit cross-referencing
`14ac320`. Probe-first sequencing for the borrow: that same v8 rebase is what forces the lease-reclaim deadlock
in-tree (FX-CONTENTION) — once it does, open the lease-lifecycle ADR with `LESSONS_FROM_OPCOM.md` Lesson 1 as
design input. Do NOT pre-build the lease lifecycle on the sibling-system precedent alone.

**Security:** the uploaded `mcp_agent_mail` archive contained a private signing key (`signing-77c6e768.key`) and a
`.env`. Treat both as exposed — rotate them and scrub from any future uploads.

**Preserve (carry into SPEC-LIVE-01 and later):** single-source invariant discipline (each invariant stated once,
referenced elsewhere — held v6→v8); the cross-repo reciprocal-commit-reference rule; the `AGENTS.md`
spec-and-planning grounding policy.
