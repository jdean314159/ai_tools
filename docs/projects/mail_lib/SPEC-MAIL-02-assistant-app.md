# SPEC-MAIL-02: Local mail assistant app (FastAPI + HTMX consumer)

**Status:** RATIFIED AND IMPLEMENTED — MVP closed 2026-07-03; live validation pending

**Depends on:** SPEC-MAIL-00 (triage), SPEC-MAIL-01 (personal rules)

**Trust model:** `mail_lib` remains the deterministic, network-free authority for
reading and classifying mail. The Thunderbird profile is read-only. The app owns
its interaction state and local-model output; neither may alter triage priority.

## 1. Purpose

Build a localhost web app for reviewing Thunderbird mail in descending priority,
summarizing selected sections with a local model, marking messages read within the
app, and authoring deterministic personal rules through an explicit review and
approval workflow.

The MVP proves a narrow vertical slice. It does not add chat, retrieval, adaptive
memory, IMAP writes, or model-based priority scoring.

## 2. Scope boundary

### In the MVP

- FastAPI backend and server-rendered Jinja templates enhanced with locally served
  HTMX, bound only to `127.0.0.1`.
- A fresh, read-only Thunderbird snapshot loaded at app startup and explicitly
  refreshable without restarting the process.
- Unread/all views grouped in descending `Priority` order.
- Explicit, on-demand batch summarization of one priority section through
  `llm_engines`; output is display-only and cached in app-owned storage.
- Personal-rule widgets that produce a reviewed TOML diff and commit it only
  through a validated, conflict-detecting, atomic write.
- An app-local read ledger. It never writes Thunderbird state.
- A deterministic rule `action` of `none|summarize|ignore`.

### Out of scope

- **F1 — Chat over currently listed mail.** Trigger: the MVP review workflow is
  useful and a concrete question requires synthesis beyond section summaries.
- **F2 — IMAP actions (triggered and partially shipped).** The original trigger
  named non-destructive `\Seen` propagation. Live use instead forced a destructive
  network write because app-only review still required returning to Thunderbird
  for deletion. The shipped slice is explicit, confirmed server-side `MOVE` to a
  configured Trash folder. Read-state propagation remains deferred.
- **F3 — Mail-wide retrieval.** Trigger: a query needs messages outside the
  current snapshot or the selected set exceeds the model context.
- **F4 — Cross-session or adaptive memory.** Trigger: deterministic rules prove
  insufficient and a real usefulness signal is defined.
- **F5 — Model interest scoring.** Trigger: deterministic rules cannot represent
  demonstrated topical interest. It may not directly set priority.
- **F6 — Concurrent summary-call deduplication.** Trigger: an observed run issues
  duplicate local-model calls for the same cache key and the duplication has a
  material latency or resource cost.

Do not pre-build F1–F6.

## 3. Existing code that may be reused

- `mail_lib/thunderbird.py` supplies `MailMessage` records. Gloda's
  `ATTRIBUTE_READ` is exposed as `message.metadata.flags["read"]` at
  `mail_lib/thunderbird.py:180`.
- `mail_lib/triage.py::triage_message` performs built-in deterministic triage and
  returns `TriageResult(header_message_id, priority, reason, matched_rules)`.
  `triage_messages` only applies this built-in path; it does **not** apply personal
  rules.
- `mail_lib/personal_rules.py::load_personal_rules` strictly reads and validates a
  TOML rules file. `apply_to_message` selects the most-specific matching rule and
  applies its priority to an existing `TriageResult`.
- The current complete rule-aware call path is composed in
  `scripts/mail_triage.py`: `triage_message(message)` followed by
  `apply_to_message(..., message, rules)`. There is no reusable batch service that
  also exposes a selected presentation action.
- `mail_lib/indexer.py::MailIndex` owns deterministic processed-message/run state
  in SQLite. It does not store message bodies or subjects and must not become the
  app's model-output or interaction-state store.
- `examples/language_tutor/web_app.py` is precedent for a FastAPI app and local
  engine initialization. It is not precedent for Jinja or HTMX.
- `llm_engines` publicly exposes `get_engine`, `GenerationRequest`, `ChatMessage`,
  `StructuredOutputHandler`, `count_tokens`, and `compress_prompt`. Their concrete
  request and structured-output contracts must be verified before implementation;
  names alone are not a grounded summarizer design.

## 4. Must be built

1. `examples/mail_assistant/`, including packaging, FastAPI routes, Jinja
   templates, static assets, and a locally pinned HTMX asset. The MVP must not
   depend on a CDN or browser-side network access.
