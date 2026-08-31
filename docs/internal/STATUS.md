# Repo Status

Last updated: 2026-08-30

Single source of truth for the current `ai_tools` repo state. Use this file
first when starting a new thread or resuming work after a handoff.

## Current posture

**Phase: the failure-driven course and `docs/learning` material have been
extracted to the sibling `llm-failure-lab` repository. Its maintainer gate
builds ordinary wheels from this checkout, so the split does not imply PyPI
publication. NAV-VERIFIABLE-00 remains complete
with a frozen `inconclusive` verdict; NAV-TEST-00 remains an autonomous
navigation failure. Mail-assistant adoption is closed, and neural memory
remains parked and output-isolated. Engram temporal reliability, persistent
memory trust enforcement, live security/availability characterization, and the
audited review workflow are complete; the next Engram experiment is not yet
selected.**

For a fresh Claude thread, read
`docs/internal/CLAUDE_THREAD_HANDOFF.md` after this file. For a fresh Codex
thread, read `docs/internal/CODEX_THREAD_HANDOFF.md`.

### Latest completed work — remote local-model characterization

`llm_engines` now supports a remote OpenAI-compatible llama.cpp server as a
fully exercised local inference path. Request-level thinking, strict structured
output, token log probabilities, validated streamed tool calls, and JSON-safe
tool-history replay are covered by ADR-024 and ADR-025. Local-compatible
endpoints no longer claim embeddings or vision unless the corresponding typed
contract is actually available.

ADR-026 adds privacy-bounded synthetic characterization. A single run checks
chat, structured output, tool-call construction, and log probabilities; a
campaign repeats those checks and records descriptive stability and latency
summaries. ADR-027 adds a separate version-2 tool-decision campaign for required
tool use, relevant-tool choice, avoiding unnecessary tools, and typed argument
construction. It never executes tools or retains raw prompts, responses,
argument values, endpoint URLs, secrets, or exception messages. Inspector
recognizes and compares both profiles while refusing model-identity or
hidden-reasoning claims.

Live Qwen 3.8 27B testing against llama.cpp on the DGX Spark passed all four
characterization probes in five repetitions. Matched sequential tool-decision
campaigns exercised four cases three times per condition; every case passed in
both thinking-disabled and thinking-enabled runs. The baseline was already at
ceiling, so improvement was not measurable. Thinking increased median latency
in every case and did not cause a regression in this small campaign. These are
observations about the exact endpoint and cases tested, not general
model-quality estimates.
The committed artifacts, digests, and execution limitations are recorded in
`docs/projects/llm_engines/SPARK-QWEN-CHARACTERIZATION-2026-08-29.md`.

The next process experiment is multi-turn recovery from a tool error or a
contradictory tool result. It must remain a separate governed profile rather
than expanding the current single-decision contract implicitly.

ADR-028 now defines seed request and acceptance as separate facts; accepted
seed parameters do not upgrade `best_effort` determinism. ADR-029 freezes the
recovery pilot boundary, four failure families, privacy contract, and baseline-
headroom stop rule. The executable pilot profile is available, but no live
recovery comparison or improvement threshold has been authorized. The baseline
pilot is frozen in
`docs/projects/llm_engines/TOOL-RECOVERY-PILOT-2026-08-29.md`.
That version-1 pilot exposed an invalid exact-text scorer and was withdrawn.
The corrected version-2 baseline is frozen in
`docs/projects/llm_engines/TOOL-RECOVERY-PILOT-V2-2026-08-29.md`.
It passed 12/12 recoveries with no fabricated-success flags, so the predeclared
ceiling rule stopped the experiment before a thinking-on condition. Designing
a harder version-3 suite is a new project; version 2 must not be tuned in place.
The thinking-off-only development stage for that project is frozen in
`docs/projects/llm_engines/TOOL-RECOVERY-V3-DEVELOPMENT-2026-08-29.md`.
It produced five 3/3 families and one 0/3 family. Because no family had mixed
development performance, the predeclared advancement rule stopped the project;
no version-3 evaluation suite or thinking-on run exists.
The stop also exposed that mixed-family eligibility cannot sensibly rely on
repeating one identical temperature-zero, same-seed case. Any replacement
development plan must use multiple predeclared variants per family and keep
repeatability separate from difficulty headroom.

