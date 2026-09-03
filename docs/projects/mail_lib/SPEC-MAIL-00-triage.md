# SPEC-MAIL-00 — `mail_lib` v0: Thunderbird Reader + Rules-Layer Triage (Script-First)

**Status:** Implemented. Supersedes the earlier package/UI-first draft of this file, which
contradicted `mail_lib_scoping_note.md` and is withdrawn.
**Authority:** This spec implements `mail_lib_scoping_note.md` (the scoping note). The note is
authoritative on **scope and intent** (script-first, fixtures-first, CLI v0, no model, no UI, no
package promotion, privacy rule). This spec is authoritative on **technical mechanism where it
records a maintainer-confirmed correction validated against real data** — specifically, the
Gloda↔mbox join is **bracket-stripped `Message-ID`** (validated, 5,101 messages), NOT the note's
`messageKey` byte-offset claim (disproven). The scoping note carries a Correction/Supersession block
recording this. On any *other* disagreement, the note wins — report the conflict rather than
diverging.
**Covers:** First-sprint v0 only: synthetic fixtures, the Thunderbird Gloda→mbox reader, the
incremental indexer, and the **rules-layer** triage with a CLI digest. **No model calls. No
package promotion. No Streamlit. No engram writes.**
**Depends on:** Python stdlib `mailbox`, `email`, `sqlite3`, `json`, `pathlib`. No `llm_engines`,
`engram`, or `rag_lib` usage in v0 (they enter at v1+, see "Deferred to later stages").
**Mode:** Deterministic end to end. Everything in v0 is testable with no model present.
**Discipline:** READ the scoping note and the cited tree paths before writing. The note's confirmed
Gloda facts are authoritative; do not re-derive or generalize them.

---

## 0. PRIVACY — HARD RULE (verbatim authority from the scoping note; state first)

**Only the local LLM on the maintainer's workstation may ever read real email content. Neither
Codex nor Claude is given access to real email data — not messages, not subjects, not sender names,
not any content from the live Gloda database or mbox files. All development and testing by Codex and
Claude uses SYNTHETIC FIXTURE DATA only. This rule has no exceptions.**

Operationally for this spec:
- Every module is developed and tested **exclusively** against the committed synthetic fixtures
  (Stage 1). No code, test, log, or example in this commit may contain, print, or embed real mail.
- The real Thunderbird path is exercised **only** by the maintainer, locally, and its output is
  never shared back to Codex or Claude (note, First Sprint step 4).
- The reader is **read-only** against Gloda and mbox. It never writes, moves, or deletes Thunderbird
  storage (note, "Governing constraints" + module 1).

## 1. SECURITY INVARIANT (carried from the prior draft; aligns with ADR-017 / ADR-020 / SPEC-EXEC-00)

**INV-SEC: Email body content is untrusted attacker-controlled input. The pipeline interprets it and
never acts on it.** In v0 there is no model and no action surface at all, so INV-SEC is trivially
satisfied — but it is stated now because v1 (model layer) and later (engram, archiving) must preserve
it: model output is advisory, no automated deletion/archiving until a rule is manually confirmed
(note, "deferred"), and any instruction-like text in a body is data to classify, never a command.

---

## 2. HEAD grounding

Citations below are confirmed against live HEAD **`1d7a057`** (`fix(agent_lib): fail closed on
unpolicied command execution`) on `codex-cleanup-pass`, verified directly from the repo's git
history. Line numbers are current as of that commit; re-confirm only if HEAD has advanced before
implementation.

## 3. Confirmed reuse surface (verified at HEAD `1d7a057`)

v0 uses **stdlib only** — the items below are cited for v1+ accuracy and to prevent rebuilding, not
because v0 calls them.

- **Engine (v1, not v0).** `llm_engines` exposes `get_engine(backend, model)` → `ChatModel`, with
  `ChatMessage` (`contracts/engine.py:222`) and `GenerationRequest` (`contracts/engine.py:250`),
  both `BaseModel` subclasses. **Thinking suppression is engine/backend config (`think=False` for
  Ollama/llama.cpp), NOT a `GenerationRequest` field** — the prior draft was wrong on this; Codex's
  correction is adopted.
