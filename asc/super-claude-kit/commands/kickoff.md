---
description: Kick off a session by syncing mail, capsule, and a fresh plan
argument-hint: [focus-area]
---

Use this ritual at the beginning of every work session (or after long pauses) to synchronize the Super Claude Kit context:

1. Restate the focus area ($ARGUMENTS if provided, otherwise the current sprint/milestone) and confirm the active worker profile / session id so the log books record the right persona.
2. Check inbound context:
   - If `.claude/shared/logs/agent-mail.md` or `.claude/beads/quickstart.log` exist, read the newest entries, summarize actionable items, and capture todos with TodoWrite or by calling `bash .claude/hooks/log-discovery.sh <discipline> "<note>"` when something needs to be broadcast to the hive.
   - Inspect `.claude/shared/logs/tasks.log` for any `pending` or `blocked` items and mirror them in the working plan.
   - Review `CLAUDE.md` plus the capsule `<files-in-context/>` section to see what was already loaded into memory.
3. Produce a concrete work plan (3-5 steps) that names the files/tools you expect to use and the verification strategy (tests, linters, manual review, etc.).
4. Only start using tools after the kickoff summary + plan have been written so the rest of the session is grounded in the refreshed context.


