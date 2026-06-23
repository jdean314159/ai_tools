# mail_lib — Email Triage Tool: Scoping Note

**Status:** Scoping note, NOT a spec. No implementation authorized yet.
**Goal:** A daily-use tool that reads email, produces a prioritized morning digest,
filters low-value mail, and feeds activity memory into `engram`. The forcing function
for `ai_tools` improvements; the first tool built to be used rather than to demonstrate
a capability.
**Governing constraints:**
- Local-first, read-only access to Thunderbird data. LLM suggestions are advisory; no
  automated deletion or archiving until a rule has been manually confirmed.
- **PRIVACY — HARD RULE:** During development and at all times, only the LOCAL LLM
  (Ollama/llama.cpp on the RTX 3090 workstation) may read actual email content. Neither
  Claude nor Codex is ever given access to real email data — not messages, not subjects,
  not sender names, not any content from the live Gloda database or mbox files. All
  development and testing by Codex and Claude uses SYNTHETIC FIXTURE DATA only (a
  small SQLite file with fake messages in the confirmed Gloda schema + a synthetic mbox
  file with fake messages, both committed to the repo). The real data path is exercised
  exclusively by the maintainer running the tool locally. This rule has no exceptions.

---

## Gloda schema (fully confirmed from live db)

`messages` table top-level columns: `id`, `folderID`, `messageKey`, `conversationID`,
`date`, `headerMessageID`, `deleted`, `jsonAttributes`, `notability`.

`jsonAttributes` stores integer-keyed attribute values. Attribute ID → name mapping
(confirmed from `attributeDefinitions` table):

| id | name | use |
|---|---|---|
| 43 | from | sender identity |
| 44 | to | recipient(s) |
| 45 | cc | cc recipients |
| 46 | bcc | bcc recipients |
| 47 | date | message date (redundant with top-level) |
| 48 | headerMessageID | message ID |
| 52 | involves | contact relationships |
| 53 | recipients | all recipients |
| 54 | fromMe | sent by the account owner |
| 55 | toMe | addressed to the account owner |
| 56 | mailing-list | mailing list membership |
| 57 | tag | Thunderbird tags |
| 58 | star | starred flag |
| 59 | read | read flag |
| 60 | repliedTo | replied flag |
| 61 | forwarded | forwarded flag |
| 32 | subjectMatches | full-text search only (NOT the subject text) |
| 38 | bodyMatches | full-text search only (NOT the body text) |

**Critical finding:** subject and body text are NOT stored as retrievable values in
Gloda. `subjectMatches` and `bodyMatches` are search-index attributes for querying,
not for retrieval. Subject line and body text live in the **mbox files** only.

**Ingestion is therefore a two-step join:**
1. Query Gloda for metadata (sender, recipients, flags, thread ID, folder, date,
   `messageKey`).
2. Use `messageKey` (byte offset into the mbox file) to read subject and body from
   the mbox file via Python's `mailbox` module.

This is well-supported: Python's `mailbox.mbox` reads Thunderbird mbox natively, and
`messageKey` is the byte offset for direct access. Read-only; never write to mbox.

---

## Accounts (confirmed)

Four IMAP accounts: `imap.gmail.com`, `imap.gmail-1.com`, `imap.gmail-2.com`,
`outlook.office365.com`. Multi-account enumeration is in scope from day one.
mbox files live under:
`~/.thunderbird/6svxxg9o.default-release/ImapMail/<account-server>/<FolderName>`

---

## What exists (do not rebuild)

- **`llm_engines`** — local inference via Ollama/llama.cpp; `qwen3:8b` for summarization
  and structured extraction; `TurboQuantEngine` for extended context on long threads.
- **`engram`** — activity memory; email is an ingestion source alongside other work.
  `observe()` with `source="email"`, dedup threshold 0.92, existing four-layer store.
- **`rag_lib`** — retrieval against prior messages and project context; RAGAS harness
  for evaluating quality (also the citation-verifier trigger).
- **`llm_inspector`** — useful later for debugging triage decisions; not MVP.
- **`agent_lib`** — not needed for MVP; no multi-agent loop in a daily digest.

---

## What is new (narrow, one module each)

**1. Thunderbird reader** (`mail_lib/thunderbird.py`)
- Locate profile at `~/.thunderbird/6svxxg9o.default-release/`.
- Enumerate accounts and folders from `folderTree.json`.
- Query Gloda read-only (WAL mode, `SQLITE_BUSY` retry) for message metadata,
  decoding `jsonAttributes` with the confirmed attribute-ID map above.
