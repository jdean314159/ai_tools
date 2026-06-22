# Lessons from the OPCOM / dev-team-six family (inputs to SPEC-LIVE-01 and the lease-lifecycle decision)

**Status:** Reference notes, not a spec. Captured from a read of a sibling multi-agent system so the lessons
don't get lost. Where a lesson is actionable for `ai_tools`, it is tied to the specific open decision it bears on.

## What was read

A related multi-agent system (separate author), reviewed as source, not run. The pieces and their roles, as
grounded in the code:

- **dev-team-six** — installable framework for Claude Code workers (current evolution of `super-claude-kit`).
  Templates a `.claude/` config into a target project: ~16 worker personas (ceo → product-manager →
  project-manager → architect → devs/testers/reviewers), ~40 process skills, an 8-event hook system, and a
  capsule context layer.
- **OPCOM** — out-of-process coordination backbone. TypeScript/pnpm monorepo (server, shared, ui) on Postgres +
  MCP (3100) + WebSocket (3200): missions, tasks, reservations, messaging, channels, events, plus a task
  dispatcher with a wake waterfall. Replaces the earlier `mcp_agent_mail`.
- **mcp_agent_mail** — OPCOM's direct predecessor, in Python (SQLModel). Reviewed specifically to diff the
  reservation model across the rebuild.
- **Beads (`bd`)** — external task authority (third-party). OPCOM defers to it: a code comment reads "Beads
  remains the task authority; this is OPCOM's dispatch and tracking layer."
- **Capsules** — TOON-format session memory persisted through PreCompact/PostCompact hooks; externalized memory
  across bounded worker sessions.

Architecture in one sentence: **thin Claude-Code workers, coordinated out-of-process through a stateful service
(OPCOM), with task authority external (Beads) and memory external (capsules)** — orchestration pushed out of the
agent into surrounding services. This is the architectural opposite of `agent_lib`, where coordination, leases,
and (under debate) the loop live in-process in a library.

Caveat that governs every lesson below: that system is **out-of-process** (service + CLI workers); `ai_tools` is
**in-process** (a library). Lessons about *data models* transfer directly; lessons about *topology* transfer as
direction and caution, not as drop-in designs.

## Lesson 1 — Lease lifecycle: a proven design for the gap LIVE-00 already predicted (DIRECTLY PORTABLE)

This is the highest-value takeaway and the one concrete borrow.

