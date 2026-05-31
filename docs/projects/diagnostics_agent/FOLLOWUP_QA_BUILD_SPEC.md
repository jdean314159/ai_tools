# Follow-up Q&A Build Spec — Grounded Chat Over Results

**For:** an autonomous coding agent (Codex).
**Parent:** `docs/projects/diagnostics_agent/CAMPAIGN.md`.
**Status:** committed (presentation/conversation layer; adds **no** system access).
**Consumes:** a completed `DiagnosticResult` and the existing local engine.

A read-only Q&A over results already in hand. The user asks questions about the
findings ("why is ata10 medium?", "what's the difference between the chronyd and
overlayfs warnings?") and the model answers **only from the existing
`DiagnosticResult`**. No new collection, no sandbox, no command execution, no
data fetching. The data is already in `session_state`; a question is one more
local-engine call with that context.

Two tasks: **Task A** (library, fully unit-testable) then **Task B** (UI panel).

---

## The bright line (read this first)

This capability **explains existing results**. It must never **fetch, collect,
run, or change** anything. The moment a chat turn can trigger new collection or a
command ("pull the dmesg around ata10"), that is **Phase 3** — the LLM choosing
what to run, gated by the sandbox and the vetted catalog — and it does **not**
belong in this spec. Any such capability is a separate, later, gated build. Keep
the `DiagnosticResult` immutable; the chat is a view onto it, not an actor.

---

## Task A — `FollowupChat` (`src/diagnostics_agent/followup.py`)

```python
@dataclass(frozen=True)
class ChatTurn:
    role: Literal["user", "assistant"]
    content: str

class FollowupChat:
    def __init__(self, engine, *, allow_remote: bool = False,
                 temperature: float = 0.3, max_tokens: int = 768,
                 max_history_turns: int = 8) -> None:
        """Reuse the SAME local-only guard as LogInterpreter — extract that guard
        into a shared helper if it is currently inline in LogInterpreter.__init__,
        so both use one implementation and cannot diverge. Remote backends
        (openai/anthropic) raise RemoteEngineRefused unless allow_remote=True:
        findings contain IPs/usernames and must not leave the host."""

    def answer(self, result: DiagnosticResult, question: str,
               history: Sequence[ChatTurn] = ()) -> str:
        """Free-text answer grounded ONLY in `result`. Read-only — never mutates
        `result`, never fetches or runs anything. Returns prose (no json_schema;
        this is conversation, not a structured verdict)."""
```

### A1. Grounding context (what `answer` puts in the prompt)
From `result`, serialize for context: the `TriageSummary` (findings, top clusters,
severity counts, `excluded_self_noise`) and the `Interpretation` (reasoning,
summary, `security_risk`, `operational_risk`, concerns, recommended checks), plus
the collection metadata (command, `source_description`, time window). **Not** the
raw staged logs — the summary is the distilled grounding, same as the interpreter
saw. Apply the same example-compaction the interpreter prompt uses; the summary is
large and history accumulates on top of it.

### A2. System prompt (grounding is the whole point)
Instruct the model explicitly: answer **only** from the provided diagnostic
results; if the question asks about data not present (raw log lines, current system
state, output of a command that wasn't collected), say so plainly — **do not invent
system state**; you cannot run commands, fetch data, or change the diagnosis; you
explain what is already here; be concise. Without this, you get confident
fabrication about the machine — the standard ungrounded-Q&A failure.

### A3. Message assembly
System prompt (A2) → grounding context (A1) → the most recent
`max_history_turns` of `history` (drop older; the engine is stateless so history
is passed each call and must stay bounded) → the new `question`. Call the engine,
return `response.text`. No retry loop (free text can't fail schema validation); let
an engine error propagate for the UI to surface.

### A4. Exports & errors
Export `FollowupChat`, `ChatTurn` from `__init__.py`. Reuse the existing
`InterpreterError`/`RemoteEngineRefused` hierarchy; add no new structured-output
machinery.

### A5. Task A tests (no model, no network — stub engine)
- **Answer path:** stub engine returns a fixed string → `answer()` returns it.
- **Grounding context present:** the built request contains a known finding from
  the result (assert a rule name or cluster template, e.g. `ata10`, appears) and
  the user's question; the system message contains the "answer only from the
  results / do not invent" instruction.
- **Local-only guard:** an `openai`-backed stub without `allow_remote` →
  `RemoteEngineRefused`; with `allow_remote=True` it constructs.
- **History cap:** pass more than `max_history_turns` → only the most recent
  `max_history_turns` appear in the request, newest preserved.
- **Immutability:** `answer()` does not mutate the passed `DiagnosticResult`
  (it's frozen; assert equality before/after).

The model's *behavioral* grounding ("says it can't see raw lines rather than
inventing them") is validated empirically like the calibration, not in unit tests —
note this in the README.

---

## Task B — chat panel in the Streamlit shell (`ui/app.py`)

A panel rendered **after** the results, only when a `DiagnosticResult` exists in
`session_state`.

- A text input + send button below the rendered result.
- On send: build `FollowupChat(engine)` from the **current model selection** (same
  local engine the run used), call `answer(result, question, followup_history)`,
  then append `ChatTurn("user", question)` and `ChatTurn("assistant", reply)` to a
  **separate** `session_state` key (`followup_history`). Render the history.
- **Run-gating, same discipline as the run button:** a chat submit triggers exactly
  one engine call (the answer), **never** a re-run of diagnostics. The
  `DiagnosticResult` in `session_state` is untouched; only `followup_history` grows.
- Wrap the answer call in `st.spinner`. Surface an engine error inline.
- Clear the chat history when a new diagnostics run starts (the old conversation is
  about the old result).

---

## Non-goals (the bright line, restated as rules)
- No fetching, collecting, running commands, or any system access from a chat turn.
- No mutating the `DiagnosticResult`, re-running diagnostics, or changing the verdict
  or any severity. The chat explains; it does not adjudicate.
- No structured output / `json_schema` — free-text Q&A only.
- No cloud engine on the default path (findings carry IPs/usernames; stay local).
- No tool/command catalog, no sandbox interaction — that is Phase 3, separate and gated.

## Optional, note as future (do not build now)
When the model answers "that's not in the current results" (raw log lines, uncollected
state), that is a signal for a future Phase 3 catalog entry — the user just named a
fetch they want. Capturing those unanswerable questions would make a clean Phase 3
requirements log, but it's a later nicety, not part of this build.

## Acceptance criteria
1. Task A unit tests pass with no model and no network (stub engine).
2. `answer()` is grounded (context carries the result), read-only (no mutation), and
   local-only by default (remote refused without `allow_remote`).
3. History is capped at `max_history_turns`; the summary-plus-history prompt stays
   bounded (compaction applied).
4. The UI chat submit makes one engine call and never re-runs diagnostics; the
   result is unchanged; history clears on a new run.
5. The local-only guard is a single shared implementation used by both
   `LogInterpreter` and `FollowupChat` (no duplicated divergent copy).
6. Lint/type checks clean against the repo config.
```