- For each message: read subject and body from the mbox file at the `messageKey`
  byte offset using `mailbox.mbox`. Read-only; never modify mbox.
- **Development:** all code developed and tested against:
  - `tests/fixtures/mail_lib/gloda_fixture.sqlite` — fake messages in confirmed schema.
  - `tests/fixtures/mail_lib/fixture.mbox` — synthetic mbox with fake messages.
  Neither fixture contains any real email data.

**2. Message indexer** (`mail_lib/indexer.py`)
- Own SQLite at `~/.local/share/mail_lib/index.db`.
- Tracks processed `headerMessageID`s, priority labels, rule history, engram state.
- Incremental: only processes messages newer than last run timestamp.
- Never modifies Thunderbird storage.

**3. Triage pipeline** (`mail_lib/triage.py`)
- Rules layer first (no model call):
  - Sender/domain rules: mailing lists, newsletters, receipts, known-important senders.
  - Subject patterns: notifications, calendar invites, tracking numbers.
  - Flags from Gloda: `read` (59), `repliedTo` (60), `mailing-list` (56).
  - Thread state: already-replied threads drop in priority.
- Model layer second (local LLM only — privacy constraint):
  - Summarization and classification via `llm_engines` → Ollama/llama.cpp only.
  - Structured JSON output: `{priority: urgent|normal|low|ignore, reason: str,
    action_needed: bool, deadline: date|null}`.
- Priority tiers: `urgent`, `normal`, `low`, `ignore` (suggested — human confirms).

**4. Activity extractor** (`mail_lib/extractor.py`)
- Structured extraction from `urgent`/`normal` messages. Local LLM only.
- Output: `{people: [], projects: [], commitments: [], appointments: [], decisions: []}`.
- Each item → `engram.observe()` with source metadata (headerMessageID, date, sender).
- Human approval required before any item becomes a durable engram memory.

**5. Digest report** (`mail_lib/digest.py`)
- CLI output for MVP.
- Sections: Urgent, Normal, Suggested ignores, Activity memory candidates, Open loops.

---

## What is explicitly deferred

- Automated archiving, deletion, or IMAP folder moves. Advisory only until rules confirmed.
- Thunderbird extension / UI integration. External tool first.
- Cross-account thread correlation. Enumerate all accounts; correlate later.
- Attachment handling. Subject/body only for MVP.
- Streamlit dashboard. CLI first.

---

## Forcing-function value

Every failure maps to a concrete `ai_tools` gap felt immediately by the maintainer:
- Misclassified message → triage rule or prompt gap.
- Extraction losing context → `engram` ingestion gap.
- Source not traceable → citation verifier trigger (KEEP-DORMANT).
- "What did I commit to?" miss → gap analysis trigger.

---

## First sprint

1. **Build fixtures** (Codex): `gloda_fixture.sqlite` + `fixture.mbox` with fake
   messages in confirmed schema. This is what all Codex/Claude development uses.
2. **`thunderbird.py`** (Codex against fixture; maintainer validates against real Gloda):
   Gloda metadata query + mbox body read via `messageKey` offset.
3. **`indexer.py`** (Codex): SQLite tracking, incremental processing.
4. **Rules-layer triage** (Codex): no model calls, output prioritized message list.
   **→ First real run: maintainer only, against real Thunderbird data. No output
   shared with Codex or Claude.**
5. **Model layer** (local LLM, maintainer runs): summarization and classification.
6. **`engram` ingestion** (advisory mode): extracted activity items, human approval.

---

## Open questions (all resolved)

- Profile location ✓ `~/.thunderbird/6svxxg9o.default-release/`
- Account count ✓ 4 accounts (gmail ×3, outlook ×1)
- Gloda schema ✓ confirmed — no subject/body columns; numeric-keyed jsonAttributes
- Attribute ID map ✓ confirmed — see table above
- Body text in Gloda? ✓ NO — subject + body require mbox read via messageKey offset
- mbox approach ✓ Python `mailbox.mbox`, read-only, messageKey as byte offset

No open design questions remain. The scoping note is complete.

---

## Where this lives in ai_tools

Script-first: `scripts/mail_triage.py` importing from `mail_lib/`. Promote to a proper
`mail_lib` package with its own `pyproject.toml` only when a second use case forces it.
