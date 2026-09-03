# mail_lib — Live-Run Status (v0.1)

**Status:** v0 implemented, committed, and validated against the maintainer's real Thunderbird mail.
Three triage patches applied post-run. This note records what the live run changed and what it taught.
**Successor:** MAIL-01 deterministic personal rules are implemented and maintainer-live-validated;
see `SPEC-MAIL-01-personal-rules.md` and `../../internal/history/SESSION_HANDOFF.md`. Digest traceability
is the next queued thin follow-on. The planning action at the end of this v0.1 record is historical.
**Predecessors:** `mail_lib_scoping_note.md` (scope/intent + corrections), `SPEC-MAIL-00-triage.md`
(the v0 build spec), both authoritative for their domains. This note is the *post-live-run* record.
**Implementation commits:** `9f9125f` (v0), `a80c45c` (self-mail), `2191e09` (star recency),
`c7f2d89` (calendar recency). Current mail_lib tests: `10 passed`; root-adjacent mail/import/public
API gate: `20 passed`.

---

## What v0 shipped

Script-first `mail_lib/` (importable, not yet a package): `thunderbird.py` (reader), `indexer.py`,
`triage.py` (rules layer), `digest.py`, driven by `scripts/mail_triage.py`. Synthetic fixtures only
for Codex/Claude; real data is the maintainer's alone. Spec ratified at `72caded`; implementation
and live-run corrections are listed above, on `codex-cleanup-pass`.

## What the live run produced — three patches

The first real run against the maintainer's mail surfaced one recurring defect class and one
workflow-specific gap. Three patches (each tested, each stacking on the prior):

1. **Self-mail demotion** (`selfmail.patch`). The reader computed `from_me`/`to_me` but `triage.py`
   ignored them. The maintainer routinely emails to/from the same account to move data between
   platforms; that mail was mis-prioritized. Rule added: self-mail (Gloda `from_me`, OR sender in
   recipients — the latter works for unindexed mail without knowing the user's addresses) → `low`,
   and it **wins** over receipt/calendar/star promotions.

2. **Star/folder flood fix** (`starfix_age.patch`). The urgency rule fired on the Gmail `Important`
   and `Starred` *folders*, not just the star flag. Gmail auto-labels most mail `Important`, so the
   rule marked a huge swath of years-old mail URGENT. Fixed to: urgency requires the Gloda **star
   flag** (a deliberate user action), gated to messages within **6 months** (`URGENT_MAX_AGE_DAYS`).
   Folder membership no longer promotes.

3. **Calendar recency gate** (`calendar_age.patch`). The calendar subject rule had no recency bound,
   so years-old "meeting/invitation/appointment" mail showed URGENT. Gated to **1 month**
   (`CALENDAR_MAX_AGE_DAYS`) — calendar mail goes stale faster than starred mail. Older calendar mail
   → `normal`.

**Result:** urgent tier went from floods to **one** message — one the maintainer had actually
starred. The tier now means what it should.

## The durable finding

**Keyword/folder heuristics over a multi-year archive surface *history* as urgency unless
recency-gated.** Both floods (star-folder, calendar) were the same shape: a broad rule with no time
bound matching a deep archive. Any future subject/folder rule needs the same gating.

**The deeper finding:** hand-coded heuristics cannot know the maintainer's priorities. The run buried
mail the maintainer *wanted* (preferred automated notifications, selected publications, and
personal-interest event mail) because the rules saw "automated sender / newsletter-shaped /
digest." No regex tuning fixes this — the signal is personal. **This is the forcing function for
sprint 1 (personal rule engine).**

## Current triage rule order (post-patch, authoritative)

In `triage_message`, priority starts `NORMAL`, then rules apply in this order (later overrides
earlier, with self-mail sticky-last):
1. `gloda:mailing-list` → `low`
2. `subject:newsletter` → `ignore`
3. `subject:receipt-or-tracking` → `low`
4. `subject:calendar` → `urgent` if within 1 month, else `normal`
5. `gloda:starred-recent` → `urgent` if star flag AND within 6 months (suppressed for self-mail)
6. `gloda:replied` → demote (suppressed for self-mail)
7. `self-mail` → `low`, sticky (suppresses 5 and 6)

Constants `URGENT_MAX_AGE_DAYS=183` and `CALENDAR_MAX_AGE_DAYS=31` are tunable in one place.

## Open observations for future runs (not yet defects)

- **Normal is now a catch-all.** With urgent de-flooded, most mail lands `normal`. Sprint 1's
  personal rules are what promote the handful that matter out of that pile.
- **Receipt and newsletter rules are still broad** and ungated — if a future run floods on either,
  the fix is the known move (gate or reclassify), or decide they never warrant their current tier.
- **Cross-account dedup** (by bare Message-ID) merges the same message across the five accounts —
  confirm this matches intent at scale.
- **Open-loops requires Gloda metadata**, so recent unindexed mail (Gloda lags disk) may miss the
  section — watch whether it feels complete.
- **Bcc-to-self** self-mail won't match sender-in-recipients (To won't contain you) and unindexed
  mail lacks `from_me` — a Sent-folder check is the fallback if this case appears.

## Next planning action

Draft and ratify a thin `SPEC-MAIL-01-personal-rules.md` before changing code. It should cover only
the deterministic personal-rule layer: file format, precedence over built-in heuristics, validation,
and fixture-only tests. Behavioral instrumentation, model calls, summarization, `engram`, `rag_lib`,
and UI remain later stages governed by `mail_lib_system_parameters.md`.