- **Structured output (v1, not v0).** `llm_engines/src/llm_engines/utils/structured_output.py`:
  `StructuredOutputHandler.parse_with_details(...)` (line 131) returns `ParseResult`, with
  `ParseResult.data` already typed via `model_class.model_validate_json(...)` (line 150), and
  `_strip_think_blocks` (line 94) handling Qwen `<think>` output. Reuse this in v1; do not hand-roll
  a parser.
- **Memory (later stage, not v0).** `engram` ingestion is `observe(observation: MemoryObservation)`
  (`engram/src/engram/contracts.py:90`), where `MemoryObservation` (line 43) has fields
  `role, text, session_id, embedding?, surprise?, metadata`. **Email provenance goes in
  `metadata`** (e.g. `{"source": "email", "headerMessageID": ..., "date": ..., "sender": ...}`) —
  there is **no `source=` kwarg** on `observe`; the note's `source="email"` shorthand maps to the
  `metadata` dict. Correct this when the engram stage is built.

## 4. Must be built in v0 (new; one module each, per the note)

Script-first layout (note, "Where this lives"):
- `mail_lib/` as an **importable directory** (not a promoted package — no `pyproject.toml` of its
  own yet), imported by `scripts/mail_triage.py`. Promotion to a package waits for a second use case.
- `mail_lib/thunderbird.py`, `mail_lib/indexer.py`, `mail_lib/triage.py` (rules layer only in v0),
  `mail_lib/digest.py`.
- `scripts/mail_triage.py` — the CLI entry point wiring reader → indexer → rules-triage → digest.
- `tests/fixtures/mail_lib/gloda_fixture.sqlite` and `tests/fixtures/mail_lib/fixture.mbox` —
  synthetic, committed.
- `tests/` for each module, fixture-only.

---

## Stage 1 — Synthetic fixtures (FIRST; everything depends on these)

Per First Sprint step 1. Build the fixtures before any reader code, because they define the schema
the reader targets and they are the only data Codex/Claude may use.