`agent_lib`'s `WorkspaceIsolationManager` lease record is `{owner_id, status, thread_id, note, created_at,
metadata}` — no TTL, no reclaim, no exclusive/shared distinction. LIVE-00 named "no TTL / owner-death reclaim /
release-on-failure" as the predicted #2 gap, and FX-CONTENTION exists to force precisely the deadlock that
absence produces (a holder stalls; nothing reclaims; contenders are denied to the step cap).

The sibling system solved this, and kept the solution across a full Python→TypeScript reimplementation — the
strongest signal a design is load-bearing:

- **mcp_agent_mail** (`src/mcp_agent_mail/models.py:88`, `storage.py`): `FileReservation` has `exclusive: bool`,
  `expires_ts` (TTL), `released_ts` (explicit release). A lock is reclaimed when stale, where stale = **owner
  process dead OR age exceeds `stale_timeout` (default 180s)**, with automatic cleanup.
- **OPCOM** (`packages/shared/src/types/reservation.ts`, `packages/server/src/services/reservation-service.ts`):
  kept `exclusive`, `expiresAt` (TTL default 3600s), `releasedAt`. Conflict checks filter `expiresAt > now`, so
  an expired reservation automatically stops blocking (reclaim-at-query-time).

The reclaim *mechanism* adapted to deployment: local/co-located (agent_mail) used owner-PID-liveness plus age;
out-of-process service (OPCOM) used TTL expiry plus explicit release, because it cannot see a remote worker's
process.

Actionable for `ai_tools`: when the lease-reclaim gap is forced in-tree, do not design from scratch. Add to the
lease record an `expires_ts`, an explicit release, and an exclusive/shared distinction, and treat an expired
lease as free. `created_at` is already present. Because `agent_lib` is **in-process**, owner-liveness reclaim
(is the holding thread/owner still alive?) is available to it the way it was to `agent_mail` — it is not limited
to TTL-only reclaim. This is a candidate ADR in its own right, distinct from SPEC-LIVE-01's termination work, and
should be triggered probe-first (a run that deadlocks on a stalled holder) rather than built speculatively.

## Lesson 2 — Externalization answers the loop fork by example (DIRECTION, NOT DROP-IN)

The sibling system pushes everything out of the agent: coordination → OPCOM, task authority → Beads, memory →
capsules; the worker is deliberately thin. That is the maximal form of the "primitives in the library, loop in a
separate layer" split — and it is a running system, which is real evidence the split scales.

It bears directly on the open `agent_lib` fork (should the execution loop live in `agent_lib`, or stay in the
probe/application layer). The grounded fact behind that fork: `agent_lib/.../coordination.py` has no execution
loop, no `run`/`step`/`terminate`/`done` — `ManagedCoordination` is a container, and the probe builds the entire
loop. The sibling system is a worked example of keeping orchestration *outside* the agent primitive.

What transfers is the **boundary discipline** (orchestration is not the agent's job), not the implementation (a
Postgres-backed service is not what an in-process library should become). Recommendation already on record:
keep the loop out of `agent_lib`; extract shared contracts (see Lesson 3) only when a second consumer forces
them.

## Lesson 3 — External, singular task authority is the clean form of Finding 1

OPCOM's comment — "Beads remains the task authority; this is OPCOM's dispatch and tracking layer" — is the
separation Finding 1 is about: *who owns completion state* vs *who acts on it*. LIVE-00 Finding 1 is exactly the
failure of collapsing those — the harness has an authoritative `_done()` but lets a model-volunteered
`{"done":true}` substitute for it, so a satisfied predicate never terminates the run.

The sibling system makes that mistake structurally impossible by putting the authority in a different system.
`ai_tools` can get the same guarantee in-process without a separate service: make the authoritative predicate —
never the model signal — drive termination; demote `{"done":true}` to an early-exit hint. That is precisely what
SPEC-LIVE-01 would encode. The lesson is not "add a task service"; it is "the completion authority and the actor
must not be the same component."

## Lesson 4 — Wake-on-event vs a scheduler loop (REFRAMES THE FORK)

OPCOM has no central turn-loop. AsyncRewake wakes a worker when a task or message lands (a poll hook that exits
code 2 to wake the model). The LIVE probe, by contrast, uses synchronous coordinator-alternation.

Not directly portable to a synchronous local-model probe, but it reframes the loop fork usefully: the question
may not be *where* the loop lives but whether it is a central loop at all versus a wake-on-event reaction with no
central scheduler. Worth holding when scoping any future `agent_lib` orchestration: a reaction-to-events contract
may be a smaller, more reusable primitive than a loop.

## Lesson 5 — Capsules ≈ engram (CONFIRMATION, NOT A BORROW)

Capsules are TOON-format session memory surviving compaction via flat files and PreCompact/PostCompact hooks —
the same externalized-memory-across-bounded-sessions problem `engram` solves with a real library (four layers,
calibrated thresholds). The sibling system is the shell-script-and-flat-file version; `engram` is the engineered
version. Nothing to adopt. The value is confirmation that a serious multi-agent system independently hits the
problem `engram` was built for and must solve it somehow.

## Priority

If one lesson is acted on, it is **Lesson 1**: the only place where a proven, rewrite-survived design in the
sibling system drops almost directly onto a gap `agent_lib` has already predicted in itself. Lessons 2–4 are
architectural orientation for the loop fork and SPEC-LIVE-01; Lesson 5 is a sanity check on `engram`.

## Provenance note

All claims above are grounded in a read of the sibling repositories' source (cited by file where load-bearing).
The system was read, not executed; behavioral claims about it are inferred from code and would need a run to
confirm. The two systems differ in deployment model (out-of-process service vs in-process library), so transfer
is selective and called out per lesson.