The replacement version-4 thinking-off development stage used five distinct,
predeclared variants in each of the six families. It passed 28/30 overall, but
five families remained at 5/5 and only `stale_success` showed family-level
headroom at 3/5. The frozen gate required at least three eligible families, so
advancement stopped. No evaluation suite or thinking-on run exists. The run,
artifact digest, privacy boundary, and exact stopping decision are recorded in
`docs/projects/llm_engines/TOOL-RECOVERY-V4-DEVELOPMENT-2026-08-30.md`.

### Latest completed work — memory/inspection composition

Engram temporal reliability and memory-test attribution were extended on
2026-08-30. Explicit `store_temporal_episode(...)` calls now retain version
history with supersession/retraction metadata while current-state retrieval
suppresses superseded predecessors. Prompt compression packs ranked items
instead of dropping whole memory layers, and prompt/search results expose
structured provenance, budget starvation, exclusions, and temporal conflict
diagnostics. `llm_harness_core` adds deterministic storage → retrieval →
composition → inference → scoring attribution with privacy-minimized artifacts;
Engram provides the adapter. Existing topic replacement remains compatible and
semantic contradiction is not claimed. A paired live validation then found
obsolete evidence in 3/3 legacy current prompts and 0/3 temporal prompts while
preserving exact answers and historical recall. Cold reopen with cached MiniLM
and real ChromaDB subsequently passed current filtering, historical retrieval,
prompt provenance, and persisted metadata in 3/3 timelines. The repository gate
passed at 1,240 tests with 292 skips. See
`docs/projects/ENGRAM-TEMPORAL-AND-MEMORY-EVAL-2026-08-30.md`.

A five-case synthetic composition experiment exercised the remote llama.cpp
engine with Engram memory and Inspector evidence traces. All five baselines
safely returned unknown. In every memory condition Inspector showed both a
current fact and an explicit superseded distractor in the prompt; the model
returned the current value and cited the relevant synthetic memory ID in all
five cases, with no distractor use. This is a bounded 5/5 composition result,
not a general memory-quality claim. Version 1 produced no retained result due
to an interruption and then an artifact-directory defect; the sole disclosed
version-2 retry is frozen in
`docs/projects/MEMORY-INSPECTION-COMPOSITION-2026-08-30.md`.

The next Engram gate exercised cached `all-MiniLM-L6-v2` embeddings on CPU,
ChromaDB, hybrid fusion, and retrieval telemetry across five synthetic cases.
Hybrid retrieval used vector search and ranked the current relevant memory
ahead of an explicit superseded conflict in 5/5 cases; text-only retrieval did
so in 2/5, while both recalled the relevant item in the top three in 5/5.
This bounded result is frozen in
`docs/projects/ENGRAM-VECTOR-RETRIEVAL-2026-08-30.md`.

Engram's persistent-memory trust boundary is now implemented and validated.
The original five-family probe showed untrusted content reaching storage,
retrieval, and prompts in 5/5 cases even though the model resisted compromise.
The opt-in policy now enforces application-assigned trust, tenant, source, and
writer metadata at ingestion, retrieval, and composition. In the final paired
DGX Spark run, policy-on reduced poison storage, retrieval, and prompt inclusion
to 0/5 while preserving exact values and evidence citations in 5/5 cases. The
failed intermediate citation runs are retained and disclosed; they led to the
addition of `evidence_id` in visible prompt provenance. See
`docs/projects/ENGRAM-TRUST-POLICY-LIVE-VALIDATION-2026-08-30.md`.

A separate legitimate-memory availability probe observed 0/3 unexpected
rejections among fully conforming records, but confirmed five operational
blocks involving legacy metadata, aliases, writer rotation, low-trust review,
and quarantine release. Accepted one-item prompts incurred approximately 37
word-count tokens of policy/provenance overhead. Exact-ID review now supports
legacy classification, explicit tenant aliases, and quarantine release with
persisted history; applications must authenticate reviewers, and JSONL history
is not tamper-evident. See `docs/projects/ENGRAM-TRUST-AVAILABILITY-2026-08-30.md`
and `docs/projects/ENGRAM-TRUST-REVIEW-WORKFLOW-2026-08-30.md`.

The follow-up trust-label prompt-pressure profile crossed three word-count
budgets with 2, 5, and 10 fully conforming ranked memories. Its corrected live
version passed exact value/citation in all 18 policy-off/on conditions and kept
the first relevant record under every budget, but policy labels displaced up to
four otherwise accepted memories. At 420 tokens, policy off/on included 10/6
records at density ten; both included all five records at density five. The
infrastructure-invalid version 1 and citation-asymmetric version 2 are retained
and disclosed. See
`docs/projects/ENGRAM-TRUST-PROMPT-PRESSURE-2026-08-30.md`.
The subsequent repository gate passed with 1,252 tests, 304 skips, and three
existing multiprocessing/fork deprecation warnings.

