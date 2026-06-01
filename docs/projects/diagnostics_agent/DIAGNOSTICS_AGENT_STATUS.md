# diagnostics_agent — Status & Handoff (reconciled 2026-05-31)

**Purpose:** read-only local-LLM system diagnostics tool in the `ai_tools` monorepo.
**Pipeline:** collect → triage (deterministic) → interpret (local LLM) → audit; with
optional grounded follow-up Q&A over a completed result.
**Posture:** local-only, sandboxed, propose-not-execute, fail-loud, auditable.
**Location:** `examples/diagnostics_agent/` (moved from repo root; it is an example in
the *campaign* stage, not a frozen reference). Campaign docs:
`docs/projects/diagnostics_agent/`.
**Tests:** 123 passed, 1 skipped (live-model E2E) as of this reconciliation.

> **Reconciliation note.** This file was rewritten by reading the current source
> tree end to end, because the prior version had drifted: several items listed as
> "open" or "to build" were already implemented. Each item below was checked against
> code, not memory. Where an item is marked done, the implementing symbol is named so
> the claim is falsifiable.

---

## Public surface (from `__init__.py` `__all__`, verified)

Errors: `SandboxError`, `RuntimeNotFoundError`, `ImageNotAvailableError`,
`MountError`, `InterpreterError`, `RemoteEngineRefused`, `InterpretationParseError`,
`CollectionReadError`.
Collect: `CollectedLogs`, `Collector`, `CommandCollector`, `journalctl_collector`.
Sandbox: `ReadOnlySandbox`, `SandboxConfig`, `SandboxResult`, `make_staging_sandbox`.
Triage: `LogTriage`, `TriageConfig`, `TriageSummary`, `Finding`, `EventCluster`,
`LogRecord`, `Severity`.
Interpret: `LogInterpreter`, `Interpretation`, `ConcernAssessment`.
Followup: `FollowupChat`, `ChatTurn`.
Models: `LocalModel`, `ModelDiscoveryError`, `estimate_fit`, `list_local_models`.
Orchestrate: `DiagnosticResult`, `DiagnosticsOrchestrator`.

Local-only enforcement is shared: `engine_guard.require_local_engine` is used by both
`LogInterpreter` (interpret.py) and `FollowupChat` (followup.py). The guard keys on
backend *name* (`LOCAL_BACKENDS`), so pointing a laptop's `OllamaEngine` at the
workstation LAN IP passes — it is your own trusted box, not cloud.

---

## Built & working (verified against code)

- **Phase 0 — `sandbox.py`:** `ReadOnlySandbox`, `SandboxConfig`,
  `make_staging_sandbox`. Rootless Podman, `--network none`, `--read-only`,
  `--cap-drop ALL`, keep-id userns, staged file 0600. Output truncation is
  **tail-biased by default** (`truncate_keep="tail"`), cap `max_output_bytes`
  = 16 MiB, partial leading line dropped on tail-cut, `truncated` flag propagated.
- **Phase 1 — `triage.py` + `rules.py`:** severity from journald `PRIORITY`,
  template-masking clustering, findings-vs-clusters split, conservation invariant,
  structured self-noise exclusion (`diag-sbx-`). `DEFAULT_RULES` covers auth (ssh/
  sudo/pam), memory (oom), disk (`disk_io_error`, incl. `ata\d+` patterns), stability
  (segfault, kernel bug), and service (`service_failed`).
- **Phase 2 — `interpret.py`:** `LogInterpreter`, two-axis
  `security_risk`/`operational_risk`, `ConcernAssessment` (finding_ref → rationale →
  severity), local-only guard, `json_schema` + retry-once. Deterministic operational
  floor (disk/memory/stability ERROR→≥medium, CRITICAL→≥high; auth not floored).
  **Risk-coherence clamp** (`_apply_risk_coherence`) ensures
  `max(security_risk, operational_risk) ≥ max(concern.severity)`, raising the higher
  axis only, never lowering; runs after the operational floor.
- **Follow-up Q&A — `followup.py`:** `FollowupChat` + `ChatTurn`, grounded read-only
  over a `DiagnosticResult`, shared local-only guard, capped history. Cannot
  fetch/run/mutate (that bright line is Phase 3).
- **Phase C — `orchestrate.py` + `collect.py`:** `DiagnosticsOrchestrator`,
  `DiagnosticResult`, `Collector`/`CommandCollector`/`journalctl_collector`.
  `journalctl_collector` emits `--output-fields=` (full `JOURNAL_OUTPUT_FIELDS` set,
  covering everything triage/rules/self-noise read). Partial-failure tolerant;
  fail-loud on sandbox read error/timeout.
- **UI — `ui/app.py` + `models.py`:** Streamlit. Ollama model picker, VRAM-fit
  annotation, run-on-button-only, render-from-state, visible truncation warning.

---

## Open items — priority order (reconciled)

