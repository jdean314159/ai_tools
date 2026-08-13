# Repo Status

Last updated: 2026-08-13

Single source of truth for the current `ai_tools` repo state. Use this file
first when starting a new thread or resuming work after a handoff.

## Current posture

**Phase: RUN-RECORD-00 Phase 3 generation/agent cross-kind proof is complete;
the next bounded consumer capability has not been selected. NAV-VERIFIABLE-00 remains complete
with a frozen `inconclusive` verdict; NAV-TEST-00 remains an autonomous
navigation failure. Mail-assistant adoption is closed, and neural memory
remains parked and output-isolated.**

For a fresh Claude thread, read
`docs/internal/CLAUDE_THREAD_HANDOFF.md` after this file. For a fresh Codex
thread, read `docs/internal/CODEX_THREAD_HANDOFF.md`.

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

RUN-RECORD-00 Phase 3 is complete without rewriting legacy producers or engine
backends. Select the next bounded consumer capability before implementation.
Do not continue NAV-VERIFIABLE-00 as an unfrozen tuning campaign.

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

**Neural memory (RTRL/TITANS) — parked, output-isolated, default-off.** Fully implemented behind
the additive `MemoryLayer` seam (ADR-016 / NEURAL-01..07) and evaluated.
Retrieval re-ranking was rejected (catastrophic recall loss, two clean 27b
runs). TITANS-style prompt synthesis first returned a clean null, then NEURAL-07
content inspection found 0/180 expected episodes in emitted hints. A calibrated
surprise-threshold finalist reduced neural updates but regressed decoy recall;
a held-out utility scorer produced no improvement across three seeds. Neural
reranking remains absent, while prompt and episode-importance outputs are now
separately default-off. The layer is retained for explicitly enabled telemetry
and research; the base package imports neither `engram.neural` nor torch unless
enabled. Reactivation requires a real usefulness-feedback source plus the
predeclared gate in the NEURAL-07 report. `value_dim` and `hidden_dim` remain 32
(64 caused RTRL/P-matrix overflow).

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

Next project: select a bounded post-Phase-3 consumer capability; inspector
loading and kind-specific summaries are the leading option.
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
not actively developed. It cannot improve retrieval as integrated; its only
distinctive output is a label-free surprise signal better suited to
novelty/anomaly use (agent derailment, memory-poisoning detection, chunk
segmentation). Reactivation needs a concrete safety/observability need plus a
predeclared decision gate. Do not re-run retrieval evals without a new mandate.
ADR-016 holds the full rationale.

NEURAL-07 follow-up closed the remaining output paths. Affinity is inactive;
the full surprise-threshold finalist failed; all 180 inspected prompt hints
missed the expected episode; a direct-latent variant still missed 76.1%; and a
feedback-free candidate-utility scorer failed across three seeds. Prompt hints
and surprise-based importance adjustment now require separate explicit opt-ins,
so an enabled RTRL layer can collect telemetry without affecting recall. See
`docs/projects/engram/NEURAL-07-RTRL-OUTPUT-EVALUATION.md`.

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

The collection-time live Ollama call in `course/test_loop.py` was fixed on
2026-06-09 by moving executable work behind `main()`.

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
