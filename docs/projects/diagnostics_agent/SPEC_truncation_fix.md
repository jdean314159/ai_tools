# Build Spec — Truncation Fix (reframed) — `diagnostics_agent`

**Status of the original three-part item:** field projection is already done in
`collect.py` (`JOURNAL_OUTPUT_FIELDS` + `--output-fields=`); a `truncated` boolean
is already plumbed sandbox → orchestrate → UI. This spec covers only the parts that
are verifiably still broken after reading the code.

## Verified problem (re-confirmed against current source)

- The default read path runs `cat /staging/collected.log` **inside the sandbox**
  (`orchestrate.py` `_read_collected_logs`, sandbox branch). The sandbox caps
  command stdout at `max_output_bytes = 1_048_576` (`sandbox.py:23`), applied in
  `_truncate_text` (`sandbox.py:148`,`221`).
- `_truncate_text` keeps `encoded[:max_bytes]` — the **head** of the output.
- `journalctl_collector` sets **no ordering flag**, so journald emits **oldest-first
  (ascending)**. Head-truncation therefore drops the **newest** entries — it keeps
  the boot burst and loses recent runtime, the opposite of what a diagnostics tool
  wants.
- The host-side path (`sandbox is None`) reads the file whole with no cap, so the
  bug is specific to the sandboxed (default, security-relevant) path.

Net: a large collection is silently truncated to its least-relevant slice, and the
only signal is `truncated=True` buried in a UI debug string.

## Scope / non-goals

- Do **not** re-add field projection — already present and more complete than the
  original proposal.
- Do **not** change `journalctl` ordering to `--reverse`. Triage and the conservation
  invariant assume natural order; flipping the source order risks subtle breakage.
  Fix truncation at the truncation site instead.
- No schema change. No prompt change.

## Fix

### 1. Raise the default cap (backstop) — `sandbox.py`

Change `SandboxConfig.max_output_bytes` default from `1_048_576` to `16_777_216`
(16 MiB). Field projection already cut per-line size, so this is now a backstop, not
the primary lever — but 1 MiB is too low for a multi-MB journal. Keep it a config
field so a caller can lower it for untrusted commands.

### 2. Make truncation tail-biased — `sandbox.py`

The real fix. When output exceeds the cap, keep the **newest** content for
time-ascending sources. Implement as a config-selected policy rather than hardcoding,
because not every sandboxed command is time-ordered (a future `lsusb -t` is not).

- Add to `SandboxConfig`:
  ```python
  truncate_keep: Literal["head", "tail"] = "tail"
  ```
  Default `"tail"` — the journald collector is the primary consumer and is
  ascending, so newest-kept is the safe default. A caller running a non-ordered
  command can pass `"head"`.

- Change `_truncate_text(text, max_bytes)` →
  `_truncate_text(text, max_bytes, keep="tail")`:
  - `keep == "head"`: current behavior — `encoded[:max_bytes]`.
  - `keep == "tail"`: `encoded[-max_bytes:]`.
  - In both cases decode with `errors="ignore"` (already done) — note the multibyte
    boundary can clip a partial char at the *cut* end; `ignore` handles it. For
    `tail`, additionally drop everything up to and including the first newline after
    the cut so the first retained line is whole (journald JSON is one object per
    line; a half-line is unparseable and would make triage drop a record silently).
    If there is no newline, keep as-is.

- Update both call sites (`sandbox.py:148-149`) to pass
  `keep=self.config.truncate_keep`. stdout and stderr both use the configured policy.

### 3. Surface truncation as a visible warning — UI + result

The `truncated` flag currently reaches the UI only as `f"truncated={sandbox.truncated}"`
in a debug line (`ui/app.py:115`). The original requirement was a **visible warning**.

- In `ui/app.py`, when the run's `sandbox_result.truncated` is true, render a
  Streamlit `st.warning(...)` above the interpretation, with concrete text, e.g.:
  > ⚠️ Collected log output exceeded the {cap} read limit and was truncated to the
  > most recent {cap}. Older entries in the window were not analyzed. Narrow
  > `--since`, raise the priority filter, or increase `max_output_bytes` for a
  > complete view.
  Compute `{cap}` from the sandbox config so the message stays accurate if the
  default changes.
- Keep the existing debug-line flag too; the warning is additive.
- The audit dict already carries `truncated` (`orchestrate.py:168`) — leave it; the
  audit trail should record that analysis was partial. Good as-is.

## Tests (`examples/diagnostics_agent/tests/`)

Sandbox-level (no container needed — test `_truncate_text` directly):

1. **tail keeps newest:** ascending numbered lines exceeding `max_bytes`, `keep="tail"`
   → result contains the last line, not the first; byte length ≤ `max_bytes`.
2. **head still works:** same input, `keep="head"` → contains first line, not last.
3. **tail drops partial leading line:** construct input where the `[-max_bytes:]` cut
   lands mid-line → first retained line is whole (starts after a newline), no partial
   JSON object survives.
4. **under cap is untouched:** input < `max_bytes` → returned unchanged, `truncated`
   false, for both policies.
5. **config default is tail and 16 MiB:** `SandboxConfig()` →
   `truncate_keep == "tail"`, `max_output_bytes == 16_777_216`.

UI: if the UI has a testable render path, assert `st.warning` is invoked when
`truncated` is true; if UI tests aren't established, skip — don't build a Streamlit
test harness for this.

## Acceptance

- `make test-diagnostics` green (current baseline 116 passed, 1 skipped; expect +~5).
- `SandboxConfig` default truncation is tail-biased at 16 MiB.
- A truncated run shows a visible UI warning, not only a debug-line flag.
- `git diff` confined to `sandbox.py`, `ui/app.py`, and one test file. No change to
  `collect.py`, `triage.py`, `interpret.py`, schema, or prompts.

## Note for the author

The deeper correctness question — whether a security diagnostics tool should ever
silently analyze a partial window even with a warning — is real but out of scope
here. The honest-partial posture (analyze what fits, loudly flag the gap) matches the
project's fail-loud principle. If later runs show truncation is common rather than
exceptional, the right move is chunked multi-pass collection (the RLM pattern in
`INFERENCE_OPTIMIZATION.md`), not an ever-larger cap. Record that in the campaign
backlog if it recurs; don't pre-build it.
