---
description: Rehydrate context after an interruption by replaying shared logs
argument-hint: [what-changed]
---

When resuming a task mid-stream, do the following before issuing new tool calls:

1. Summarize why you are resuming (use $ARGUMENTS if present) and read `.claude/shared/logs/session-log.md` plus `.claude/shared/logs/tasks.log` to see the last recorded outcome + open todos.
2. Load `.claude/sessions/$CLAUDE_SESSION_ID/current_worker_message.txt` if it exists so you know which worker persona and guardrails are in effect.
3. Tail `.claude/beads/quickstart.log` and `.claude/beads/bug-issues.log` to confirm whether the Beads backlog already tracks the issue you are about to work on; avoid duplicating discoveries.
4. Rebuild a concise plan (what to inspect, which tools/scripts to run, and how you will verify fixes). Cross-link the plan with any Agent Mail threads or backlog ids surfaced in the logs.
5. Explicitly call out assumptions, missing inputs, or blockers so the next hand-off can pick up without re-reading the entire history.