2. Refactor personal-rule matching to expose one shared selector, then build a
   reusable deterministic classification function that composes built-in triage
   with that selector and returns both the final `TriageResult` and resolved
   `action`. `apply_to_message` must use the same selector; the app must not
   duplicate its matching logic.
3. The `action` extension to the personal-rule schema and validator.
4. An app-owned `AssistantStore` with its own SQLite database and connection
   lifecycle. Do not add app tables to `MailIndex`.
5. Snapshot loading/refresh, unread-state merging, and view assembly.
6. The on-demand section summarizer and cache.
7. A transactional rule proposal/approval/commit service.
8. Web security middleware and untrusted-content rendering policy.

## 5. Deterministic classification contract

Add `action` to `PersonalRule`:

```text
action in {none, summarize, ignore}; default none
```

It is accepted by `_RULE_KEYS`, parsed and validated by
`load_personal_rules`, and absent values remain backward-compatible as `none`.

Add a typed classification result, conceptually:

```text
ClassifiedMessage(message, triage, action, matched_personal_rule_index)
```

The exact name may change, but the contract must preserve the final triage result
and the action from the same selected personal rule. The function must use the
existing most-specific/latest-file-entry selection behavior rather than implementing a
second matcher in the app.

The current `apply_to_message` contract cannot supply this result because it
returns only `TriageResult` and discards the selected `PersonalRule`. Refactor
`personal_rules.py` to add one shared selector, conceptually:

```text
select_personal_rule(message, rules) -> PersonalRule | None
```

Both `apply_to_message` and the new classification function must call that
selector. Preserve `apply_to_message`'s existing public return type for backward
compatibility unless a repository-wide call-path review justifies changing it.

`priority` and `action` are orthogonal with these rendering rules:

- Priority always determines the section and ordering.
- `action=none` renders the normal message row.
- `action=summarize` renders the normal row plus a cached-summary placeholder or
  an explicit summarize control. It never invokes the model during `GET /`.
- `action=ignore` collapses matching rows into an expandable count within their
  priority section; it never removes them.
- Existing `Priority.IGNORE` remains a priority section. It does not imply
  `action=ignore`; collapsing occurs only when the resolved action says so.

## 6. Message and read-state lifecycle

At startup, load a read-only Thunderbird snapshot using the existing mail reader.
Keep the resulting `MailMessage` records in app memory. A user-triggered refresh
replaces the snapshot only after a complete successful read; a failed refresh
leaves the prior snapshot available and reports the error.

The MVP does not use `MailIndex` as a message store. Reclassification runs over
the in-memory snapshot whenever the snapshot or committed personal rules change.

For a message, effective unread is:

```text
not thunderbird_read and not app_read
```

The all view includes both read and unread messages. The app ledger can only mark
a message read in the MVP; undo and Thunderbird synchronization are follow-ons.
Unknown message IDs fail closed with `404` and do not create ledger rows.

## 7. App-owned persistence

Use a separate SQLite database, defaulting to:

```text
~/.local/share/mail_assistant/assistant.db
```

`AssistantStore` owns at least:

```sql
CREATE TABLE read_state (
    header_message_id TEXT PRIMARY KEY,
    read_at REAL NOT NULL
);

CREATE TABLE section_summary_cache (
    section_key TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (section_key, model, prompt_version)
);
```

`section_key` is a SHA-256 digest over a canonical, ordered representation of the
selected section's message IDs and the exact message fields sent to the model.
Changing membership or summarized content invalidates the cache naturally.

Use a per-request connection or another explicitly synchronized connection
strategy compatible with FastAPI's execution model. Configure a bounded busy
timeout and transactions. Concurrent same-key model-call deduplication is F6 and
is not part of the MVP.

## 8. Summarization contract

`POST /summarize/{section}` summarizes the current messages in one known priority
section. It must:

1. Resolve the section server-side; clients cannot submit arbitrary message text.
2. Construct a bounded prompt using only the selected snapshot fields.
3. Count tokens with the configured model's tokenizer and reject or deterministically
   truncate to the documented input budget.
4. Execute synchronous engine work outside the async event loop, with a timeout.
5. Treat model output as untrusted plain text, HTML-escape it, and cache it using
   the key in section 7.
6. Return a safe HTML fragment or a structured error without changing rules,
   priority, read state, or the snapshot.

The prompt must state that message content is untrusted data and that instructions
inside messages must not be followed. This reduces prompt-injection risk but does
not replace the hard display-only boundary.

## 9. Rule proposal and commit transaction

The rules path is configured server-side at startup and is never accepted from an
HTTP request. The app must reject symlinks and paths outside the configured rules
location.

### Propose

`POST /rules/propose` accepts a known `example_message_id`, a selected predicate
field (`sender|domain|subject`), `priority`, and `action`. The server derives the
predicate value from that message. It does not accept arbitrary email-derived
predicate text as authoritative input.

