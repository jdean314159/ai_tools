# SPEC-MAIL-01 — `mail_lib`: Deterministic Personal-Rule Layer (Script-First)

**Status:** Implemented and maintainer-live-validated, **revision 5**. The live-validation follow-up
sets `SELFMAIL_LINK_MAX_PROSE_CHARS = 40`, with no required subject-tag convention. Validation:
`46 passed` for the MAIL-00/01 suite; `56 passed` for the combined
mail/import-provenance/public-API gate; Ruff and the fixture CLI checks pass; the
no-model/no-network grep is empty. Real mail and rule content remain private and are not recorded.
**Authority:** This spec implements Sprint 1 of `mail_lib_system_parameters.md` ("Deterministic
personal-rule engine") and answers the forcing result recorded in `mail_lib_status_v0.1.md`
("hand-coded heuristics cannot know the maintainer's priorities"). On scope, the system-parameters
note and the scoping note win; on the post-live-run rule order, `mail_lib_status_v0.1.md` is
authoritative and this spec must not contradict it.
**Covers:** A file-backed, deterministic personal-rule layer that runs **after** built-in
`triage_message` and reclassifies messages its rules match; a strict rule-file validator; one
**built-in** `triage.py` change graduating the self-mail floor so link-bearing self-mail (saved
articles) surfaces at `normal` instead of `low` (§6); and one small **`thunderbird.py`** reader change
preserving HTML `href` URLs so the self-mail link detector works on HTML mail (§6.3). Fixture-only
tests throughout.
**Out of scope (each needs its own forcing result and thin follow-on spec):** behavioral
instrumentation, model classification, summarization, `engram` writes, `rag_lib` retrieval,
drafting, UI, package promotion, network access.
**Depends on:** Python stdlib only (`tomllib`, `re` only for the documented internal
matchers — **not** user-supplied regex, `pathlib`, `dataclasses`). No `llm_engines`, `engram`, or
`rag_lib`.
**Mode:** Deterministic end to end. Testable with no model present.

---

## 0. PRIVACY — HARD RULE (carried verbatim authority from the scoping note; state first)

**Only the local LLM on the maintainer's workstation may ever read real email content. Neither
Codex nor Claude is given access to real email data. All development and testing by Codex and Claude
uses SYNTHETIC FIXTURE DATA only. This rule has no exceptions.**

Operationally for this spec:
- The rule-file *format* and the *validator* are developed against committed synthetic fixtures and
  synthetic rule files. No real sender address, domain, or subject string appears in any committed
  test, fixture, log, or example.
- The maintainer's actual personal-rule file (which names real senders/domains they care about) is
  **the maintainer's alone**, lives outside the repo at the runtime path (§4), and is never shared
  back to Codex or Claude. The repo ships only synthetic example rules.
- The layer is **advisory and read-only**, exactly as v0: it reclassifies a priority label and the
  one built-in self-mail change (§6) likewise only adjusts a label. Nothing here sends, deletes,
  archives, moves, or touches Thunderbird storage.

## 1. SECURITY INVARIANT (aligns with ADR-017 / ADR-020 / SPEC-EXEC-00)

The rule file is **data, not code**. It is loaded with the stdlib data-only parser `tomllib`;
it is never `eval`'d, never `exec`'d, never imported as a module, and never unpickled. This is the
direct application of ADR-020's data-only-loading invariant to a new untrusted input surface. A
malformed rule file fails closed (§5): a load or validation error means **no personal rules are
applied** and built-in triage stands unchanged — it never crashes the digest and never silently
applies a partial ruleset.

User-supplied **regex is explicitly excluded** (§2). Subject matching is plain case-insensitive
substring containment. This removes a ReDoS / footgun surface and keeps the specificity metric (§3)
statically computable.

---

## 2. The rule model (decision: sender/domain + subject-substring only)

A personal rule targets mail using **only** these predicates. A rule MUST carry at least one;
predicates within a rule are **ANDed** (all present predicates must match).

| predicate | matches against | match semantics |
|---|---|---|
| `sender` | `MailMessage.sender` (full address) | exact, case-insensitive, after `.strip()` |
| `domain` | the part of `MailMessage.sender` after the last `@` | exact, case-insensitive |
| `subject` | `MailMessage.subject` | case-insensitive **substring** containment |

No regex. No folder/header/account predicates (deferred — if a real run needs `List-Id` or
per-account rules, that is a MAIL-01.x follow-on with its own forcing result). `sender` and `subject`
map onto fields the v0 reader already populates (`thunderbird.py` `MailMessage`: `sender`,
`subject`); `domain` is derived from `sender` (substring after the last `@`). **No reader change is
required for rule matching.** (The §6 self-mail feature *does* require a small reader change for HTML
links — see §6.3 — but that is independent of the rule predicates here.)

**`sender` and `domain` MUST NOT both appear in one rule.** An exact `sender` already implies its
`domain`, so combining them is logically redundant — and worse, it inflates specificity: a
`{sender, domain}` rule would score `(2, 5)` and beat a genuinely narrower `{sender, subject}` rule
at `(2, 4)`, promoting a broad identity match over a targeted one. Forbidding the pair (a validation
error, §2.1) removes the anomaly and caps predicate count at **2**: the only legal multi-predicate
shapes are `{sender, subject}` and `{domain, subject}`.

Each rule also carries:
- `priority` — one of `urgent | normal | low | ignore` (the existing `Priority` enum; the personal
  layer introduces no new tier).
- `note` — free-text, display-only, surfaced in the digest reason. Never drives logic.

### 2.1 Rule-file schema and validation (complete; every violation is a hard error)

The validator enforces this exactly. Any violation rejects the **entire** file (§5), never a single
rule.

**Top-level structure.**
- The file MUST parse as a TOML table whose only recognized key is `rule`, an **array of tables**
  (`[[rule]]`). A file with a top-level `rule` that is not an array-of-tables (e.g. a scalar or a
  single table) is an error.
- **Unknown top-level keys are an error** (not ignored) — a typo'd section name must fail loudly
  rather than silently disable rules.
- An **empty ruleset is valid**: a file present but containing zero `[[rule]]` entries (or `rule = []`)
  loads successfully and applies no personal rules (equivalent to absent, but not an error — it lets
  the maintainer keep a commented-out file).

**Per-rule keys.** Recognized keys are exactly `sender`, `domain`, `subject`, `priority`, `note`.
Any other key in a rule table is an error.

**Per-rule value types and shapes** (every row is an error if violated):
- `sender`, `domain`, `subject`: if present, MUST be a **TOML string** that is **non-empty after
  `.strip()`**. A non-string (integer, array, boolean, float), or an empty/whitespace-only string,
  is an error. (An empty `subject` would substring-match every message; forbidden.)
- `domain`: additionally MUST NOT contain `@` (it is a bare domain, not an address).
- `sender` and `domain` MUST NOT both be present in the same rule (§2; redundant and
  specificity-distorting) — an error.
- At least **one** of `sender`/`domain`/`subject` MUST be present and valid — **zero predicates** is
  an error.
- `priority`: **required**, MUST be a string equal to one of `urgent`/`normal`/`low`/`ignore`. Any
  other value, a non-string, or a missing `priority` is an error.
- `note`: **optional**, MUST be a string if present. An **empty-or-whitespace `note` is treated as
  omitted** (not an error), falling back to the generated default below — a blank note carries no
  information, so equating it with absent is least surprising. If omitted/blank, the digest reason
  defaults to `"Matched personal rule #<n>."` (one-based, §3.3). `note` never drives logic.

The validator produces a single result object: either `ok` with the compiled, ordered rule list (each
rule carrying its precomputed predicate set, specificity tuple §3.2, and one-based index), or `error`
with a list of human-readable messages naming the offending rule index and key. There is no partial
success.

### 2.2 Example rule file (synthetic — ships in fixtures)

```toml
# tests/fixtures/mail_lib/personal_rules.toml — SYNTHETIC. No real data.
[[rule]]
sender = "alerts@example-fixture.test"
priority = "urgent"
note = "fixture: preferred automated alert I actually read"

[[rule]]
domain = "fixture-arxiv.test"
subject = "cs.LG"
priority = "normal"
note = "fixture: domain + subject, more specific than either alone"

[[rule]]
subject = "fixture-newsletter-i-want"
priority = "normal"
note = "fixture: rescue a newsletter the built-in IGNORE rule would bury"
```

---

## 3. Precedence (decision: most-specific wins, later file entry breaks ties)

### 3.1 Where the layer runs

The personal layer runs **once per message, after** `triage_message` returns its `TriageResult`. It
selects **at most one** matching rule (§3.3) and, if one is selected, **replaces** the priority with
that rule's `priority`, appends a `personal:<idx>` token to `matched_rules`, and sets the reason to
the rule's `note`. If no rule matches, the built-in `TriageResult` passes through unchanged.
`triage_message`'s **rule-evaluation pipeline is not modified** by the personal layer — the personal
layer is a separate function consuming its output. (The one built-in edit this spec makes, §6.2's
graduated self-mail floor, lives inside `triage_message` itself and is independent of the personal
layer; the two are specified separately.)

### 3.2 The specificity metric (statically computable)

Each rule's specificity is a tuple compared lexicographically, **higher wins**:

1. **predicate count** — number of predicates present (1 or 2; §2 forbids the redundant
   `sender`+`domain` pair, so the only 2-predicate shapes are `{sender, subject}` and
   `{domain, subject}`).
2. **predicate-type weight** — sum of per-predicate weights: `sender = 3`, `domain = 2`,
   `subject = 1`. (Exact sender is strictly more specific than a domain, which is more specific than
   a subject substring.)

Worked: `{sender}` → `(1, 3)`. `{domain}` → `(1, 2)`. `{subject}` → `(1, 1)`.
`{sender, subject}` → `(2, 4)`. `{domain, subject}` → `(2, 3)`. So any 2-predicate rule beats any
1-predicate rule; among 2-predicate rules `{sender, subject}` beats `{domain, subject}`; among
singles `{sender}` beats `{domain}` beats `{subject}`. The validator computes and prints this for
every rule from the file alone — the maintainer predicts the outcome without running mail.

### 3.3 Selection among multiple matches

Among all rules that match a message:
1. Compute each match's specificity tuple (§3.2).
2. Take the **maximum**.
3. If exactly one rule holds the maximum, it is selected.
4. If two or more rules **tie** at the maximum specificity (possible only with same predicate count
   **and** same type-weight — e.g. two different `subject` substrings both matching, or two
   different `sender` rules, which should not co-match but is defended anyway), the **latest in
   file order** is selected. This permits the append-only MAIL-02 editor to override an earlier
   rule without rewriting hand-authored TOML. File order is the sole, deterministic tiebreaker.

The persisted/displayed token is `personal:<idx>` where `<idx>` is the rule's **one-based** position
in file order (matching the `note` default and validator output).

The validator warns (not errors) only for rules that are statically **certain or likely** to
collide: two rules with **identical predicate values** (exact duplicates), or two `subject`-only
rules where one's substring contains the other's (a guaranteed co-match whenever the longer matches).
It does **not** warn for every same-signature pair — distinct exact `sender` rules cannot co-match,
and unrelated `subject` substrings usually will not, so blanket signature warnings would be noise on
a normal file. Anything beyond these static-certainty cases needs real data to judge (out of bounds),
so it is left silent rather than warned. There is no `--strict-rules` flag in this sprint.

---

## 4. Runtime wiring, file location, and exit semantics

### 4.1 Rule-file path

- **Default path:** `${XDG_CONFIG_HOME:-$HOME/.config}/mail_lib/personal_rules.toml`. Honor
  `$XDG_CONFIG_HOME` when set and non-empty; fall back to `$HOME/.config` otherwise. (The earlier
  draft's hardcoded `~/.config` was inaccurate to call "XDG"; this is genuine XDG resolution.) The
  maintainer's real rules live here, outside the repo.
- **Override:** `--rules <path>` on `scripts/mail_triage.py` supplies an explicit path.

### 4.2 Missing-file semantics (implicit default vs explicit `--rules` differ)

| situation | outcome |
|---|---|
| no `--rules` given, default path **absent** | silent no-op, personal layer disabled, **exit 0** (expected first-run state) |
| no `--rules` given, default path **present** | load + validate it (§2.1); fail-closed on error (§5) |
| `--rules PATH` given, `PATH` **absent** | **error before reading mail**: diagnostic to **stderr**, **nonzero exit**, no profile or index access — an explicitly named file that does not exist is a user mistake, not a default-absent no-op |
| `--rules PATH` given, `PATH` **present** | load + validate it; fail-closed on error (§5) |

### 4.3 CLI surface and exit codes

- **`--rules <path>`** — as above.
- **`--validate-rules`** — load and validate the configured rule file (default path or `--rules`),
  print each rule with its one-based index, predicate set, computed specificity (§3.2), and any
  warnings (§3.3), then exit. Exit **nonzero** on any validation error, **0** on success. In this
  mode the tool **never accesses the Thunderbird profile or the index** — it does not read mail.
- **`--profile` becomes conditionally required:** it is required for a normal triage run but **not**
  required (and not consulted) under `--validate-rules`. The argument parser must allow
  `--validate-rules` to run with no `--profile`. (v0 made `--profile` unconditionally required;
  this spec relaxes it for validation mode only.)
- **Exit-status and persistence contract for a normal run:** if a present rule file is unreadable,
  malformed, or invalid (§5), the tool still renders the built-in digest to **stdout**, writes one
  diagnostic to **stderr**, returns **nonzero**, and **MUST NOT call `MailIndex.record_results`**.
  The fallback digest preserves availability, but a degraded run is index-read-only: a temporary
  configuration error must not overwrite previously persisted personal classifications with
  built-in priorities. An explicitly named missing `--rules` path exits before reading mail (§4.2).
  A valid run (rules applied, an empty valid ruleset, or no implicit-default file present) may
  persist its effective results and exits **0**.

### 4.4 Application placement (personal results precede BOTH persist and render)

The v0 pipeline is `triage_messages` → `MailIndex.record_results` → `render_digest`
(`scripts/mail_triage.py`). For a valid configuration, replace the parallel-sequence step with one
per-message expression: for each `message`, call `triage_message(message)` and immediately pass that
same message and result to `apply_to_message`; collect those return values as `effective_results`.
There is no separate built-in-results list and no `zip`, so truncation, reordering, and cross-message
pairing are impossible in the normal pipeline. Pass `effective_results` to **both**
`record_results` and `render_digest`. Persisting built-in priorities while displaying personal ones
(or vice versa) is a defect — the index and digest must agree.

For an invalid present rule file, `triage_messages(messages)` may produce the fallback built-in
results for `render_digest`, but those results MUST NOT be persisted (§4.3). An explicitly missing
`--rules` path exits before this pipeline begins.

### 4.5 Loading

Read the rule file once at startup, validate (§2.1/§5), and build the ordered compiled rule list
(predicate sets + specificity tuples + one-based indices precomputed). For a valid configuration,
apply each message's personal rule immediately after its built-in `triage_message` call and before
the two consumers (§4.4).

---

## 5. Failure model (fail closed, never partial)

| condition | outcome |
|---|---|
| default path absent (no `--rules`) | no-op; built-in triage unchanged; **exit 0** (normal first-run) |
| explicit `--rules` path absent | **error before reading mail**: stderr diagnostic; **nonzero exit**; no profile or index access (§4.2) |
| file unreadable / TOML parse error | **error**: apply **zero** personal rules; render built-in digest to stdout; one stderr diagnostic; **nonzero exit**; **do not write the index** |
| any schema/type violation (§2.1) in any rule | **error**: the **entire** ruleset is rejected (no partial application); same fallback as above |
| `--validate-rules` with any error | print errors; **nonzero exit**; never touch profile or index (§4.3) |
| empty ruleset (file present, zero rules) | valid; no personal rules applied; **exit 0** |
| valid file, no rule matches a message | message passes through with built-in `TriageResult` unchanged |

Rationale for whole-file rejection over skip-bad-rule: a silently-dropped rule is the lossy-failure
class the maintainer has repeatedly flagged as the architectural risk. Better to apply none and say
so than to apply a subset the maintainer believes is complete. (Matches the deterministic-gate,
no-silent-loss posture of ADR-016 / the curation findings.)

---

## 6. The self-mail floor becomes graduated (built-in), with an unrestricted personal override

### 6.1 The problem v0's flat floor created

v0's self-mail rule (`5e95695`) is sticky-last and demotes **all** self-mail to `low`. That fix was
correct for one population — platform-transfer mail the maintainer moves between accounts and does
not read — but self-mail is **two populations with opposite value**. The maintainer also emails
themselves **links to articles** seen on a phone to read later on the workstation. Both are sent
*from* and *to* the maintainer, so no identity predicate (`sender`/`domain`) can separate them; the
only distinguishing signal is the **body** (a stash carries a URL and little else). A flat `low`
floor therefore **silently buries** the article-stash mail — the same lossy-failure class flagged
elsewhere in this repo as the architectural risk. The fix is to make the floor distinguish the two
shapes deterministically.

### 6.2 Built-in: bare-link self-mail demotes to `normal`, not `low`

This is a **change to the built-in self-mail rule in `triage_message`**, not part of the personal
layer (the personal layer is still pure post-processing per §3.1). The self-mail branch becomes:

- self-mail **AND** body is **bare-link-shaped** (§6.3) → `Priority.NORMAL`, reason
  `"Self-addressed mail carrying a link (likely a saved article)."`, rule token
  `self-mail:link`.
- self-mail **AND** not bare-link-shaped → `Priority.LOW` (unchanged `5e95695` behavior), rule token
  `self-mail`.

Linkless transfer mail keeps the hard `low` floor. Article-stash mail surfaces at `normal` with **no
tag to remember and no rule to write** — which matters because phone-stashing is a low-effort
gesture; requiring a magic subject would defeat its purpose.

### 6.3 The bare-link detector (deterministic, testable)

A body is **bare-link-shaped** iff **both**:
1. it contains **≥1** `http(s)://` URL (matched by an internal, fixed URL regex — not user-supplied);
   **and**
2. after removing all matched URLs, the remaining **non-whitespace** character count is **≤**
   `SELFMAIL_LINK_MAX_PROSE_CHARS`.

`SELFMAIL_LINK_MAX_PROSE_CHARS` is a named module constant beside `URGENT_MAX_AGE_DAYS` /
`CALENDAR_MAX_AGE_DAYS` (one tunable place; same pattern as the v0 gates). Default: a deliberately
narrow allowance (spec value **40**) so a pasted URL plus a very short note still counts as a stash,
while substantive prose does not.

**Reader change (required, implemented in the working tree):** stash mail shared from a phone is
frequently HTML, with the article as an `<a href="…">` anchor. The v0 `_html_to_text` stripped all
tags including the `href`, so the URL was lost and the detector would see only the anchor text — the
feature would miss the HTML majority of exactly the mail it targets. `thunderbird.py` `_html_to_text`
now extracts each `href`, **`html.unescape`s it** (so an entity-encoded query string like
`?a=1&amp;b=2` is restored to `?a=1&b=2` rather than corrupting the URL), then keeps it only if it
begins with `http://`/`https://` — decoding before the scheme check also correctly excludes
entity-encoded `mailto:`/`tel:`. Surviving URLs are appended to the visible text so links persist in
`MailMessage.body`. This is the **one** reader change in this spec; it also benefits any downstream
consumer needing URLs from HTML mail. The detector itself is then a pure string op on `message.body`.

Edge cases the detector must handle: empty body → not bare-link (no URL); plain-text body with a bare
URL and little prose → bare-link; **HTML body with an `href` link and little visible text** →
bare-link (the appended href supplies the URL, the short anchor text stays under threshold); body
with a URL **and** several sentences of prose → not bare-link (over threshold) → stays `low`;
multiple URLs with near-zero prose → bare-link.

### 6.4 Personal override: unrestricted (decision)

The earlier identity-predicate restriction is **dropped**. Any personal rule — including a
`subject`-only rule — may promote (or demote) a self-mail message, at either floor tier (`low` or
the new `normal`). Rationale: the distinguishing signal for a wanted stash is content, which is
exactly what a `subject` predicate targets (e.g. the maintainer stashes with a subject tag like
`!read` and writes `subject = "!read"` → `urgent`). The transfer-mail re-promotion collision is real
but **avoidable by habit** — the maintainer controls both the stash subject and the rule — and §6.2
already means the common stash case works at `normal` with **no rule at all**. The personal layer is
only needed to push a stash *above* `normal` or to handle a stash the bare-link detector misses
(prose-heavy note around the link).

Mechanically: the personal layer receives the built-in `TriageResult` (whose priority is now `low`
**or** `normal` for self-mail per §6.2). It applies §3.3 selection with **no self-mail filtering** —
every matching rule is eligible. The only self-mail-specific logic now lives in the **built-in**
(§6.2/§6.3); the personal layer treats a self-mail `TriageResult` like any other.

---

## 7. Must be built (does not exist yet) — implementation contract

Per `AGENTS.md` spec policy, the machinery this spec requires that the codebase lacks. New code lives
in a new module `mail_lib/personal_rules.py` plus edits to two existing files.

**New: `mail_lib/personal_rules.py`**
- `@dataclass(frozen=True) PersonalRule` — fields: `index: int` (one-based), `sender: str | None`,
  `domain: str | None`, `subject: str | None`, `priority: Priority`, `note: str | None`; plus a
  precomputed `specificity: tuple[int, int]` (§3.2). All string predicates stored already
  `.strip().lower()`'d for case-insensitive matching.
- `load_personal_rules(path: Path) -> RuleLoadResult` — parse with `tomllib`, run full §2.1
  validation, return a result object. `RuleLoadResult` is a small frozen dataclass:
  `ok: bool`, `rules: tuple[PersonalRule, ...]`, `errors: tuple[str, ...]`, `warnings: tuple[str, ...]`.
  Never raises on malformed content — errors are returned, not thrown (fail-closed at the call site).
- `match_rule(rule: PersonalRule, message: MailMessage) -> bool` — ANDed predicate match (§2).
- `apply_to_message(result: TriageResult, message: MailMessage, rules: Sequence[PersonalRule]) -> TriageResult`
  — **the sole application primitive**: takes one message and the result produced for it, first
  verifies `result.header_message_id == message.header_message_id`, and raises `ValueError` on a
  mismatch. It then runs §3.3 selection (most-specific, latest-file-entry tiebreak) over `rules` and returns
  a new `TriageResult` with replaced `priority`, `personal:<idx>` appended to `matched_rules`, and
  `reason` set to the rule `note` or generated default. If no rule matches, it returns `result`
  unchanged. Pure; no I/O. There is **no batch wrapper accepting parallel sequences or pre-paired
  tuples**; the CLI constructs each result and applies this primitive in one per-message loop (§4.4).
- `format_validation_report(result: RuleLoadResult) -> str` — the `--validate-rules` human output
  (per-rule index/predicates/specificity + warnings/errors).

**Edit: `mail_lib/triage.py`**
- Add `SELFMAIL_LINK_MAX_PROSE_CHARS = 40` and a module URL regex.
- Add `_is_bare_link(body: str) -> bool` (§6.3).
- Modify the self-mail branch of `triage_message` to the graduated floor (§6.2): `self-mail:link` →
  `NORMAL` when `_is_bare_link(message.body)`, else `self-mail` → `LOW`. **`triage_message`'s
  signature and `TriageResult`'s shape are unchanged**; `triage_messages` is unchanged. The personal
  layer is a separate function (above), not a new argument to `triage_message`.

**Edit: `scripts/mail_triage.py`**
- Add `--rules` and `--validate-rules`; make `--profile` conditionally required (§4.3).
- Implement the missing-file semantics table (§4.2) and the exit-status contract (§4.3).
- For valid rules, build `effective_results` in one per-message loop by calling
  `apply_to_message(triage_message(message), message, rules)`; pass that list to **both**
  `record_results` and `render_digest` (§4.4).
- For invalid rules, render the built-in fallback digest but skip `record_results`; for an explicit
  missing `--rules` path, exit before reading the profile (§4.2–§4.4).

**Reuse (cited, exists):** `Priority`, `TriageResult`, `triage_message`, `triage_messages`
(`mail_lib/triage.py`, exported via `mail_lib/__init__.py`); `MailMessage` with `body`, `sender`,
`subject` fields (`mail_lib/thunderbird.py:62`); `MailIndex.record_results` and `render_digest`
(`scripts/mail_triage.py:26,31`); `_html_to_text` href preservation + entity decode
(`mail_lib/thunderbird.py`, implemented in the working tree this spec).

**Verified (read end to end):** `MailIndex.record_results` (`mail_lib/indexer.py:67`) stores
`result.priority.value` directly and does **not** re-run triage, so passing `effective_results` to it
(§4.4) is sufficient — `record_results` itself needs no change. It also stores `result.reason` and
`",".join(result.matched_rules)`, so the personal layer's `personal:<idx>` token and rule note are
persisted automatically.

---

## 8. Tests (fixture-only; no model; no real data)

All against synthetic fixtures and synthetic rule files. Required cases:

**Matching and precedence**
1. **Absent default file** → no-op, built-in result unchanged, exit 0.
2. **Sender exact match** promotes/demotes to the rule's tier; reason carries the note;
   `matched_rules` gains `personal:<idx>` (one-based).
3. **Domain match** behaves like sender at lower specificity; `domain` derived from `sender`.
4. **Subject substring** match, case-insensitive.
5. **AND semantics** — a `{domain, subject}` rule matches only when **both** hold; fails when only
   one does.
6. **Redundant predicate pair rejected** — a `{sender, domain}` rule and a `{sender, domain, subject}`
   rule are **validation errors** (§2/§2.1); the only legal 2-predicate shapes are `{sender, subject}`
   and `{domain, subject}`, each matching only when both predicates hold.
7. **Specificity ordering** — a message matching both `{subject}` and `{domain, subject}` resolves to
   the latter; matching `{sender}` and `{domain}` resolves to `{sender}`.
8. **File-order tiebreak** — two same-signature rules both matching → latest (higher one-based
   index) wins.
9. **Default `note`** — a matching rule with no `note` yields reason `"Matched personal rule #<n>."`.

**Self-mail graduated floor (built-in) + HTML reader change**
10. **Bare-link self-mail (plain text) → `normal`** — body is a URL plus ≤40 non-URL non-whitespace
    chars → `normal`, token `self-mail:link`, **no personal rule present**.
11. **Bare-link self-mail (HTML `href`) → `normal`** — self-mail whose HTML body has the URL only in
    an `<a href>` (short anchor text) is detected as bare-link after the §6.3 reader change. **This
    is the case the pre-change reader silently missed; it must be a distinct fixture.**
12. **Linkless / prose-heavy self-mail → `low`** — no URL, and URL-with-prose-over-threshold, both
    stay `low` with token `self-mail` (`5e95695` preserved).
13. **Bare-link detector edges** — empty body → not bare-link; `mailto:`/`tel:` href (plain **and**
    entity-encoded, e.g. `&#109;ailto:`) → not a link (excluded); multiple URLs + near-zero prose →
    bare-link; threshold boundary at `SELFMAIL_LINK_MAX_PROSE_CHARS` exactly and ±1.
13a. **HTML-entity URL decode (reader regression, required)** — an `href` containing `&amp;` (e.g.
    `?a=1&amp;b=2`) is preserved **decoded** (`?a=1&b=2`) in `MailMessage.body`, not corrupted. Direct
    unit test on `_html_to_text`.
14. **Self-mail personal override (unrestricted)** — a `subject`-only rule promotes a self-mail
    message (at either floor) to the rule's tier; confirms no self-mail filtering in the personal
    layer.

**Validation (every §2.1 violation; whole-file rejection)**
15. **Type/shape errors rejected** — for each: `priority` missing; `priority` not in the enum;
    `priority` a non-string; a predicate that is an integer/array/boolean; an empty-or-whitespace
    predicate string; `@` in `domain`; **`sender` and `domain` both present**; zero predicates; an
    unknown per-rule key; an unknown top-level key; top-level `rule` not an array-of-tables. Each
    rejects the **entire** file, built-in triage stands, one stderr diagnostic, nonzero exit, no
    crash.
15a. **Empty `note` = omitted** — a rule with `note = ""` (or whitespace) is valid and uses the
    generated default reason, not an error.
16. **Empty ruleset valid** — file with zero `[[rule]]` (or `rule = []`) loads, applies nothing,
    exit 0.
17. **Tie warnings narrow** — exact-duplicate rules and nested `subject`-substring rules warn; a file
    of distinct `sender` rules produces **no** warnings.

**CLI / runtime semantics**
18. **Explicit `--rules` missing** → stderr diagnostic, nonzero exit, and no profile/index access
    (distinct from case 1).
19. **Invalid rules, normal run** → built-in digest on **stdout**, diagnostic on **stderr**, nonzero
    exit; seed the index first and assert its stored priority and run timestamp remain unchanged.
20. **`--validate-rules` without `--profile`** → runs, prints report, never accesses profile/index;
    nonzero exit iff errors present.
21. **Application placement** — effective (personal-applied) results reach **both** `record_results`
    and `render_digest`: assert the persisted priority and the rendered priority for a rule-affected
    message are identical and equal to the rule's tier.
22. **Built-in passthrough** — a valid file with no matching rule leaves every built-in result
    byte-identical (including the graduated self-mail tiers).
23. **Message/result identity guard** — calling `apply_to_message` with different
    `header_message_id` values raises `ValueError`; the normal CLI path constructs and applies each
    result in one loop and contains no `zip`/parallel-list alignment.

Implemented validation: the additive MAIL-00/01 suite passes (`46 passed`); the combined
mail/import-provenance/public-API gate passes (`56 passed`). The §6.3 reader change has both direct
HTML-href/entity-decoding coverage and end-to-end self-mail-floor coverage.

---

## 9. Forcing-function check (why this matures the library)

This sprint exercises **no** `ai_tools` library by design — it is deliberate deterministic
groundwork (system-parameters note, item 1). Its value is twofold: (a) it buys back the maintainer's
morning now by rescuing the wanted mail v0 buried; (b) it becomes the surface the maintainer reacts
to and corrects, which is the labeled substrate Sprint 2 (behavioral instrumentation) will capture.
The deterministic-floor-then-personal-override shape is itself the propose-then-verify primitive
validated on a fourth domain (after diagnostics, curation, netflow) — repeated necessity is the
admission filter for promoting it, but that promotion is **not** part of this spec.

---

## 10. Decisions resolved for implementation

1. **Self-mail logic location — RESOLVED.** All self-mail logic lives in the built-in
   `triage_message` (graduated floor, §6.2/§6.3). The personal layer needs no `self_mail` boolean;
   `TriageResult`'s shape is unchanged.
2. **Config format — RESOLVED to TOML.** `tomllib` is stdlib at the repo's existing 3.11 floor
   (`StrEnum` already forces it); no new dependency, satisfies the data-only-loading invariant (§1).
3. **Strict-tie flag — RESOLVED: not in this sprint.** Warnings are narrowed to static-certainty
   collisions (§3.3); no `--strict-rules`.
4. **Bare-link prose threshold — RESOLVED to 40 after live validation.** The maintainer selected
   `SELFMAIL_LINK_MAX_PROSE_CHARS = 40`. One constant and boundary tests keep later tuning safe.
5. **Subject-tag promotion convention — RESOLVED as optional.** No tag is required. §6.2 surfaces
   stashes at `normal`; the maintainer may later add a personal subject rule to promote selected
   stashes above `normal` without changing this specification.

(Addressed from Codex reviews and not re-opened: complete strict-validation schema §2.1; runtime
exit/stream semantics §4.2–4.3; application-placement-before-persist-and-render §4.4 with
`record_results` verified non-re-deriving §7; degraded runs prohibited from mutating the index
§4.3–§5; explicit missing rule paths exit before profile/index access §4.2; `--profile` conditional
§4.3; XDG path §4.1; the
redundant `sender`+`domain` pair prohibited so specificity stays monotone §2/§3.2; per-message apply
contract with an ID guard and no batch/parallel-sequence API §7/§4.4; HTML-href reader change **with
entity decoding** §6.3; empty-`note`-as-omitted §2.1; `tomllib`-only §1/§22; narrowed tie warnings §3.3; the
"Must be built" contract §7.)