**Confirmed `jsonAttributes` encoding (from one redacted real row, maintainer-supplied).** A real
value is:
`{"43":12,"44":[2],"45":[],"46":[],"50":false,"51":[],"52":[12,2],"53":[2],"57":[],"58":false,"59":true,"60":false,"61":false}`
This establishes three facts the fixture MUST reproduce:
1. **Values are contact-ID references, not inline strings.** `"43":12` means `from` → contact #12;
   `"44":[2]` means `to` → [contact #2]; `"52":[12,2]` is `involves` → both. The human-readable
   address/name strings are NOT in `jsonAttributes` — they live in a separate Gloda contacts table
   keyed by these integer IDs. (This corrects the note, which assumed addresses were inline.)
2. **Flags are JSON booleans, not 0/1 integers.** `"59":true` (read), `"58":false` (star),
   `"60":false` (repliedTo), `"61":false` (forwarded), `"50":false`. The fixture encodes bools; the
   reader parses bools.
3. **IDs `50` and `51` are real but unmapped in the note.** Include them as fields; their semantics
   can be confirmed from `attributeDefinitions` later. Single-valued keys (`43`) are scalars;
   multi-valued keys (`44,45,46,52,53,57`) are arrays.

Ingestion is therefore a **multi-step join**, not the note's two: Gloda `messages` → resolve contact
IDs through `contacts` (name) **and** `identities` (address) → map disk mbox ↔ Gloda folder by account
identity (NOT dir name) → match each mbox message to its Gloda row by **bracket-stripped `Message-ID`**
(NOT `messageKey` offset). Folders absent from Gloda are read mbox-only.

- `gloda_fixture.sqlite`: reproduce the **confirmed Gloda schema** (full DDL supplied by maintainer
  via `.schema`). The fixture needs these tables, with **fake** data throughout:
  - `messages (id, folderID, messageKey, conversationID, date, headerMessageID, deleted,
    jsonAttributes, notability)` — `jsonAttributes` encoded exactly as the confirmed real blob
    (contact-ID refs + boolean flags).
  - `contacts (id, directoryUUID, contactUUID, popularity, frecency, name, jsonAttributes)` — maps
    the integer contact IDs used in `jsonAttributes` (12, 2, ...) to **fake display names**. Holds
    the name, NOT the address.
  - `identities (id, contactID, kind, value, description, relay)` — maps `contactID` → **address**,
    where `value` is the email (and `kind` distinguishes email/IM/etc.). A contact may have several
    identity rows. This is where sender/recipient **addresses** actually live.
  - `folderLocations (id, folderURI, dirtyStatus, name, indexingPriority)` — maps `messages.folderID`
    → folder URI/name. Lets the reader resolve a message's folder **in-db**, without `folderTree.json`.
  - `attributeDefinitions (id, attributeType, extensionName, name, parameter)` — the **source of
    truth** for the attribute-ID→name map (43=from, 44=to, 58=star, 59=read, 60=repliedTo, etc., and
    the names for 50/51). The reader reads the map from here rather than hard-coding it.
  - (Optional for v0) `messageAttributes (conversationID, messageID, attributeID, value)` — the
    relational mirror of `jsonAttributes`, indexed for attribute queries. v0 parses `jsonAttributes`
    per message and does not need this; include only if the indexer adds attribute-filtered queries.
  - Populate with **fake** messages spanning every rules-layer branch (Stage 4): a mailing-list
    message, a newsletter, an already-replied thread (`60:true`), a starred important sender
    (`58:true`), and a plain personal message.
- `fixture.mbox`: a synthetic mbox whose messages carry **`Message-ID` headers that match (after
  bracket-stripping) the `headerMessageID` values** in the SQLite fixture — this is the join under
  test (NOT `messageKey` offsets, which are disproven; see Stage 2). Each message has a fake subject
  and body, with fake `From:`/`To:` headers consistent with the `contacts`+`identities` rows. The
  fixture stores `headerMessageID` without angle brackets and the mbox `Message-ID` with them, so
  tests exercise the strip-and-match the reader performs. Include at least one folder with Gloda rows
  (indexed) and one mbox-only folder with no matching Gloda rows (unindexed case).
- **Folder layout in the fixture** mirrors the confirmed real structure (see Stage 2): a
  profile-root `folderTree.json` with `open.all` URIs for **fake** accounts/folders
  (`imap://account-1@.../[Gmail]/All Mail`, a nested user folder, etc.), plus the on-disk
  storage — extensionless mbox files with `.msf` siblings and an `[Gmail].sbd/` subfolder dir, with
  `All Mail` as canonical store and `INBOX`/`Important`/`Starred`/user-folders as overlapping
  signal-folders. The fixture must include at least one nested user folder and at least two accounts
  to exercise multi-account enumeration and nested-path handling.
- **Hard constraint:** every value in every fixture is invented. No real sender, subject, body,
  address, or contact appears. A test asserts the fixtures load, the contact-ID resolution returns
  the fake identities, and the **Message-ID join resolves** (bracket-stripped `headerMessageID` ↔
  mbox `Message-ID`) — proving self-consistency.

**Tests:** load `gloda_fixture.sqlite`, decode one `jsonAttributes` blob, **resolve `43`/`44`
through `contacts`+`identities` to fake identities**, **match the fixture's bracket-stripped
`headerMessageID` to the mbox message's `Message-ID`** and assert the expected fake subject/body come
from the matched mbox message. Assert flags parse as bools (`59:true` → `read=True`). Assert an
mbox-only message (no Gloda row) yields with reduced enrichment.

## Stage 2 — Thunderbird reader (`mail_lib/thunderbird.py`)

Per module 1. **Multi-step** join (Gloda metadata → contact resolution via contacts+identities →
folder resolution via folderLocations → mbox body), read-only:

- **Account/folder enumeration — `folderTree.json` at the PROFILE ROOT.** The file exists, but at
  the profile root (alongside `global-messages-db.sqlite`), **not** inside `ImapMail/` — which is why
  the `ImapMail/<server>/` directory listing showed only mbox + `.msf` and no JSON. Its `open.all`
  array lists folder URIs of the form `imap://<user>@<server>/<folderpath>` (plus a
  `mailbox://...Local%20Folders` entry). Parse each URI for **account (user@server)** and
  **folder path**; this is the canonical account→server→folder registry. **Do not hard-code an
  account count** — the note's "four accounts" is stale (the real registry shows five gmail accounts
  plus an outlook/`nps.edu` account plus Local Folders). Enumerate whatever the URIs contain.