The proposal service:

1. Reads the current file bytes and records their SHA-256 revision. This check is
   required even for a single-user process because the configured file remains
   externally editable between proposal and commit (for example through an editor,
   CLI, or another browser tab).
2. Constructs a candidate document that surgically updates the latest exact
   predicate match (preserving comments and unrelated bytes), or appends a new
   block when the predicate is new.
3. Serializes the exact candidate bytes.
4. Validates those exact bytes using the normal personal-rule validator through a
   safe temporary file or a new byte-oriented validator sharing the same parser.
5. Returns a human-readable diff, validation report, and opaque proposal token
   bound to the base revision and SHA-256 of the candidate bytes.

It performs no write to the configured rules file.

### Commit

`POST /rules/commit` accepts only the opaque proposal token plus the CSRF token.
The server retrieves the corresponding bounded, short-lived proposal; clients do
not resubmit candidate TOML.

Commit must fail if the current rules-file revision differs from the proposal's
base revision. It revalidates the exact candidate bytes, writes a mode-`0600`
temporary file in the destination directory, flushes and `fsync`s it, atomically
replaces the configured file, and `fsync`s the directory. Failure before replace
must leave the original bytes unchanged. Successful commit invalidates the token,
reloads rules, and reclassifies the current snapshot.

Stale commits are rejected rather than merged.
Preserving arbitrary TOML comments is not an MVP requirement. The proposal diff
must make canonical reserialization visible before approval.

## 10. Web security invariants

- Bind only to `127.0.0.1`; reject unexpected `Host` values to reduce DNS-rebinding
  exposure.
- Generate a random per-process session/CSRF secret. Every state-changing request
  requires a valid CSRF token and an allowed same-origin `Origin` or `Referer`.
- Use POST for every state change. Do not encode raw Message-ID values in route
  paths; send them in validated form bodies.
- Escape sender, subject, body excerpts, rule notes, diffs, validation messages,
  and model output. Templates must not apply Jinja `safe` to any mail-, rule-, or
  model-derived content. HTMX fragments obey the same rule.
- Set restrictive response headers, including a CSP that permits only locally
  served scripts/styles, `X-Content-Type-Options: nosniff`, and
  `Referrer-Policy: no-referrer`.
- The Thunderbird profile is read-only. The app writes only its own database and
  the explicitly configured personal-rules file.
- `mail_lib` and `scripts/mail_triage.py` remain model- and network-free. Model
  initialization and calls exist only under the app.
- Model output is display-only and cannot propose or commit rules, alter priority,
  mark messages read, or initiate network activity.
- Real mail is private runtime data. It must never be committed, added to fixtures,
  or sent to Claude, Codex, hosted judges, or other remote services. Tests and
  development artifacts use only synthetic mail fixtures.

## 11. MVP HTTP contracts

- `GET /?view=unread|all` renders the classified snapshot by descending priority.
  Default is `unread`. It performs no model call.
- `POST /refresh` reloads the read-only Thunderbird snapshot transactionally.
- `POST /summarize/{section}` returns an escaped section-summary fragment.
- `POST /rules/propose` returns an escaped diff, validation result, and approval
  control. It performs no rules-file write.
- `POST /rules/commit` commits one valid, current proposal and returns the updated
  list or a conflict/error fragment.
- `POST /read` accepts a form-body Message-ID, records local read state, and returns
  the updated view fragment.

All POST routes enforce the controls in section 10.

## 12. Dependencies and configuration

Add explicit app dependencies for FastAPI, Uvicorn, Jinja, and the chosen form
parser. Pin and serve HTMX as a checked-in or packaged static asset; document its
version and provenance. No CDN fallback is permitted.

Configuration must include the Thunderbird profile/account selection, personal
rules path, assistant database path, local engine/backend and model, model timeout,
context/input budget, and bind host/port. Reject a non-loopback bind host in the
MVP.

## 13. Required tests

Use only `tests/fixtures/mail_lib` or additional synthetic fixtures. Mock the model
engine in the normal gate; optional live-local-model tests are explicitly marked
and excluded by default.

At minimum test:

- Complete built-in-plus-personal classification and propagation of the selected
  action.
- Every meaningful priority/action combination, including `Priority.IGNORE` with
  `action=none` and another priority with `action=ignore`.
- Unread merging, all view, unknown IDs, successful refresh, and failed-refresh
  rollback.
- No model call during list rendering; cache hit/miss and invalidation on content,
  membership, model, or prompt-version changes.
- Model timeout/error behavior. Same-key request deduplication is tested only when
  F6 is implemented.