Outside Engram, a six-case deterministic `agent_lib` policy/observability probe
found that `tool_not_granted` enforced denial but was misclassified as a generic
invocation failure in Inspector and shared interop surfaces. The failed version
1 artifact is retained. Adding the existing code to both blocked-error
classifications produced full policy, trace, diagnostic, warning, and critic-
escalation parity in 6/6 corrected version-2 cases. This does not validate OS or
container isolation, concurrent patch ownership, model planning, or UI display.
See `docs/projects/agent_lib/AGENT-POLICY-OBSERVABILITY-2026-08-30.md`.
The subsequent repository gate passed with 1,255 tests, 304 skips, and the same
three multiprocessing/fork deprecation warnings.

The replacement Spark model, reported by the endpoint as
`Qwen3.8-Flash-Next-UD-IQ4_XS`, passed the unchanged five-run version-2
`llm_engines` characterization campaign: exact chat, strict structured output,
typed tool calling, and token log probabilities each passed 5/5 with stable
status. Exact-chat latency was 337.2–434.179 ms with a 361.603 ms median. The
comparison with the earlier 27B campaign is descriptive because load and order
were not controlled. Tool-selection, thinking-on, and long-context behavior
remain separate gates. See
`docs/projects/llm_engines/SPARK-QWEN38-FLASH-NEXT-CHARACTERIZATION-2026-08-30.md`.

The unchanged four-case tool-decision campaign then passed 12/12 decisions with
thinking off and 12/12 with thinking on. Required use, relevant-tool selection,
avoiding unnecessary tools, and typed arguments each passed 3/3 in both
conditions. Thinking increased median latency in every case without changing
the exact outcomes; the off baseline was already at ceiling, so improvement was
not measurable. Conditions were sequential and load was not independently
controlled. See
`docs/projects/llm_engines/SPARK-QWEN38-FLASH-NEXT-TOOL-DECISIONS-2026-08-31.md`.

### Active project — RUN-RECORD-00

The next project is a versioned, cross-package run-artifact surface. The key
correction is that this is **not greenfield**: `agent_lib.eval.repo_navigation`
already emits a schema-v1 `run-record.json`, and the NAV counterfactual tool
already consumes it. ASC, inspector traces, engine responses, campaigns, and
application evals use other shapes.

Phase 0 inventory is complete. ADR-021 accepts the artifact
semantics and ADR-022 places dependency-free envelope/read/validate primitives
in `llm_harness_core` while producer adapters remain in producer packages.
Phase 2 implements lossless NAV-v1 and ASC adapters over one shared agent body;
the package-local gates are recorded in
`docs/projects/RUN-RECORD-00-PHASE-2-COMPATIBILITY.md`.

Phase 3 adds an opt-in recorder around existing generation contracts, exercises
the common reader across generation and agent bodies, and records a successful
privacy-safe Ollama acceptance run. See
`docs/projects/RUN-RECORD-00-PHASE-3-VALIDATION.md`. Inspector loading is the
leading next option, but it is not yet selected. Experiment, RAG, photo, and
course migrations remain deferred.

Phase 4 adds library/CLI artifact loading and separate generation/agent
summaries to `llm_inspector`, including unsupported-version handling and
comparisons that never promote matching labels to model identity. See
`docs/projects/RUN-RECORD-00-PHASE-4-INSPECTOR.md`. No UI work was included.

Phase 5 adds one shared experiment body, adapters for the mutable ASC report
and paired NAV campaign outputs, separately addressable published child runs,
and Inspector experiment summaries. It does not fabricate standalone ASC
timeout records or claim portable bundling/recomputation. See
`docs/projects/RUN-RECORD-00-PHASE-5-EXPERIMENTS.md`.

Phase 6 adds atomic local-directory bundle writing, exact-byte SHA-256
attachments, confined resolution and tamper detection, derived experiment
bundle identities, and Inspector directory loading. See
`docs/projects/RUN-RECORD-00-PHASE-6-BUNDLES.md`.

Phase 7 validates the first concrete no-GPU teaching consumer with a minimized,
privacy-safe ASC failure bundle. It adds resolved-child summaries and scalar
evaluation/aggregate signals to Inspector because the original Phase 6 view
could not answer the lesson's frozen diagnostic question. See
`docs/projects/RUN-RECORD-00-PHASE-7-COURSE-FIXTURE.md`.

