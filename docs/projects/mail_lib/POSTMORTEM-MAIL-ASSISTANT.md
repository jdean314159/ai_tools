# Mail Assistant Post-Mortem

Date: 2026-07-11

## Summary

The local mail assistant reached a working MVP, but it should not continue as an
active daily-use product. The decisive failure was not the LLM layer. The tool
competed with Thunderbird and Gmail on their strongest surface: daily mail
reading, state, sync, deletion, and trust. The incumbent full client won that
surface.

The experiment was still useful. It produced a deterministic Thunderbird reader,
personal-rule machinery, local snapshot/cache patterns, reviewed file mutation,
section summarization boundaries, and hard-won IMAP safety lessons. Those are
worth keeping. The assistant application itself should be treated as a completed
case study and harvested example, not the next active project.

## What The Tool Was

The mail assistant combined:

- `mail_lib`: read-only Thunderbird profile ingestion, mbox parsing, Gloda
  enrichment, rule-based triage, and message-body hydration.
- `examples/mail_assistant`: a localhost FastAPI/Jinja/HTMX app for unread/all
  views, local read state, section summaries, personal-rule proposals, sender
  and domain stats, and explicit IMAP Trash/Seen propagation.
- Local-first safety constraints: no remote mail exfiltration, no Thunderbird
  mbox mutation, explicit IMAP account configuration, preview-before-move, and
  exact `Message-ID` lookup before server mutation.

## Why Adoption Failed

The assistant tried to replace part of a mature mail client instead of filling
an unserved gap.

Thunderbird and Gmail already own the hard daily-mail workflows: reliable
account state, sync semantics, read/unread status, folder visibility, search,
bulk operations, recovery from stale cache state, and user trust around
destructive actions. The assistant had to reconstruct enough of that substrate
to be useful, but every reconstructed edge created another place for mismatch.

The late IMAP Trash work exposed the core problem. Even after fixing command
formatting, Gmail raw-search behavior, All Mail fallback, per-account sessions,
batch preflight, and stale-row suppression, the user experience still degraded
into managing local/server state drift. The problem was not that the model was
weak. The problem was that mail is already a synchronized multi-client state
system with a strong incumbent UI.

The model's contribution was also not the bottleneck. Summaries and rule
suggestions could help at the margin, but the daily pain was dominated by
message state, filtering, deletion confidence, duplicate account views, stale
local cache rows, and bulk-action ergonomics. Those are product and integration
problems, not prompt-quality problems.

## What Worked

- Deterministic local ingestion of Thunderbird mail became real and testable.
- The bracket-stripped `Message-ID` join between mbox and Gloda was validated
  and encoded into the reader.
- Personal rules became a small, reviewed, file-backed capability rather than
  opaque model memory.
- The app-owned snapshot/cache pattern made local UI work possible without
  continuously rereading the full profile.
- Bounded summarization clarified how to put a model behind explicit token and
  timeout limits.
- Reviewed rule proposals demonstrated a safer pattern for model-adjacent file
  mutation.
- IMAP mutation was kept conservative: exact lookup, configured accounts,
  atomic `MOVE`, no copy/delete fallback, no mbox writes.

## What Was Harvested

Keep these as reusable assets:

- `mail_lib.thunderbird`: read-only Thunderbird and mbox machinery.
- `mail_lib.personal_rules`: deterministic personal-rule parsing and selection.
- Snapshot encode/decode and preview truncation patterns from the assistant.
- The reviewed proposal/commit pattern for user-owned configuration files.
- IMAP safety lessons: never trust local cache rows as server identity; require
  exact lookup; treat stale rows as non-actionable; preserve account identity in
  UI state.
- The case study itself: an LLM feature can be technically correct and still
  lose if the product competes with a mature incumbent's stateful home turf.

## What Should Not Be Carried Forward

- Do not keep expanding the mail assistant into a general mail client.
- Do not add more fallback deletion heuristics such as subject-based deletion.
  The diagnostics showed why this is unsafe: subjects are ambiguous across
  accounts and time.
- Do not treat better prompts or a larger model as the path to adoption.
- Do not use local cache artifacts as authorization for server mutation.

## Lesson For The Next Daily Tool

The next daily-use candidate should target a job with no strong incumbent. The
right shape is not "replace a mature app's main surface with an LLM wrapper."
It is "make a workflow possible that currently has no coherent tool."

The computer-helper-agent direction fits that shape better than mail did. It
can focus on cross-application tasks, inspection, explanation, and constrained
execution where there is no single mature incumbent already owning the workflow.
That does not need to be selected immediately. The important closure is to carry
forward the criterion:

> Prefer daily tools where nothing currently does the job at all over tools
> where an incumbent already does the job well and owns the state.

## Project Disposition

Status: closed as an active product direction.

Recommended future use:

- keep `mail_lib` as a deterministic local-mail example and utility;
- keep the assistant as an example/case study;
- accept bug fixes that preserve tests and safety;
- avoid feature expansion unless a future concrete need is outside the failed
  daily-client replacement frame.
