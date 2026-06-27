# SPEC-MAIL-01 — `mail_lib`: Deterministic Personal-Rule Layer (Script-First)

**Status:** Draft. Not ratified. No code until this spec is reviewed and accepted.
**Authority:** This spec implements Sprint 1 of `mail_lib_system_parameters.md` ("Deterministic
personal-rule engine") and answers the forcing result recorded in `mail_lib_status_v0.1.md`
("hand-coded heuristics cannot know the maintainer's priorities"). On scope, the system-parameters
note and the scoping note win; on the post-live-run rule order, `mail_lib_status_v0.1.md` is
authoritative and this spec must not contradict it.
**Covers:** A file-backed, deterministic personal-rule layer that runs **after** built-in
`triage_message` and reclassifies messages its rules match; a strict rule-file validator; and one
**built-in** `triage.py` change — graduating the self-mail floor so link-bearing self-mail (saved
articles) surfaces at `normal` instead of being buried at `low` (§6). Fixture-only tests throughout.
**Out of scope (each needs its own forcing result and thin follow-on spec):** behavioral
instrumentation, model classification, summarization, `engram` writes, `rag_lib` retrieval,
drafting, UI, package promotion, network access.
**Depends on:** Python stdlib only (`tomllib`/`json`, `re` only for the documented internal
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

The rule file is **data, not code**. It is loaded with a data-only parser (`tomllib`, or `json`);
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
per-account rules, that is a MAIL-01.x follow-on with its own forcing result). All three predicates
map onto fields the v0 reader already populates (`thunderbird.py` `MailMessage`: `sender`,
`subject`); **no reader change is required.**

Each rule also carries:
- `priority` — one of `urgent | normal | low | ignore` (the existing `Priority` enum; the personal
  layer introduces no new tier).
- `note` — free-text, display-only, surfaced in the digest reason. Never drives logic.

A rule with an unknown key, a missing `priority`, an invalid `priority` value, zero predicates, or a
`domain` value containing `@` is a **validation error** (§5).

### 2.1 Example rule file (synthetic — ships in fixtures)

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

## 3. Precedence (decision: most-specific wins, file-order breaks ties)

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

1. **predicate count** — number of predicates present (1 or 2; future predicates extend this).
2. **predicate-type weight** — sum of per-predicate weights: `sender = 3`, `domain = 2`,
   `subject = 1`. (Exact sender is strictly more specific than a domain, which is more specific than
   a subject substring.)

Worked: `{sender}` → `(1, 3)`. `{domain}` → `(1, 2)`. `{subject}` → `(1, 1)`.
`{domain, subject}` → `(2, 3)`. So `{domain, subject}` beats any single-predicate rule; `{sender}`
beats `{domain}` beats `{subject}`. The validator can compute and print this for every rule from the
file alone — the maintainer can predict the outcome without running mail.

### 3.3 Selection among multiple matches

Among all rules that match a message:
1. Compute each match's specificity tuple (§3.2).
2. Take the **maximum**.
3. If exactly one rule holds the maximum, it is selected.
4. If two or more rules **tie** at the maximum specificity (possible only with same predicate count
   **and** same type-weight — e.g. two different `subject` substrings both matching, or two
   different `sender` rules, which should not co-match but is defended anyway), the **earliest in
   file order** is selected. File order is the sole, deterministic tiebreaker.

The validator SHOULD warn (not error) when two rules are *capable* of an unresolved-by-specificity
tie on construction (same predicate-type signature) so the maintainer is told file order will decide
— but it cannot prove they ever co-match a real message (that needs real data, which is out of
bounds), so it is a warning, not a failure.

---

## 4. Runtime wiring and file location

- **Rule-file path:** `~/.config/mail_lib/personal_rules.toml` (XDG config; the maintainer's real
  rules live here, outside the repo). Overridable via `--rules <path>` on `scripts/mail_triage.py`.
- **Absent file is normal, not an error:** if the path does not exist, the layer is a no-op and v0
  behavior is unchanged. (A first-time user has no personal rules; that is the expected default, not
  a failure.)
- **Loading:** read once at startup, validate (§5), build an ordered list of compiled rules
  (predicate sets + specificity tuple precomputed). Apply per message in the digest pipeline.
- **CLI:** `scripts/mail_triage.py` gains `--rules <path>` and a `--validate-rules` mode that loads
  and validates the file, prints each rule with its computed specificity and any warnings, and exits
  non-zero on any validation error **without** reading mail.

---

## 5. Failure model (fail closed, never partial)

| condition | outcome |
|---|---|
| rule file absent | no-op; built-in triage unchanged (normal first-run state) |
| file unreadable / parse error | **error**: apply **zero** personal rules, built-in triage stands; emit one diagnostic line; digest still runs |
| any single rule invalid (unknown key, bad/missing `priority`, zero predicates, `@` in `domain`) | **error**: the **entire** ruleset is rejected (no partial application); same fallback as above |
| `--validate-rules` with any error | print errors, exit non-zero, do not read mail |
| valid file, no rule matches a message | message passes through with built-in `TriageResult` unchanged |

Rationale for whole-file rejection over skip-bad-rule: a silently-dropped rule is the lossy-failure
class the maintainer has repeatedly flagged as the architectural risk. Better to apply none and say
so than to apply a subset the maintainer believes is complete. (Matches the deterministic-gate,
no-silent-loss posture of ADR-016 / the curation findings.)

---

## 6. The self-mail floor becomes graduated (built-in), with an unrestricted personal override

### 6.1 The problem v0's flat floor created

v0's self-mail rule (`553c49e`) is sticky-last and demotes **all** self-mail to `low`. That fix was
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
- self-mail **AND** not bare-link-shaped → `Priority.LOW` (unchanged `553c49e` behavior), rule token
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
`CALENDAR_MAX_AGE_DAYS` (one tunable place; same pattern as the v0 gates). Default: a small allowance
(spec value **120**) so a pasted URL plus a short note ("read this", a title fragment, a forwarded
signature line) still counts as a stash, while a real email body with prose does not. Both operations
are pure string ops on `message.body`, which the reader already populates (`thunderbird.py`
`_message_body`, line 328) — **no reader change.**

Edge cases the detector must handle: empty body → not bare-link (no URL); body with a URL **and**
several sentences of prose → not bare-link (over threshold) → stays `low`; multiple URLs with
near-zero prose → bare-link.

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

## 7. Tests (fixture-only; no model; no real data)

All against synthetic fixtures and synthetic rule files. Required cases:

1. **Absent file** → no-op, built-in result unchanged.
2. **Sender exact match** promotes/demotes to the rule's tier; reason carries the note;
   `matched_rules` gains `personal:<idx>`.
3. **Domain match** behaves like sender at lower specificity.
4. **Subject substring** match, case-insensitive.
5. **AND semantics** — a `{domain, subject}` rule matches only when **both** hold; fails when only
   one does.
6. **Specificity ordering** — a message matching both a `{subject}` rule and a `{domain, subject}`
   rule resolves to the latter; a message matching `{sender}` and `{domain}` resolves to `{sender}`.
7. **File-order tiebreak** — two same-signature rules both matching → earliest wins.
8. **Bare-link self-mail → `normal` (built-in)** — self-mail whose body is a URL plus ≤120 non-URL
   non-whitespace chars triages to `normal` with rule token `self-mail:link`, **without any personal
   rule present**.
9. **Linkless / prose-heavy self-mail → `low` (built-in unchanged)** — self-mail with no URL, and
   self-mail with a URL but prose over the threshold, both stay `low` with token `self-mail`
   (`553c49e` preserved).
10. **Bare-link detector edges** — empty body (no URL) → not bare-link; multiple URLs + near-zero
    prose → bare-link; one URL + several sentences → not bare-link. Threshold boundary tested at
    `SELFMAIL_LINK_MAX_PROSE_CHARS` exactly and ±1.
11. **Self-mail personal override (unrestricted)** — a `subject`-only rule promotes a self-mail
    message (at either `low` or `normal` floor) to the rule's tier; confirms no self-mail filtering
    in the personal layer.
12. **Fail-closed: invalid rule** (each invalid-condition row in §5) → whole ruleset rejected,
    built-in triage stands, one diagnostic emitted, no crash.
13. **`--validate-rules`** prints specificities + warnings and exits non-zero on error without
    reading mail.
14. **Built-in passthrough** — a valid file with no matching rule leaves every built-in result
    byte-identical (including the new graduated self-mail tiers).

The existing `mail_lib` gate (currently `10 passed` / `20` combined) must stay green; these are
additive.

---

## 8. Forcing-function check (why this matures the library)

This sprint exercises **no** `ai_tools` library by design — it is deliberate deterministic
groundwork (system-parameters note, item 1). Its value is twofold: (a) it buys back the maintainer's
morning now by rescuing the wanted mail v0 buried; (b) it becomes the surface the maintainer reacts
to and corrects, which is the labeled substrate Sprint 2 (behavioral instrumentation) will capture.
The deterministic-floor-then-personal-override shape is itself the propose-then-verify primitive
validated on a fourth domain (after diagnostics, curation, netflow) — repeated necessity is the
admission filter for promoting it, but that promotion is **not** part of this spec.

---

## 9. Open questions for review (resolve before ratifying)

1. **Self-mail logic location (resolved).** The §6 redesign moves all self-mail-specific logic into
   the **built-in** `triage_message` (the graduated floor, §6.2/§6.3). The personal layer no longer
   needs a `self_mail` boolean and treats a self-mail `TriageResult` like any other — so
   `TriageResult`'s shape is **unchanged** and `_is_self_mail` is not recomputed in the personal
   layer. (This supersedes the earlier draft's threading question.)
2. **Config format — TOML (resolved).** TOML via stdlib `tomllib` (≥3.11). The floor is already
   3.11+: `triage.py` uses `StrEnum` (3.11) and the sibling libs pin `requires-python = ">=3.11"`,
   so `tomllib` needs no new dependency. TOML reads better than JSON for a hand-edited file and adds
   no third-party parser, satisfying the data-only-loading invariant (§1). Confirm only that you are
   content hand-editing TOML; otherwise JSON is a drop-in with the same data-only guarantee.
3. **Should `--validate-rules` warnings (same-signature potential ties) be promotable to errors via
   a strict flag?** Default warn; offer `--strict-rules` later only if a real file accumulates
   confusing ties.