- **Body storage — extensionless mbox files (NO `.mbox` suffix) under `ImapMail/<server>/`.**
  Enumeration gives identity; bodies still come from the mbox files. **Thunderbird mbox files have no
  file extension** — they are named `INBOX`, `All Mail`, `Sent Mail` (not `INBOX.mbox`); a search for
  `*.mbox` finds nothing, which is expected. Identify a mailbox as: **a regular file** (not a
  directory) that has a **same-named `.msf` sibling** (e.g. `INBOX` + `INBOX.msf`). The `.msf`
  presence is the reliable marker; do not rely on extension. Subfolders live in a `<name>.sbd/`
  directory (e.g. `[Gmail].sbd/` with `All Mail`, `Sent Mail`, `Important`, `Starred`, `Drafts`,
  `Spam`, `Trash`) — `.sbd` dirs are themselves extensionless, so the file-not-directory check
  matters. **Do not parse `.msf`** (Mork-format index); it only marks a sibling as a mail folder.
  Read bodies with `mailbox.mbox` (single file per folder; confirmed mbox format, not Maildir).
  User-defined folders nest arbitrarily (`Family/Meghan`, `Coding sites/Codefight`) — handle via
  `.sbd` recursion. Profile root is parameterized/injectable so tests point at the fixture.
- **NAMESPACE-MISMATCH TRAP — disk directory name ≠ Gloda folderURI host (PROVEN).** The on-disk
  storage directory and the Gloda `folderURI` are **different namespaces** and must not be matched by
  string. Thunderbird disambiguates a second account on the same server by appending a suffix to the
  *directory* name (`ImapMail/imap.gmail-3.com/`), but the **URI keeps the plain host**
  (`imap://account3%40gmail.com@imap.gmail.com/...`) — the `-3` suffix appears on disk only. Mapping a
  disk mbox to its Gloda folder by `folderURI LIKE '%<dirname>%'` therefore **fails silently** (it was
  verified to return nothing for the suffixed account). The reader must map disk mbox → Gloda folder
  via the **account identity** (user@server parsed from the URI), reconciling it to the disk directory
  through `folderTree.json`, **never** by directory-name string match. Likewise `messages.folderID` is
  a Gloda-internal integer with no relation to disk order: folder 39 was confirmed to be one account's
  All Mail (5,101 msgs), unrelated to a different account's same-named mbox (4 msgs). Resolve folders
  through `folderLocations.folderURI`, never by assuming `folderID` order matches disk.
- **UNINDEXED-FOLDER CASE — mbox on disk, absent from Gloda (PROVEN).** Gloda indexing is lazy/async;
  a folder can exist on disk with **no Gloda record at all** (verified: a new account's mbox had 4
  messages on disk but zero `folderLocations` rows — `LIKE '%account3%'` returned nothing). The reader
  MUST handle "mbox present, no Gloda metadata": fall back to reading the mbox directly with reduced
  enrichment (raw message headers/body, no contacts resolution, no Gloda flags) rather than skipping
  the folder or erroring. The fixture MUST include both an indexed folder and an mbox-only folder so
  this path is tested.
- **Gmail folder semantics — source vs. signal.** Gmail maps server-side labels to overlapping
  folders; a message appears in several (`[Gmail]/All Mail`, `Important`, `Starred`, `INBOX`, ...).
  Treat **`All Mail`** as the canonical message source of truth. Treat membership in **`Important`**,
  **`Starred`**, `INBOX`, **and user-defined folders** (`Family`, `Coding sites`, `Health`, ...) as
  **triage signals** carrying user intent — not as separate messages. Deduplicate by
  `headerMessageID`; record which folders (standard + user) a message appears in.
- **Gloda metadata query.** Open the Gloda SQLite **read-only**, in **WAL mode with `SQLITE_BUSY`
  retry**. Query `messages` and decode `jsonAttributes` per the confirmed encoding (contact-ID refs,
  boolean flags) into a `MessageMetadata` dataclass
  (`headerMessageID, message_key, folder_id, conversation_id, date, sender_id, recipient_ids[],
  flags{read,star,replied,forwarded,...}`).
- **Contact resolution — two hops.** Resolve `sender_id`/`recipient_ids` from `jsonAttributes`
  through **`contacts`** (id → display name) and **`identities`** (contactID → address `value`,
  possibly multiple rows; pick the email-`kind` identity). The note's single "contacts table" was
  incomplete: name and address are in separate tables. Senders are NOT readable from `jsonAttributes`
  alone.
