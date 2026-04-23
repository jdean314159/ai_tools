# JSON Task / Progress Manifest Specification

## Purpose

A task/progress manifest is a JSON file that records what work exists, what is in progress, how success is verified, and what should happen next.

It is designed to survive session boundaries and support both human review and agent execution.

---

## Why JSON

The preferred format is JSON because it is:

- structured and machine-readable
- easy to diff and validate
- less likely than loose Markdown notes to be casually rewritten in large blocks

---

## Design goals

A manifest should answer:

- what is the next highest-value task
- what package or subsystem it affects
- what constraints apply
- what files are likely to change
- how success is verified
- what status each task currently has

---

## Recommended filename and placement

Suggested filenames:

- `TASKS.json`
- `TASK_MANIFEST.json`
- `progress/tasks.json`

Recommended placement:

- repo root for repo-wide planning
- package root for package-local work streams

Examples:

- `TASK_MANIFEST.json`
- `agent_lib/TASK_MANIFEST.json`
- `engram_lite/TASK_MANIFEST.json`

---

## Top-level schema

Recommended top-level object:

```json
{
  "manifest_version": 1,
  "project": "ai_tools",
  "scope": "repo" ,
  "updated_at": "2026-04-21T00:00:00Z",
  "next_task_id": "agent-012",
  "tasks": []
}
```

### Top-level fields

- `manifest_version`: integer schema version
- `project`: repo or package name
- `scope`: `repo` or package/subsystem scope label
- `updated_at`: ISO-8601 timestamp
- `next_task_id`: task the agent should inspect first
- `tasks`: array of task objects

---

## Task object schema

Recommended task shape:

```json
{
  "id": "engram-lite-001",
  "title": "Improve episodic retrieval precision",
  "status": "ready",
  "priority": "high",
  "package": "engram_lite",
  "kind": "implementation",
  "summary": "Tighten retrieval scoring and reduce redundant recalls.",
  "rationale": "Current retrieval still admits moderate false positives.",
  "dependencies": ["interop-006"],
  "constraints": [
    "Keep engram_lite lightweight.",
    "Do not import heavy engram lifecycle machinery."
  ],
  "likely_files": [
    "engram_lite/engram_lite/project_memory.py",
    "engram_lite/engram_lite/memory/quality.py"
  ],
  "verification": [
    "Add targeted retrieval tests.",
    "Run engram_lite test suite."
  ],
  "notes": [],
  "completion_evidence": []
}
```

### Required fields

- `id`
- `title`
- `status`
- `priority`
- `summary`
- `verification`

### Strongly recommended fields

- `package`
- `kind`
- `rationale`
- `constraints`
- `likely_files`
- `dependencies`
- `completion_evidence`

---

## Allowed status values

Recommended statuses:

- `proposed`
- `ready`
- `in_progress`
- `blocked`
- `done`
- `archived`

Guidance:

- use `ready` when the task can be started immediately
- use `blocked` only when an explicit dependency or decision prevents work
- use `archived` when the task is intentionally no longer relevant

---

## Allowed task kinds

Suggested values:

- `implementation`
- `bugfix`
- `refactor`
- `evaluation`
- `documentation`
- `architecture`
- `release`

This field is advisory, not a hard semantic contract.

---

## Verification discipline

Every task should include explicit verification steps.

These may include:

- test files to run
- packages to compile
- wheel builds
- manual UI checks
- artifact comparisons
- doc updates required for completion

A task without verification steps is underspecified.

---

## Completion evidence

When a task is marked `done`, add evidence such as:

- test results
- archive names
- changed docs
- reports produced
- relevant ADR updates

This keeps the manifest useful as both a planning and audit artifact.

---

## Change discipline

Agents and humans should update manifests conservatively:

- do not rewrite unrelated tasks casually
- prefer status changes and evidence additions over wholesale reformatting
- keep completed tasks until they are intentionally archived
- preserve task IDs so cross-references remain stable

---

## Recommended first adopters in `ai_tools`

Use manifests first where work is multi-step, safety-sensitive, or likely to span sessions:

1. `agent_lib`
2. `engram_lite`
3. `rag_lib`
4. repo root for cross-package phases

---

## Relationship to other docs

The manifest does not replace:

- `VISION.md` for architecture
- `CURRENT_STATE.md` for implementation snapshot
- `ROADMAP.md` for ordered phases
- `ADR_INDEX.md` and ADRs for decisions
- `AGENT.md` files for local context

It answers a narrower question: *what are we doing next, how do we know it worked, and what is the current task state?*
