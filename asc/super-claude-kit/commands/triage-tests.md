---
description: Run tests in disciplined, low-noise batches and report coverage
argument-hint: [test-target]
---

Follow this whenever the plan calls for test execution:

1. Identify the minimal batch that proves the change (unit file, project, or filtered suite). Prefer commands such as `dotnet test <proj> --filter`, `npm run test -- <pattern>`, or `bash scripts/test-super-claude.sh --subset <group>` depending on the stack.
2. Run one batch at a time, capture real command output (pass/fail, timings, flaky notes), and summarize the findings inline so the console log does not get flooded.
3. If failures occur, link them back to specific commits/files and either fix immediately or record them via `log-task.sh blocked` with repro steps.
4. After all required batches pass, state the overall confidence level, remaining gaps, and whether any smoke/manual steps are still outstanding.
5. If $ARGUMENTS names a higher-level target (e.g., "CosmosDb projections"), explicitly list the sub-batches you executed so other workers can repeat or extend them.