Phase 8 removes student-facing monorepo file dependencies, pins the compatible
package set, adds a wheel-installed non-editable copied-course gate, and records
a real local generation provenance lab. A subsequently recovered full
language-tutor implementation was harvested into the examples layer, modernized
against current engine/memory APIs, and restored notebook 07 to the extraction set.
See `docs/projects/RUN-RECORD-00-PHASE-8-COURSE-PORTABILITY.md`.

### Latest completed work — NAV-VERIFIABLE-00

The repository-navigation control investigation is closed at `abcc2f0`.
Wrapper-level text repetition, duplicate-action, and observable-saturation
signals did not provide a reliable model-independent stopping criterion. The
investigation moved the missing information into an explicit task-goal ledger
and evaluated it on mechanically selected, AST-verifiable tasks.

The paired campaign held the final relation schema and scorer constant and
varied only per-step ledger state. On the six exploratory tasks:

- no-ledger terminated 0/6; ledger terminated 3/6;
- no-ledger was relation-correct 0/6; ledger was relation-correct 2/6;
- exact correctness was 0/6 in both arms;
- aggregate tokens were 124,583 no-ledger versus 99,313 ledger.

The formal predeclared verdict is `inconclusive`, not support: no exploratory
pair completed in both arms, so the paired completion-overhead condition was
unevaluable, and no exploratory answer passed exact evidence scoring. The
relation-correct ledger answers over-cited evidence. Do not alter the frozen
rule or scorer post hoc. See
`docs/projects/agent_lib/NAV-VERIFIABLE-00-VALIDATION.md`.

Current `agent_lib` checkpoint: `150 passed` at `abcc2f0`. This is a recorded
checkpoint, not a claim about later untested edits.

### Current project boundary

RUN-RECORD-00 Phase 8 is complete without UI changes. The course repository
split is complete locally at `../llm-failure-lab`; package publication is
deferred. Do not continue NAV-VERIFIABLE-00 as an unfrozen tuning campaign.

**mail_lib — completed project / harvested example.** MAIL-00 shipped a script-first, deterministic Thunderbird
reader and rules-layer triage at `8ee955b`, after spec ratification at `786de7d`. The reader iterates
extensionless mbox files as the source of truth, joins Gloda metadata by bracket-stripped
`Message-ID`, treats Gloda as lagging enrichment, and remains read-only against the Thunderbird
profile. A private maintainer-only
live run forced three corrections: self-mail demotion (`553c49e`), recent user-star-only urgency
(`175352e`, 183 days), and calendar recency gating (`f56e19c`, 31 days).

MAIL-01 then shipped deterministic file-backed personal rules at `72bea66`. It adds strict TOML
validation, most-specific/file-order rule selection, explicit precedence over built-in heuristics,
`--rules` and mail-free `--validate-rules` CLI modes, and a graduated built-in self-mail floor for
link-bearing saved-article messages.

MAIL-02 shipped the ratified localhost mail-assistant MVP at `cb4f11e`: prioritized unread/all
views, app-owned read and summary state, bounded local-model section summaries, and reviewed,
conflict-detecting personal-rule commits that preserve the hand-authored TOML prefix. The combined
mail/app/import/public-API gate passed at the MVP checkpoint (`75 passed`). Post-MVP work through
2026-07-08 added age-filtered views, cached background refresh, sender/domain statistics,
selection controls, and an explicitly configured, preview-and-confirm IMAP Move-to-Trash path
for individual messages and batches. Thunderbird mbox and Gloda access remains read-only; only
the separately configured IMAP action mutates server state. The action fails closed on missing or
ambiguous account mapping, requires IMAP `MOVE`, and does not fall back to copy/delete. Live
validation forced Gmail post-auth capability refresh, Gmail `X-GM-RAW` Message-ID lookup,
SPECIAL-USE All Mail fallback, Trash-folder filtering, per-row eligibility reasons, read-only
proposal preflight, and one IMAP session per selected account during proposal and commit.