- **Folder resolution — in-db via `folderLocations`.** A message's folder comes from
  `messages.folderID` joined to `folderLocations(folderURI, name)` — no `folderTree.json` needed to
  know *which folder a message is in*. (`folderTree.json` remains the account-enumeration registry;
  `folderLocations` is the per-message folder lookup.) Use the resolved folder URI for the
  source-vs-signal determination (All Mail = source; Important/Starred/user-folders = signal).
- **Gloda↔mbox JOIN KEY — CONFIRMED: bracket-stripped `Message-ID` (validated on 5,101 messages).**
  The note's `messageKey`-as-byte-offset claim is **false** for IMAP folders (confirmed `messageKey`
  115/123/176 matched neither mbox byte offsets 0/12245/12964 nor key indices 0/1/2). The join is
  **bracket-stripped `Message-ID`**: Gloda `messages.headerMessageID` (stored WITHOUT angle brackets,
  e.g. `8F21...@host`) matched to the mbox message's `Message-ID` header (stored WITH brackets, e.g.
  `<davR...@host>`); strip `<>` on both sides. **Validated on matched real data** (account2 All Mail):
  Gloda 5,101 ∩ mbox = 5,101 — every Gloda row matched. **The reader matches by `Message-ID`; it never
  seeks by `messageKey`.**
- **DIRECTIONALITY — mbox ⊇ Gloda; iterate the mbox (CONFIRMED).** In the same validation the mbox
  held 5,192 messages vs Gloda's 5,101 — the mbox is the **complete** store; Gloda is an enrichment
  index that **lags** (91 messages were on disk but not yet indexed, *within* an otherwise-indexed
  folder). Therefore the reader's spine is the **mbox**: iterate all mbox messages, attach Gloda
  metadata where the `Message-ID` matches, and yield the unmatched remainder as **mbox-only** (reduced
  enrichment). Do NOT iterate Gloda and look up mbox — that misses the lagging messages. This is the
  per-message form of the unindexed-folder case (which is the whole-folder form of the same lag).
- **Attribute map from `attributeDefinitions`.** Read the attribute-ID→name map from the
  `attributeDefinitions` table rather than hard-coding it; this also yields names for the
  note-unmapped IDs `50`/`51`.
- **Body read — match, do NOT seek by offset.** Read messages from the resolved mbox with
  `mailbox.mbox`, parse each message's `Message-ID`, and match (bracket-stripped) to the Gloda
  `headerMessageID` for that folder to attach metadata. **Do not seek by `messageKey`** (disproven
  above). **Read-only; never modify mbox.** Yield a `Message` combining resolved metadata + subject +
  body + folder-membership signals. For unindexed folders (no Gloda rows), yield mbox-only messages
  with reduced enrichment.
- **Dev/test:** runs against Stage 1 fixtures exclusively. The real path is the maintainer's to
  validate (First Sprint step 2); no real output returns to Codex/Claude.

**Tests:** drive the reader against the fixture profile dir; assert filesystem folder discovery finds
the fixture folders via the mbox+`.msf` pattern and recurses `[Gmail].sbd`; assert a message in both
`All Mail` and `Important`/`Starred` is ingested **once** with signal-folder membership recorded;
assert contact-ID resolution yields fake identities; assert subject/body come from the matched mbox
message via bracket-stripped `Message-ID`; assert flags parse as bools. Assert the Gloda connection
is read-only (a write attempt raises). Confirm `subjectMatches`(32)/`bodyMatches`(38) are **not**
used as text sources — subject and body come from mbox only.

## Stage 3 — Indexer (`mail_lib/indexer.py`)

Per module 2. Own SQLite at `~/.local/share/mail_lib/index.db` (path injectable for tests):

- Track processed `headerMessageID`s, assigned priority labels, rule history, and a last-run
  timestamp. Incremental: only process messages newer than the last run.
- **Never modifies Thunderbird storage** (separate db entirely).

**Tests:** seed the index, run twice over the fixture set, assert the second run processes only new
messages (inject a clock/timestamp). Round-trip a priority label.

## Stage 4 — Rules-layer triage (`mail_lib/triage.py`) — NO MODEL

Per module 3, **rules layer only**. This is the v0 endpoint and the first real forcing run.

