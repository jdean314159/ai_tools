# Minimum reliable programming path

This document defines the narrow programming workflow that `agent_lib` is currently trying to prove before adding more coordination layers.

## Goal

Solve a small, bounded programming task reliably before broadening the system with more workers, more messaging, or more policies.

## Current baseline path

1. Load a `ProgrammingTask` plus persisted task state.
2. Build a bounded context that keeps the task definition visible.
3. Let one worker inspect and patch the target.
4. Run local verification.
5. Escalate to the critic only on defined failure-policy triggers.
6. Persist plan, verification, and patch state.
7. Resume from persisted state when interrupted.

## In scope

- one patch-writing worker
- optional mentor / critic escalation
- explicit workspace policy
- explicit failure policy
- durable plan state and task state
- context compaction and file-backed output truncation
- optional isolated workspaces

## Not the default path

- multiple concurrent patch writers
- mailbox-first orchestration
- free-form worker swarms
- unrestricted shell access
- irreversible auto-apply without policy controls

## Representative benchmark suite

The benchmark exposed through:

```bash
agent-lib evaluate-programming
```

currently exercises:

- minimal single-file repair
- proposal-only review gating
- nested-path repair with compile verification
- resume from persisted task state after interruption
- isolated workspace execution

This is intended to measure the current harness before the runtime grows broader.