The private adoption observation concluded on 2026-07-11: the assistant is
closed as an active daily-use product direction because it competed with
Thunderbird/Gmail on their mature reading and state-management surface. The
LLM features were not the bottleneck; state duplication, sync drift, and
incumbent-client ergonomics were. Keep `mail_lib` and the assistant code as a
deterministic local-mail example/case study, but do not expand it into a
general mail client. See
`docs/projects/mail_lib/POSTMORTEM-MAIL-ASSISTANT.md`. F1 chat, F2 IMAP
`\Seen` propagation, F3 `rag_lib`, F4 `engram`, and F5 interest scoring remain
dormant unless a new non-client-replacement mandate appears.

Earlier neural-memory and knowledge-curation threads both concluded by *declining* to build the
larger system their investigations started toward — each on evidence, per the governing rule
(build a capability when a concrete run fails without it, not speculatively).

**Neural memory (RTRL/TITANS) — parked, output-isolated, default-off.** Fully
implemented behind the additive `MemoryLayer` seam (ADR-016 / NEURAL-01..07)
and evaluated. The core learns sequential signals; the negative decision is
about the tested label-free recall integrations, not a claim that RTRL cannot
learn. Retrieval re-ranking was rejected (catastrophic recall loss, two clean
27b runs). TITANS-style prompt synthesis first returned a clean null, then
NEURAL-07 content inspection found 0/180 expected episodes in emitted hints. A
calibrated surprise-threshold finalist reduced neural updates but regressed
decoy recall; a held-out utility scorer produced no improvement across three
seeds. Neural reranking remains absent, while prompt and episode-importance
outputs are now separately default-off. Longitudinal, domain-consistent
candidate affinity over many genuine sessions has not been measured. The layer
is retained for explicitly enabled telemetry and research; the base package
imports neither `engram.neural` nor torch unless enabled. Reactivation requires
a real usefulness-feedback source plus the predeclared gate in the NEURAL-07
report. `value_dim` and `hidden_dim` remain 32 (64 caused RTRL/P-matrix
overflow).

**Decision-history metadata — shipped.** A knowledge-curation MVP investigation
(could conversation history become an evidence-linked memory?) resolved against
an LLM adjudicator: a three-phase probe showed deterministic structured metadata
strictly dominates an LLM at this task. The shipped capability is small and has
no trust surface: a YAML front-matter schema for ADRs
(`docs/design/DECISION_HISTORY_SCHEMA.md`), a strict validator
(`scripts/validate_decision_history.py`), a `make check-decisions` target + CI
doc gate, and a proof case in ADR-016 (four scoped hypothesis records). It
captures *how conclusions changed and why* at decision time — not via runtime
inference. Adoption is opt-in/incremental: ADRs acquire a decision-history block
when they record a superseded hypothesis or split-application resolution.

Engram exposes the additive `MemoryLayer` extension seam from NEURAL-01; the
four core layers (working/SQLite, episodic/ChromaDB, semantic/SQLite,
cold/FTS5) remain authoritative and untouched.

NAV-TEST-00 is implemented in `agent_lib.eval.repo_navigation` at `c95b8ab` as a
confined, read-only Qwen3.6 repository-navigation evaluation with external
ground truth and result storage.

Next project: select a bounded post-Phase-4 capability. Experiment/campaign
records are the leading architectural option but are not yet selected.
Standing backlog (none gate-blocking): course-repo extraction, TOPOLOGY-01
conversion (ADR-015), and neural reactivation only under a new mandate.

## Neural memory — parked and output-isolated (2026-07-01)

NEURAL-06 added a TITANS-style prompt-synthesis path; the generation-mode
decision eval (qwen3:8b generator, qwen3.6:27b judge, 60 facts, six trials)
returned a clean null. Hints emitted on 180/180 probes and warmup completed at
120 steps, so the mechanism works end-to-end, but no metric beat baseline beyond
one-to-two-judgment noise. A stability correction reverted `value_dim` 64 → 32
(numerically unstable at 64; config_version bumped to 3) and added a fail-closed
non-finite-state guard.

Decision: the layer is **parked** — kept behind the default-off ADR-016 seam,
not actively developed. It cannot improve retrieval as currently integrated;
its tested label-free output paths did not supply dependable candidate utility.
Its distinctive surprise signal may be better suited to novelty/anomaly use
(agent derailment, memory-poisoning detection, chunk segmentation), but that
role is also unproven. Reactivation needs a concrete safety/observability or
longitudinal-memory need plus a predeclared decision gate. Do not re-run the
same retrieval evals without a new mandate. ADR-016 holds the full rationale.

