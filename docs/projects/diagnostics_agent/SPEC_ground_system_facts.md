# Build Spec — Ground System Facts in the Interpreter Prompt — `diagnostics_agent`

**Files:** `examples/diagnostics_agent/src/diagnostics_agent/interpret.py` (primary),
a new small module for fact collection, `orchestrate.py` (wire facts in),
`ui/app.py` (optional display), plus tests.
**Type:** additive. Schema unchanged; prompt augmented; one new deterministic
collector.
**Why:** `interpret.py` feeds the model no ground truth about the host, so a weak
model fabricates system facts (Phi-3 invented "Ubuntu 20.04 / kernel 5.13" on a
machine running neither). The fix: gather real OS/kernel/hostname deterministically
on the host and inject them as authoritative context the model must not contradict.
This is consistent with the locked decision "push non-negotiable judgments into the
deterministic layer; treat LLM output as commentary to verify."

## Design

### 1. Deterministic fact collection — new module `system_facts.py`

Gather facts on the **host**, not in the sandbox, and not via the LLM. Use Python
stdlib + `/etc/os-release` so it works without extra deps and without shelling out
where avoidable.

```python
@dataclass(frozen=True)
class SystemFacts:
    hostname: str | None
    kernel_release: str | None      # uname -r  -> platform.release()
    kernel_version: str | None      # uname -v  -> platform.version()  (optional)
    os_name: str | None             # /etc/os-release PRETTY_NAME or NAME
    os_version: str | None          # /etc/os-release VERSION_ID
    arch: str | None                # platform.machine()

    def to_dict(self) -> dict: ...
    def as_prompt_block(self) -> str: ...   # human-readable, see below
```

Collection (`collect_system_facts() -> SystemFacts`):

- `hostname`: `platform.node()` (fallback `socket.gethostname()`); `None` if empty.
- `kernel_release`: `platform.release()`.
- `kernel_version`: `platform.version()`.
- `arch`: `platform.machine()`.
- `os_name` / `os_version`: parse `/etc/os-release` (KEY=VALUE, strip quotes). Prefer
  `PRETTY_NAME` for `os_name`; fall back to `NAME`. `VERSION_ID` for `os_version`.
  If the file is absent or unreadable, both `None` — do **not** guess, do **not**
  fall back to `platform.platform()` strings that can be wrong.
- Every field independently `None`-able. A missing fact must render as "unknown",
  never as a fabricated or inferred value. This is the whole point: the model should
  receive truth-or-silence, never a plausible guess.

`as_prompt_block()` renders only the known facts, e.g.:

```
Verified host facts (authoritative — do not contradict or invent beyond these):
- hostname: hammerhead
- os: Ubuntu 25.10
- kernel: 6.17.0-23-generic
- arch: x86_64
Any fact not listed above is unknown; do not state it.
```

Omit any line whose value is `None`. If *all* are `None`, render a single line:
`No verified host facts are available; do not state OS, kernel, or hostname.`

### 2. Thread facts into `LogInterpreter`

- `LogInterpreter.interpret(self, summary, *, system_facts: SystemFacts | None = None)`.
  Keep it optional so existing callers and tests don't break; when `None`, behavior
  is exactly as today (back-compat).
- In `_build_request`, when `system_facts` is provided, prepend its prompt block to
  the **user** message, before `_FIELD_GUIDE` / triage JSON:

  ```python
  def _user_prompt(summary, system_facts=None) -> str:
      facts = f"{system_facts.as_prompt_block()}\n\n" if system_facts else ""
      summary_json = ...
      return f"{facts}{_FIELD_GUIDE}\nTriage summary JSON:\n{summary_json}"
  ```

  Pass `system_facts` down from `interpret` → `_build_request` → `_user_prompt`.
  The retry path (`_append_correction`) already replays `original.messages`, so the
  facts ride along on retry automatically — no change needed there.

### 3. Strengthen the system prompt's anti-invention clause

`_SYSTEM_PROMPT` already says "Do not invent ... hosts ...". Add one sentence tying
it to the new block:

> When 'Verified host facts' are provided, treat them as authoritative: never
> contradict them and never assert an OS version, kernel version, or hostname that
> is not listed there.