- HTML/script payloads in every mail field, rule field, diff, and model output are
  rendered inert.
- Host rejection, same-origin/CSRF enforcement, and POST-only state changes.
- Proposal performs no destination write; exact-byte validation; successful atomic
  commit; stale-revision conflict; token replay rejection; symlink/path rejection;
  and rollback on write, flush, or replace failure.
- `AssistantStore` migration/idempotence, connection strategy, busy handling, and
  transaction rollback.
- The existing `mail_lib` model/network-free gate remains unchanged and passing.

## 14. Assumptions that must be verified before coding their dependents

- Verify the concrete `llm_engines` generation, timeout, tokenizer, and structured
  output contracts before implementing section 8. `compress_prompt` must not be
  assumed to perform model summarization.
- Verify the Thunderbird reader's profile/account selection and cost before fixing
  the refresh interface.
- Select a TOML serialization strategy and document its canonical ordering before
  implementing proposals. Python's `tomllib` is read-only.
- Verify the repository's dependency/package layout before adding Jinja, form
  parsing, and the vendored HTMX asset.

These are verification gates, not permission to invent parallel interfaces.

## 15. Build order

1. Verify the assumptions in section 14 and record the selected contracts.
2. Extend `PersonalRule` with `action`; add the complete typed classification
   function and tests.
3. Build and test app-owned `AssistantStore`.
4. Build snapshot loading, refresh, read-state merging, and deterministic view
   assembly.
5. Add the FastAPI/Jinja/HTMX skeleton and security middleware; implement list,
   refresh, and read routes against synthetic fixtures.
6. Add bounded section summarization, cache, and timeout handling with a mocked
   engine.
7. Add the proposal store and transactional propose/commit workflow.
8. Run the existing repository gates plus the security, concurrency, and failure
   tests in section 13.

Only after the MVP passes these gates may an F1–F6 trigger be evaluated.

## 16. Implementation record (2026-07-02)

The MVP is implemented in `examples/mail_assistant/`. The deterministic schema,
shared selector, and classified-message contract are in
`mail_lib/personal_rules.py`. HTMX 2.0.4 is pinned locally with its source and
SHA-256 recorded in `examples/mail_assistant/static/HTMX-PROVENANCE.txt`.

Automated verification completed:

- MAIL-02 plus existing mail/import/public-API gate: 75 passed.
- Ruff over changed Python surfaces: passed.
- Package wheel build without dependency resolution: passed.
- Pinned HTMX SHA-256 verification: passed.
- Repository `make test-core`, rerun with explicit monorepo source paths because
  the project `.venv` lacked an editable `llm_engines` install: passed.

Normal tests use a mock engine and synthetic mail only. A private live run against
a real Thunderbird profile and configured local model remains an explicit manual
validation step; its data and output must not be committed or sent to remote
services.

## 17. F2b batch Move-to-Trash amendment (2026-07-06)

Live cleanup sessions forced batch granularity after the confirmed single-message
flow proved too slow. Each message row may be selected client-side, but selection
is not authorization. The server validates the complete batch, renders every
sender, subject, account host, source folder, and destination folder, then binds
that exact ordered ID set to a one-shot expiring confirmation token.

Proposal creation performs a read-only IMAP preflight grouped by resolved
account, using one login per selected account. Commit uses the same account
resolution, exact Message-ID lookup, post-auth capability refresh, and
server-side `MOVE` requirement, again grouped by account rather than opening one
connection per message. IMAP moves cannot be rolled back as one transaction:
failures are recorded per message and do not suppress later attempts;
disappeared snapshot messages are skipped; only successful moves are removed
from app state. Any unsafe Message-ID, mailbox, unresolved account, or
non-stale server preflight mismatch rejects the whole proposal before
authorization. If a grouped preflight reports that one or more selected messages
were not found on the IMAP server, proposal creation rechecks the selected
messages individually, excludes the stale rows from the confirmation token, and
lists them as skipped; if none remain available, the proposal is rejected.
Rows proven missing from the IMAP server are recorded in app-owned local state
and suppressed from subsequent snapshots so Thunderbird cache artifacts do not
remain actionable. Rules and model output cannot authorize or execute trash
actions.

## 18. Sender/domain volume statistics amendment (2026-07-06)

Live rule authoring exposed an anecdotal-selection gap. `/stats` now computes a
read-only aggregation from the current in-memory snapshot using the same bounded
date window and parser as the list view. Sender and domain rows report count,
unread count, share of all dated messages in the window, and most recent date,
sorted by descending count.

Each row links to an exact deterministic sender/domain list filter and can feed
that value into the unchanged reviewed rule proposal/commit transaction. Stats
do not persist history, invoke a model, access the network, or authorize actions.