1. **Ground system facts in the interpreter prompt — OPEN (substantive).**
   `interpret.py` does not feed real `uname -r` / distro / hostname into the prompt,
   so a weak model can fabricate them (Phi-3 invented "Ubuntu 20.04 / 5.13"). Pull
   them deterministically on the host and inject as ground truth the model must not
   contradict. Closes one confabulation category. This is the top real code item.
2. **`overall_risk ≥ max(concern severity)` consistency — DONE.** Implemented as the
   axis-aware `_apply_risk_coherence` clamp (raises higher axis; tie → operational).
   Verified against a live run (operational high matched a high disk concern).
3. **Truncation fix — DONE.** Field projection (collect.py), tail-bias + 16 MiB cap +
   partial-line drop (sandbox.py), visible UI warning (ui/app.py). Verified by tests.
4. **Follow-up Q&A — DONE.** `FollowupChat` shipped with the shared guard. The guard
   extraction the prior doc wanted is done (`engine_guard.py`, used by both
   consumers).
5. **`*.egg-info/` gitignore — DONE.** Handled during the examples/ move.
6. **`service_failed` false-positive — LIKELY FIXED; verify on a real run.** The rule
   now matches only `Failed to start` / `entered failed state` (rules.py:40), not
   bare non-zero exits, so clean-exit daemons (`status=8`, `inactive (dead)`) should
   not trigger it. No code change indicated; confirm against the laptop run that
   originally surfaced it before closing.
7. **IPv4-mask octet bound — OPEN (cosmetic).** `_IPV4_RE`
   (`(?:\d{1,3}\.){3}\d{1,3}`, triage.py:210) has no ≤255 bound, so dotted version
   strings like `1.6.99.901` mask as `<IP>`. Tighten to octets ≤255 only if it
   proves annoying in real output.

### Future (not now)

- **Structured baseline/trend store + disposition memory.** Change-detection (is
  `ata10` new/worsening or constant since boot?) plus a confirmed-benign override —
  the only legitimate way to demote a floored-but-benign recurring signal (the
  deterministic floor currently pins `ata10` at medium forever). A deterministic
  store fits trend; `engram` fits fuzzy disposition but inherits contradiction-bleed.
  Recurring-signal demotion was observed in this session's live run (`ata10` floored)
  — evidence for this item, not a regression.
- **Phase 3 — generated-query exploration (gated).** Decided design: a vetted
  parameterized check catalog (allowlist) the model selects from — NOT free code
  generation. Starter catalog still to draft. KEV/CISA rejected as layer mismatch.
- **Chunked multi-pass collection (RLM).** If truncation proves common rather than
  exceptional in real runs, the right move is chunked multi-pass collection
  (`INFERENCE_OPTIMIZATION.md` RLM pattern), not an ever-larger cap. Don't pre-build.

---

## Locked decisions (don't relitigate)

- Push non-negotiable judgments into the deterministic layer; treat LLM output as
  commentary to verify, not fact to trust. Every confabulation this project hit was
  in the LLM narrative; deterministic triage stayed honest.
- Two risk axes (security vs operational); a single axis gets pulled toward whichever
  framing dominates the prompt.
- Deterministic floor for hardware presence; LLM judgment for auth context.
- Calibration is probabilistic on local models — spot-check across models.
- Truncate at the truncation site (tail-bias in sandbox), not by reversing journald
  order — keeps triage's natural-order and conservation assumptions intact.

---

## Laptop / model findings (4 GB GTX 1650)

Unchanged from prior doc: 4B models OOM on 4 GB; 3B-class models confabulate on this
task (invent OS/kernel, finding IDs, security framings). Capability floor for grounded
interpretation is above what fits fully on 4 GB. Laptop role: deterministic collector,
or point its `OllamaEngine` at the workstation LAN IP (passes the guard). Grounding
test: run a model, check whether it invents system facts refutable by `uname -r` /
`lsb_release -a`; inventing them disqualifies it for the interpretation layer. (Item
#1 above directly hardens against this.)

---

## Launch reference

Per machine (recreate venv — venvs are NOT portable):
```bash
rm -rf ~/ai_tools/.venv
python3 -m venv ~/ai_tools/.venv
source ~/ai_tools/.venv/bin/activate
pip install --upgrade pip
cd ~/ai_tools/llm_harness_core      && pip install -e .
cd ~/ai_tools/llm_engines           && pip install -e .
cd ~/ai_tools/examples/diagnostics_agent && pip install -e ".[ui]"
```
Run:
```bash
cd ~/ai_tools/examples/diagnostics_agent
source ~/ai_tools/.venv/bin/activate
streamlit run src/diagnostics_agent/ui/app.py      # http://localhost:8501
```
Requires `systemd-journal` group membership (NOT root) and rootless Podman with the
fuse-overlayfs `storage.conf` + `podman pull docker.io/library/alpine:3.20`. From the
repo root, `make install` installs the example editable and `make test-diagnostics`
runs its suite.