NEURAL-07 follow-up closed the remaining output paths. Affinity is inactive;
the full surprise-threshold finalist failed; all 180 inspected prompt hints
missed the expected episode; a direct-latent variant still missed 76.1%; and a
feedback-free candidate-utility scorer failed across three seeds. Prompt hints
and surprise-based importance adjustment now require separate explicit opt-ins,
so an enabled RTRL layer can collect telemetry without affecting recall. See
`docs/projects/engram/NEURAL-07-RTRL-OUTPUT-EVALUATION.md`.

Interpretation boundary: these runs exceeded the 50-step warmup threshold, so
cold start alone does not explain their result. They did not test whether
direct projected-space affinity separates useful from stale or decoy candidates
after many domain-consistent, genuine project sessions. That longitudinal use
case remains an explicit unmeasured hypothesis, not a forecast of improvement.

---

## Repository hygiene campaign — complete

The staged hygiene campaign through `SPEC-HYGIENE-13` is complete:

- all spine packages use `src/` layout; the root pytest anchoring guard is
  retained by decision for importlib namespace-shadowing behavior;
- active legacy memory-package identities and ghost ML extras were removed,
  with only the explicit backward-compatible backend alias retained;
- strict `llm_engines` mypy checking passes and runs in CI;
- package metadata, README links, launch targets, Streamlit APIs, and pytest
  configuration were reconciled;
- `make test-all` includes diagnostics and passes when the local Podman
  `alpine:3.20` image is available.

Known repository-wide collection limitations outside the core package gates:

- package-scoped test commands remain the supported gate; the integration suite
  lives under `tests/integration_tests/`.

The former course's collection-time live Ollama call was fixed on 2026-06-09
before the teaching material moved to `llm-failure-lab`.

---

## diagnostics_agent — current state

### Gate results (live, `make eval-fp` against qwen3.6:27b on the workstation)

- **fp_rate: 0.000** (threshold ≤ 0.10) — zero false positives across all
  excluded-labeled findings.
- **recall: 1.000** (threshold ≥ 0.90) — every real finding recovered.
- **band_accuracy: 1.000** — every emitted non-excluded concern in its expected band.
- counts: {"ok": 19}; one known-gap concern (`drive_spinup_race`) held out of
  aggregates and reported separately.

### Working / committed

- **response_format fix** — llamacpp backend now sends `{"type": "json_object"}`
  (was the OpenAI-only `{"type": "json_schema"}`, which llama-cpp-python ignores).
  This engaged grammar-constrained decoding; thinking became structurally
  impossible. The original root-cause one-liner.
- **Thinking-suppression belt-and-suspenders** — `/no_think` injection when
  `think=False`, plus `<think>` block stripping (closed and unclosed) in
  `StructuredOutputHandler._extract_json`.
- **flash_attn coherence guard** — IMPLEMENTED. `LlamaCppEngine.__init__`
  auto-enables `flash_attn=True` with a WARNING when a quantized KV cache type
  (non-f16/f32/bf16) is set. No longer a manual step. Prevents the cryptic
  "Failed to create llama_context" on configs that require flash attention.
- **`LlamaCppEngine.count_tokens`** — exposes the model tokenizer; used by the
  prompt-budget clamp.
- **KV-cache quantization, n_batch/n_ubatch, flash_attn, think params** — all
  wired through `LlamaCppEngine`, `factory.py`, `engine_select.py`.
- **Prompt-budget clamp** — IMPLEMENTED in `interpret.py`. Measures prompt
  tokens, reserves `max(configured_max_tokens, 2048)` + safety margin, drops
  lowest-priority/oldest findings until `prompt + reserve ≤ context_limit`. Uses
  `engine.count_tokens` when available, else a `len/3.5` heuristic with a larger
  margin. Never truncates instructions or schema. `context_limit` param added to
  `LogInterpreter.__init__`. (Trigger that motivated it: 6h→24h window overflowed
  n_ctx=8192 with "Interpretation failed".)
- **Benign suppressor cap** — IMPLEMENTED. `BENIGN_SUPPRESSORS` in `rules.py`;
  clusters matching known-benign noise are dropped at triage before rule matching,
  via `TriageConfig.resolved_suppressors()` and `_is_benign()` in
  `_classify_findings`. Covers: ACPI AE_ALREADY_EXISTS, ata DRM info, i915 FIFO
  underrun, atkbd setkeycodes, overlayfs xino fallback, NTP forward time jump,
  gnome-keyring noise, screensaver-locker PAM noise (cinnamon/gnome/x/light/
  kscreen), polkit agent register/unregister, gdm session open/close, Bluetooth
  hci tx timeout. Scoped to locker/session service names so real sshd/sudo/login
  auth still fires.
