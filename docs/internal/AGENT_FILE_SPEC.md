# AGENT.md File Specification

## Purpose

`AGENT.md` files are repo-local or package-local context documents for agents and humans working inside `ai_tools`.

They exist to reduce repeated context reconstruction, make local constraints explicit, and improve the reliability of agent-driven work.

They are part of the harness. They are not optional narrative documentation.

---

## Design goals

An `AGENT.md` file should:

- tell an agent where it is
- explain local architecture and boundaries
- record package- or directory-specific conventions
- state what is in progress
- identify verification expectations
- make local “do not break this” invariants obvious

It should not duplicate the entire repo architecture. Root documents already cover that.

---

## Scope and precedence

### Root instructions

`AGENTS.md` is the single source of repository-wide operating rules. The
root-level `AGENT.md` is a compatibility pointer for tools that discover the
singular filename; it must not duplicate or add normative rules.

### Package-local `AGENT.md`

A package-local `AGENT.md` should provide local overrides and details for one package or subsystem.

Examples:

- `engram/AGENT.md`
- `rag_lib/AGENT.md`
- `agent_lib/AGENT.md`

### Precedence rule

When guidance differs:

1. safety and policy constraints always win
2. root `AGENTS.md` and architecture documents define repo-wide intent
3. the nearest relevant local `AGENT.md` defines local operating rules
4. transient chat instructions are not a replacement for repo artifacts

---

## Recommended structure

Use concise Markdown with explicit section headings. A strong default template is:

```md
# AGENT.md

## Purpose
What this package/directory is for.

## Role in ai_tools
How it fits the suite.

## Key modules
List the most important files/directories and what they own.

## Invariants
Rules that must remain true.

## Current state
What is implemented, partial, or intentionally deferred.

## Constraints
Safety, dependency, performance, or design limits.

## Verification
Which tests/checks matter here.

## Typical tasks
Common safe tasks for agents or humans.

## Avoid
Common failure modes or bad edits.

## Related docs
Links to `docs/design/VISION.md`, ADRs, README, manifests, or other local docs.
```

---

## Content guidance

### Good content

Include information such as:

- ownership boundaries
- important public APIs
- current migration state
- local terminology
- local testing commands
- dependency direction rules
- files that should not be casually rewritten
- performance or safety constraints

### Bad content

Avoid:

- long prose history
- stale sprint notes
- speculative architecture that has not been accepted
- secrets, tokens, private credentials, or host-specific personal paths
- content copied verbatim from root docs without local specialization

---

## Style constraints

`AGENT.md` files should be:

- short enough to load quickly
- concrete rather than motivational
- updated when local architecture changes
- written for both humans and agent tooling

They should prefer bullets and short sections over essays.

---

## Suggested placement order

Create package-local `AGENT.md` files first for the packages where local guidance provides the most leverage:

1. `agent_lib`
2. `engram`
3. `rag_lib`
4. `llm_inspector_ui`
5. `language_tutor`

---

## Change discipline

Any substantial change to a package’s public boundary, local architecture, or testing expectations should trigger a review of that package’s `AGENT.md`.

If a package repeatedly requires long chat explanations before work can begin, that is a sign its local `AGENT.md` is missing or insufficient.
