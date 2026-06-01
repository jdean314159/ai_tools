---
description: Close the sprint by updating plans, Beads, and review notes
argument-hint: [sprint-number]
---

Use this when all sprint work is done and you are finalizing Sprint $ARGUMENTS (default 109):

1. Confirm every task is complete: check Agent Mail, `/todos`, and `.claude/shared/logs/tasks.log`, closing anything that still shows `pending/blocked`.
2. Update the sprint plan under `management/sprints/` (burn-down, completed scope, carryover). Be explicit about which backlog items moved.
3. Close related Beads tasks (`bd ready --json`, `bd update <id> --status done`, etc.) so the backlog stays accurate.
4. Draft the Sprint $ARGUMENTS review document inside `management/sprints/` capturing achievements, demo notes, risks, and next-sprint focus.
5. Perform a clean git close-out: review `git status`, add the updated sprint plan/review docs (plus the Beads sync artifacts if tracked), commit with a message like `"Sprint $ARGUMENTS closeout"`, and `git push` so the team has the latest state.
6. Send a final notification to the whole team (Agent Mail/chat) summarizing the close-out, linking to the updated plan + review doc, confirming the push succeeded, and explicitly mentioning ProjectManager, ProductManager, SoftwareArchitect, BackendDeveloper, TestsDeveloper, ProjectReviewer, and DocumentationWriter so nothing falls through the cracks.