- Pure deterministic classification producing a priority in the confirmed tier set
  `urgent | normal | low | ignore` plus a structured reason, with **no LLM call**:
  - **Sender/domain rules:** mailing lists, newsletters, receipts, known-important senders (matched
    on the **resolved** contact address from Stage 2, since the sender is a contact-ID, not inline).
  - **Subject patterns:** notifications, calendar invites, tracking numbers.
  - **Gloda flags (booleans):** `read`(59), `repliedTo`(60), `mailing-list`(56), `star`(58),
    `forwarded`(61) — all parsed as JSON bools per the confirmed encoding.
  - **Gmail folder-membership signals:** presence in `Important` or `Starred` (recorded by Stage 2)
    raises priority; this is distinct from the Gloda `star` flag and is Gmail-specific.
  - **Thread state:** already-replied threads (`repliedTo:true`) drop in priority.
- Output a `TriageResult(headerMessageID, priority, reason, matched_rules[])`. Priorities are
  **suggestions**; the human confirms (note). No deletion/archiving — advisory only.
- Rule config is data (a small declarative table of sender/domain/subject rules), so adding a rule
  is editing data, not code — matches the "rule gap felt immediately" forcing-function intent.

**Tests:** each fixture message hits a deterministic, asserted tier via a named rule; an
already-replied thread (`repliedTo:true`) demotes; a mailing-list flag routes to `low`/`ignore`; a
message in the `Important` signal-folder is raised. No engine is imported.

## Stage 5 — Digest (`mail_lib/digest.py`) + CLI (`scripts/mail_triage.py`)

Per module 5, **CLI only**:

- `digest.py` renders sections: **Urgent, Normal, Suggested ignores, Activity-memory candidates
  (empty in v0 — extractor is later), Open loops** (already-replied/awaiting threads from rules).
- `scripts/mail_triage.py` wires reader → indexer → rules-triage → digest and prints the digest.
  Against fixtures it prints fake data; the maintainer runs it against real data privately.

**Tests:** the CLI run over fixtures produces a digest with the expected sections and the expected
fake messages in the expected tiers (assert at the `digest.py` function layer; keep `__main__` thin).

---

## Verification (before the commit is complete)

- `python scripts/mail_triage.py --profile tests/fixtures/mail_lib/` (or equivalent fixture flag)
  runs end to end over fixtures and prints a digest. No network, no model.
- `grep -rn "llm_engines\|engram\|rag_lib\|ollama\|requests\|httpx\|smtplib\|imaplib\|subprocess" mail_lib/ scripts/mail_triage.py`
  returns **nothing** — v0 is stdlib-only and model-free.
- A test asserts the Gloda connection is read-only and that no code path writes to mbox or the
  Thunderbird profile.
- A test (or a committed check) asserts the fixtures contain only synthetic data — e.g. all
  addresses use a reserved example domain — as a guard against accidental real-data inclusion.
- Full `mail_lib` tests pass with no engine importable.

## Assumptions to verify (Codex confirms before/while building)

**Resolved by maintainer-supplied real-account inspection (no longer open):**
- **Enumeration source:** `folderTree.json` **exists at the profile root** (not in `ImapMail/`). Its
  `open.all` array holds folder URIs `imap://<user>@<server>/<folderpath>`; parse for account and
  folder path. Use it for account/folder identity; use the mbox+`.msf` files for bodies. (Confirmed
  from redacted `folderTree.json`.) Both the note ("enumerate from folderTree.json") and an earlier
  draft ("no folderTree.json, walk the filesystem") were half-right: the file is the registry, the
  walk is the storage.
- **Account count is not fixed at four.** The real registry shows five gmail accounts + an outlook
  account + Local Folders. Enumerate from the URIs; do not hard-code a count. (Note was stale.)
- **Folders nest arbitrarily and are user-defined** (`Family/Meghan`, `Coding sites/Codefight`) —
  handle nested paths; treat user folder names as triage signals.
- Folder discovery on disk: mbox files are **extensionless** (named `INBOX`, not `INBOX.mbox`),
  identified by a same-named `.msf` sibling, with `.sbd` recursion for subfolders. Storage is mbox
  (single file per folder), not Maildir. (Confirmed from listing + extension search.)
- `jsonAttributes` encodes **contact-ID references** (`"43":12`) and **JSON booleans**
  (`"59":true`), not inline strings or 0/1 integers. (Confirmed from one redacted real row.)
