# Contract boundary assessment

**Date:** 2026-09-01
**Status:** Trace duplication consolidated; tool boundaries retained.

## Decision

- Keep `agent_lib.ToolCall` / `ToolResult` distinct from the `llm_engines`
  provider contracts.
- Use `llm_harness_core.TraceEvent` as the one trace-event class. Inspector now
  re-exports that exact class rather than subclassing and copying it.

## Tool contracts: same vocabulary, different ownership

`agent_lib` models an agent-runtime action and observation. Its call contains
only a runtime tool name and arguments, while its result carries a boolean
outcome plus open policy/execution metadata
(`agent_lib/src/agent_lib/contracts.py:30-41`). The runtime compares calls by
value to detect repeated actions (`agent_lib/src/agent_lib/runtime.py:575-587`),
and its interop conversion interprets metadata such as approval, sandbox,
policy, and degraded execution (`agent_lib/src/agent_lib/interop.py:14-78`).

`llm_engines` models provider-facing generation and replay. Its model-produced
call requires a provider correlation ID and converts to the shared
`ToolInvocation` contract (`llm_engines/src/llm_engines/contracts/engine.py:210-230`).
Its executor result preserves that correlation ID, a three-state status,
separate error text, and execution timing
(`llm_engines/src/llm_engines/contracts/tools.py:72-94`). The engine executor
uses those fields to associate results with calls and format them back into the
model conversation (`llm_engines/src/llm_engines/tools.py:283-330`).

No `agent_lib` source imports either `llm_engines` tool class. A shared class
would therefore add provider/replay requirements to local agent actions or
discard agent policy metadata without removing an active adapter.

### Must be built (does not exist yet)

Nothing is required for the current call paths. If an agent runtime later
executes model-emitted provider calls directly, it will need an explicit adapter
that assigns or preserves `call_id`, maps `success` plus agent error metadata to
the engine status/error fields, and preserves sandbox/policy diagnostics. That
bridge does not exist today and should not be implied by matching class names.

## Trace events: duplicate identity removed

The shared event already owns the full trace payload, severity, correlation,
timestamp, and tags (`llm_harness_core/src/llm_harness_core/events.py:10-22`).
Inspector's former subclass added only the legacy aliases `kind` and `fields`
and a field-by-field copying constructor. Inspector adapters then copied shared
events solely to regain the subclass identity.

The aliases now live on the shared immutable event. `llm_inspector.TraceEvent`,
`llm_inspector.core.TraceEvent`, and `llm_harness_core.TraceEvent` are the same
class. Inspector traces return their event instances directly, and the Engram
adapter no longer rebuilds them.

### Compatibility

- Existing `event.kind` and `event.fields` reads continue to work.
- Existing constructors are unchanged because the aliases are properties, not
  dataclass fields.
- `isinstance(event, llm_harness_core.TraceEvent)` now holds for every event
  exported by Inspector without conversion.
- The former Inspector-only `TraceEvent.from_interop(...)` helper is removed;
  repository search found its only production uses inside the copying paths
  removed by this change.

## Assumptions to verify

- External consumers may have called the undocumented Inspector subclass
  method `TraceEvent.from_interop(...)`. No in-repository consumer remains.
- No cross-package agent/provider tool adapter is currently required. Revisit
  only when a concrete call path crosses that boundary.