Do not over-engineer the wording; one explicit sentence is enough and keeps the
prompt short (it stays a system-prompt, not a policy essay).

### 4. Wire through the orchestrator

`DiagnosticsOrchestrator` should collect facts once per run and pass them to the
interpreter:

- In `run()`, call `collect_system_facts()` (cheap, host-side, no sandbox) and pass
  the result into `self.interpreter.interpret(summary, system_facts=facts)`.
- Add the facts to the audit dict (`_build_audit`) under a `system_facts` key via
  `facts.to_dict()`, so the audit trail records what ground truth the model was
  given. This matters for a security tool: the audit should show the model was
  anchored, and to what.
- Make collection failure non-fatal: if `collect_system_facts()` raises, log/degrade
  to `None` (interpret runs unanchored, as today) rather than failing the run.
  Fail-loud applies to the sandbox read boundary, not to an optional grounding nicety.

### 5. UI (optional, light)

If quick: surface the collected facts in the UI alongside the result (a small
"Host" caption). Not required for acceptance; skip if it means building new UI
plumbing. The grounding value is in the prompt + audit, not the display.

## Non-goals

- Do **not** collect facts inside the sandbox. These are host facts; the sandbox is
  for untrusted read-only command execution, not for describing the host.
- Do **not** add new runtime deps. stdlib `platform`/`socket` + reading
  `/etc/os-release` only.
- Do **not** feed package lists, full `uname -a` strings, or anything large — just
  the few facts a model tends to fabricate. Keep the block short; it competes with
  the triage summary for context.
- No schema change to `Interpretation`.

## Tests (`examples/diagnostics_agent/tests/`)

`system_facts.py` (pure, no model):

1. **os-release parse:** feed a temp file with `PRETTY_NAME="Ubuntu 25.10"`,
   `VERSION_ID="25.10"` → `os_name == "Ubuntu 25.10"`, `os_version == "25.10"`.
2. **quotes stripped / missing keys:** values with and without quotes parse; absent
   `VERSION_ID` → `os_version is None`.
3. **os-release absent:** point the parser at a nonexistent path → both os fields
   `None`, no exception.
4. **prompt block omits None lines:** a `SystemFacts` with `os_*` set, `hostname=None`
   → `as_prompt_block()` contains os/kernel lines, no `hostname:` line.
5. **all-None block:** every field `None` → block is the single "no verified host
   facts" sentinel line.

`interpret.py` (use a stub engine, the existing pattern):

6. **facts appear in the user prompt:** stub engine captures the request; assert the
   user message contains the verified-facts block and that it precedes the triage
   JSON.
7. **back-compat:** `interpret(summary)` with no `system_facts` produces a request
   with no facts block (identical to current behavior).
8. **(optional, strong) anti-confab regression:** a stub engine that echoes a
   fabricated kernel in `reasoning` still validates (schema unchanged) — this test
   documents that grounding is a prompt-level mitigation, not an enforced guarantee.
   Keep it as a comment/docstring if a full stub is heavy; the point is to record
   that the deterministic layer informs but does not police free-text fields.

`orchestrate.py`:

9. **facts in audit:** a run (stub engine, fake collector returning known facts) →
   `result.audit["system_facts"]` matches the collected facts dict.
10. **collection failure is non-fatal:** monkeypatch `collect_system_facts` to raise
    → run still completes, interpret called with `system_facts=None`,
    `audit["system_facts"]` is null/absent (pick one and assert it).

## Acceptance

- `make test-diagnostics` green (current 123 passed, 1 skipped; expect +~8).
- `LogInterpreter.interpret` accepts optional `system_facts`; default path unchanged.
- A real run on the workstation injects true OS/kernel/hostname; the audit records
  them.
- `git diff` confined to `system_facts.py` (new), `interpret.py`, `orchestrate.py`,
  optional `ui/app.py`, and test files. No schema/prompt-essay sprawl.

## Real-model validation (do once, not in CI)

The motivating bug was model-specific. After the change, rerun the grounding test
from DIAGNOSTICS_AGENT_STATUS: run a small model (the one that confabulated) and
confirm it no longer asserts a wrong OS/kernel now that the truth is in-prompt. If a
model *still* contradicts the verified block, that model is disqualified for the
interpretation layer — which is itself a useful result, recorded against the model,
not the code.