- **Full Gloda schema confirmed** (maintainer `.schema` dump). Contact resolution is **two hops**:
  `jsonAttributes` ID → `contacts(id→name)` → `identities(contactID→address value)`. Per-message
  folder is in-db via `messages.folderID → folderLocations(folderURI,name)`. Attribute-ID→name map
  lives in `attributeDefinitions`. `messagesText` is an fts3 search index (`body,subject,author,
  recipients`), confirming subject/body are search-tokenized there and the retrievable body is
  **mbox-only**. `messageAttributes` is the relational mirror of `jsonAttributes` (not needed for v0).
- **`messageKey` is NOT a byte offset (DISPROVEN); join key CONFIRMED.** Real `messageKey`
  (115,123,176) matched neither mbox offsets nor key indices. The Gloda↔mbox join is **bracket-stripped
  `Message-ID`**, validated on account2 All Mail: Gloda 5,101 ∩ mbox = 5,101 (every Gloda row matched).
  Reader matches, never seeks.
- **DIRECTIONALITY CONFIRMED — mbox ⊇ Gloda.** Same validation: mbox 5,192 vs Gloda 5,101 (91
  on-disk-but-unindexed). Reader iterates the mbox as the spine, attaches Gloda metadata on
  `Message-ID` match, yields unmatched as mbox-only. Never iterate Gloda→lookup-mbox.
- **NAMESPACE MISMATCH (PROVEN).** Disk dir name (`imap.gmail-3.com`) ≠ Gloda URI host
  (`imap.gmail.com`); the disambiguation suffix is disk-only. `folderID` is Gloda-internal, unrelated
  to disk order. Map disk↔Gloda by account identity in the URI, never by dir-name string or `folderID`
  order. (Verified: `LIKE '%gmail-3%'` and `LIKE '%account3%'` both returned nothing.)
- **UNINDEXED FOLDERS EXIST (PROVEN).** A new account's folder had 4 messages on disk but no Gloda
  record. Reader must handle mbox-present/Gloda-absent with reduced enrichment; fixture includes both.

**Still open — confirm against the real account (maintainer only, no content to Codex/Claude):**
- **Attribute IDs `50`/`51` names** — resolvable with `SELECT id,name FROM attributeDefinitions;`
  (definitions, not mail content; safe to read). Not blocking; fixture carries them as fields.

**All structural unknowns for v0 are now resolved.** The Message-ID join key, the directionality
(mbox-as-spine), the namespace-mapping rule, the contact/identity/folder schema, and the storage
format are all confirmed against real data. v0 is fully grounded; Codex can build fixtures-first.

## Deferred to later stages (explicitly NOT in v0 — do not build)

- **Model layer** (note module 3, model half): local-LLM summarization/classification with the
  structured schema `{priority, reason, action_needed, deadline}`. Becomes **v1**, gated on the
  Stage 4 rules layer concretely failing to classify a real message (build-on-failure). Uses the
  `llm_engines` + `StructuredOutputHandler` surface in section 3, local backend only (privacy).
- **Activity extractor** (note module 4) and **engram ingestion**: `extractor.py` →
  `observe(MemoryObservation(..., metadata={"source":"email", ...}))`, advisory, human-approved.
  A later stage, not v0.
- **Package promotion** (`mail_lib/pyproject.toml`): only when a second use case forces it.
- **Streamlit / Thunderbird-extension UI, automated archiving/deletion/IMAP moves, cross-account
  thread correlation, attachment handling:** all deferred per the note.

## Conflicts resolved against the prior draft (for the record)

- Package-now → **directory imported by a script**, promotion deferred (note wins).
- Generic Maildir/mbox → **Thunderbird Gloda→mbox bracket-stripped `Message-ID` join** (the note's
  `messageKey`-offset claim was disproven on real data; see Stage 2), the actual forcing path.
- Streamlit v0 → **CLI v0** (note wins).
- LLM triage v0 → **rules-layer v0, model deferred to v1**.
- `~/.mail_lib/` SQLite → **`~/.local/share/mail_lib/index.db`** (note's path).
- `observe(source="email")` → **`MemoryObservation(metadata={"source":"email"})`** (real contract).
- `think=False` is engine config, not a request field.
- Privacy hard rule and synthetic-fixture-only constraint carried verbatim.
