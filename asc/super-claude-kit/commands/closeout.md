---
description: Close out a work session with tests, discoveries, and notifications
argument-hint: [result]
---

Run this before leaving the terminal so the hive stays up to date:

1. Verify the work: execute the smallest meaningful batch of tests/linters that prove the change, capture pass/fail status, and note any follow-up test debt.
2. Update `.claude/shared/logs/tasks.log` (via TodoWrite or `bash .claude/hooks/log-task.sh <status> <note>`) so every pending/blocked/done item reflects its latest state.
3. Log key discoveries or architecture decisions with `bash .claude/hooks/log-discovery.sh <discipline> "<message>"` so they propagate to Agent Mail + Beads when applicable.
4. Refresh `CLAUDE.md` / capsule summaries (especially `<team-tasks>` and `<team-discoveries>`) and draft the notification you will send to the wider team (agent mail, chat, PR comment, etc.) describing what was done, what is left, and how to verify—always CC ProjectManager, ProductManager, SoftwareArchitect, BackendDeveloper, TestsDeveloper, ProjectReviewer, and DocumentationWriter so documentation and downstream owners stay unblocked.
5. Confirm that temporary files in `.claude/sessions/$CLAUDE_SESSION_ID/` are clean, stop any background `/bashes`, and record explicit next steps or owners before signing off.