- **Auth security floor** — IMPLEMENTED. `_apply_security_floor` in `interpret.py`,
  mirroring `_apply_operational_floor`. Deterministically floors `auth`-category
  concern severity to `medium` and raises `security_risk`, independent of model
  output. Call order: operational floor → security floor → coherence. Resolved the
  workstation model under-rating failed-auth findings (was `low`). Flat medium
  floor; volume-aware escalation is backlog.
- **Two-axis risk model** — `security_risk`/`operational_risk` per ADR-012.
  Operational floor: disk/memory/stability ERROR→medium, CRITICAL→high. Auth is
  excluded from the operational floor by design and handled by the security floor.
- **Eval harness** — `src/diagnostics_agent/eval/{calibration,reporting}.py`,
  `scripts/run_fp_eval.py`, gate test `tests/test_fp_gate.py`. Per-concern severity
  calibration scored against the labeled corpus; `finding_ref` is the deterministic
  join key (rule_name or cluster template). Metrics return `None` (rendered `n/a`)
  on zero denominators. `make eval-fp` for human-readable report; `make test-fp-gate`
  (`-m ollama`) asserts fp_rate ≤ 0.10 and recall ≥ 0.90, skipped offline.
- **Labeled eval corpus** — 7 cases in `tests/fixtures/eval/` (`.log` +
  `.labels.json`): benign_kernel_noise, desktop_session_noise, disk_failing,
  drive_spinup_race, mixed_real_and_noise, oom_event, ssh_bruteforce. Concerns
  labeled excluded/low/medium/high; `drive_spinup_race` flagged `known_gap`.
- **Parse-failure observability** — `interpret.py` logs WARNING with full raw
  response, attempt number, schema flag, and parse error on every failure.
- **Phase 3 follow-up Q&A** — `FollowupChat` (`followup.py`) + UI
  (`_render_followup_chat`): grounded-only system prompt, history truncation,
  local-engine guard, session-state chat.
- **173 tests passing, 2 skipped** (`make test-diagnostics`).

### Backlog (not Phase 3; deferred, no current blocker)

- **Sequence-aware detection** — the `drive_spinup_race` known gap. `softreset
  failed (device not ready)` immediately followed by `SATA link up` +
  `configured for UDMA/133` is a benign spin-up race the operational floor
  inflates to medium. Requires temporal correlation at the triage/collection
  stage. The one `known_gap` case in the corpus.
- **Volume-aware auth escalation** — the auth security floor is flat medium;
  sustained brute force should escalate to high. Needs triage-stage count
  aggregation.
- **Triage-stage finding aggregation** — collapse "N occurrences of X over M
  hours, most recent at T" into single count-annotated findings rather than N
  individual ones. Decouples prompt size from time window; feeds volume-aware
  escalation; preserves frequency information the clamp would otherwise lose.
- **VRAM warning banner in UI** — inline banner when detected VRAM ≤ 4GB:
  small-model severity may be over-escalated; verify high/critical before acting.
  Interim proxy now that FP rate is measured; lower priority. VRAM-fit annotation
  already exists in the UI; this is an addendum.

---

## Proven laptop config (GTX 1650, 4GB VRAM)

Model: Qwen3-4B or Gemma-4-E4B at Q4_K_M
Engine: llamacpp
```
n_gpu_layers=-1
n_ctx=8192
cache_type_k=q8_0
cache_type_v=q8_0
flash_attn=True        ← auto-enabled by the coherence guard; required
think=False
n_batch=128
```
Speed: ~32 t/s on GTX 1650.

---

## Model evaluation — empirical results (diagnostics_agent)

Historical reference. All runs below on the **old workstation (8GB VRAM card)** or
the laptop, as noted. NOTE: the Phase 3 gate (band_accuracy 1.000) was measured on
**qwen3.6:27b on the current workstation (RTX 3090, 24GB)**, which is not in this
table — these rows predate that hardware and are kept for tier/calibration context.

