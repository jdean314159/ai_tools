---
description: Mail + task execution with batched testing
---

1. Fetch Agent Mail (`/agents` if inbox not mounted) and summarize anything actionable.
2. Review your active todos (`/todos`, `.claude/shared/logs/tasks.log`, capsule `<team-tasks>`).
3. Complete each assignment, running only the minimal batch of tests per change (unit file, project, etc.) to avoid blowing up memory. Capture pass/fail details inline.
4. Once work is done, update tasks/discoveries and send a concise notification to the whole team covering what shipped, tests executed, and remaining risks—explicitly include ProjectManager, ProductManager, SoftwareArchitect, ProjectReviewer, TestsDeveloper, BackendDeveloper, and DocumentationWriter in the Agent Mail thread so everyone stays aligned.
