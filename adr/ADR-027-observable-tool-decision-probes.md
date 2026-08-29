# ADR-027 — Observable tool-decision probes

**Status:** Accepted  
**Date:** 2026-08-29

## Decision

ai_tools may investigate model *process behavior* only through named,
observable decision points. The first experiment measures whether a model:

- calls a required tool;
- chooses the relevant tool when another is available;
- avoids tool use when a direct answer is required; and
- constructs exact typed arguments.

The tools are never executed. This keeps selection and argument construction
separate from tool implementation, network, and side-effect failures. Each
case uses a fixed synthetic prompt and temperature zero. Campaigns may request
thinking on or off, but reasoning text is neither captured nor treated as an
explanation of the decision.

The profile is `llm_engines.tool_decision_campaign`, version 2. Version 1 was
withdrawn during development because it did not retain the requested thinking
setting, making matched comparisons uninterpretable. Version 2 records that
setting along with
case IDs, expected and observed action classes, selected tool names, argument
match booleans, direct-answer match booleans, finish reasons, latency, and
exception types. It omits raw prompts, response text, actual argument values,
endpoint URLs, secrets, and exception messages.

Pass rates and latency summaries describe only the fixed cases and repetitions
in that artifact. They are not estimates of application reliability. A later
application experiment must define its own tasks, expected decisions, privacy
policy, and independent checks.

Matched latency comparisons must run their conditions sequentially against an
otherwise idle endpoint unless server contention is itself the declared
treatment. The first version-2 thinking-on/off pair was launched concurrently;
its correctness observations remain usable, but its latency values were
excluded. A replacement sequential pair supplied the reported descriptive
latency comparison. This execution condition is as load-bearing as the
`thinking_requested` field added when version 1 was withdrawn.

## Acceptance observations

- Deterministic tests cover all four decisions and aggregation.
- Wrong argument values fail without being retained.
- Provider failures retain only exception types.
- Engines without tool calling fail before a campaign begins.
- Artifacts round-trip with a validated privacy declaration.
- Inspector recognizes and compares the profile without claiming access to
  hidden reasoning.