| Model | Security | Operational | Notes |
|-------|----------|-------------|-------|
| Qwen3-4B (laptop, 6h) | medium | critical | Screensaver PAM → "unauthorized access" (false positive). Over-escalated i915 and ata. |
| Gemma-4-E4B (laptop) | none | high | Found FAT-fs dirty bit (real finding, confirmed). Still over-escalated ACPI/i915. Better S/N than Qwen. |
| Phi-4-mini-instruct (laptop) | low | high | Abstracted concerns to generic labels (service_failed, kernel_error) — poor grounding. |
| Qwen3.5-9B Q4 (8GB, full) | none | high | Best causal reasoning: correctly linked service failures to disk I/O root cause. Explicit "not a security breach" on keyring. |
| LFM2.5-8B-A1B (8GB) | **high** | medium | False positive: service failures rated high-security. Inverted causality. ~1B active parameters → 1B-quality inference. |
| Gemma-12B Q4 (8GB, 20/46 layers GPU) | none | high | Best benign-pattern calibration: keyring "common during session start, local noise." Services correctly low. Surfaced xHCI USB resume error. |

**Tier summary:**
- 4GB / 4B: over-escalates; useful as collector, not trusted interpreter. Warn user.
- 8GB / 9B+ (full GPU): trustworthy enough to act on. Qwen3.5-9B recommended.
- 8GB / 12B (partial offload): comparable to 9B, slower. Gemma-12B slight edge on benign-pattern calibration.
- Sparse MoE: "active param" count predicts quality, not total params. LFM 8B-A1B ≈ 1B quality.
- VRAM warning threshold: ≤ 4GB. At 8GB with 9B+ model, output is trustworthy.

**Persistent false positives from this eval — now addressed:**
- ACPI AE_ALREADY_EXISTS → **suppressed** (benign cap)
- ata DRM info → **suppressed** (benign cap)
- i915 FIFO underrun → **suppressed** (benign cap)
- Drive spin-up softreset sequence → **NOT yet fixed**; this is the `drive_spinup_race`
  known gap (sequence detection, backlog). Operational floor still rates it medium.

---

## Code sync hazard — IMPORTANT

The laptop and workstation trees have diverged in the past (hand-tested laptop
state vs. Codex-committed history on the workstation).

**Before copying in either direction: `git diff` the trees.**
Laptop → workstation naively overwrites Codex commit history.
Workstation → laptop loses hand-tested laptop iterations.

Reconcile with a proper merge, or at minimum diff changed files before moving
anything.

---

## Standing overdue items

- **Public-API doc-sync** — `LlamaCppEngine` signature changed across this work
  (think, count_tokens, flash_attn guard, KV/batch params). Docstrings and README
  need a pass.
- **VRAM memory-model ADR** — still not written.
- **Import topology — RESOLVED** — all spine packages use `src/` layout and
  editable installs. Pytest importlib root collection can still instantiate
  outer namespace packages from package-named conftests, so the root conftest
  anchoring guard is retained as the deliberate compensating control. Attempts
  to retire it caused `tests.conftest` collisions or repository-root namespace
  imports; ADR-008 records the closed cost/benefit decision.
- **Repo hygiene** — complete: CI deduplication, `run-diagnostics`/`run-inspector`
  targets added, inspector `__main__.py` and README port corrected.
- **STATUS.md** — updated this session. Keep current each session.

---

## Package layout

    agent_lib/src/agent_lib
    engram/src/engram
    llm_harness_core/src/llm_harness_core
    llm_inspector/src/llm_inspector
    llm_inspector_ui/src/llm_inspector_ui
    rag_lib/src/rag_lib
    llm_engines/src/llm_engines
    examples/diagnostics_agent
    examples/language_tutor
    examples/agent_coordination_teaching

## Decision rules

- Build a capability when a concrete project run fails without it.
- MEMBERSHIP filter: reusable building block or agent-layer consumer?
- Design guidance for deferred work: `docs/design/AGENT_BUILD_NOTES.md`,
  `docs/design/INFERENCE_OPTIMIZATION.md`.
- **Active project: NetFlow analysis** — diagnostics_agent FP-rate gate is met,
  so this is unblocked. See "Current posture" for first steps.

### NetFlow data handling (PII)

The dissertation NetFlow capture is paired with campus LDAP data mapping IP
addresses to real users and roles. That mapping is PII and must never enter the
repo, a prompt, an eval corpus, or any committed artifact in identifiable form.

- Scrub before ingest, not after. Replace each real identity with a stable
  pseudonym (e.g. `user_0001`, role kept as a coarse class only) via a mapping
  table held **outside** the repo and never committed.
- Drop or generalize any field that re-identifies (full hostname, MAC, exact
  org-unit). Roles may be retained at a coarse granularity if useful as labels.
- Add the scrub step as a gate before any flow data is written into the
  campaign tree; treat the raw capture + LDAP join as read-only source.
