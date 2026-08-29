# ADR-028 — Request-level seed control

**Status:** Accepted  
**Date:** 2026-08-29

## Decision

`GenerationRequest` adds `seed: int | None = None`.

- `None` makes no seed request and preserves backend or server behavior.
- An integer asks the backend to forward that exact seed when its provider
  contract supports request-level seeding.

This is a preference, not a determinism claim. A successful response records
one of three observations in `GenerationResponse.seed_status`:

- `not_requested`: the request contained no seed;
- `accepted`: the adapter forwarded the seed and the provider completed the
  request without rejecting it; or
- `not_honored`: the adapter did not forward the requested seed.

`accepted` establishes only that the provider accepted the parameter. It does
not establish that the provider used it, that all stochastic state was fixed,
or that another run will reproduce the same output. A failed provider request
has no `GenerationResponse` and therefore makes no acceptance observation.

OpenAI-compatible, vLLM, Ollama, and in-process llama.cpp adapters forward a
requested seed on generation paths whose provider APIs expose one. Anthropic
does not expose this control through the current adapter and reports
`not_honored` on successful seeded requests. Mock engines report `accepted`
only because their local deterministic implementation consumes the canonical
request directly.

Tool loops and strategy wrappers preserve the original seed on every model
turn. They do not increment or derive per-turn seeds implicitly.

## Artifact rule

An experiment that requests a seed records both the requested value and the
observed status. An unrequested, rejected, or `not_honored` seed must not
strengthen a `DeterminismClaim`. An `accepted` seed may appear as a condition
on a `best_effort` claim, but acceptance alone must not produce
`deterministic` or equivalent wording. Reproducibility remains an observed
repeated-run property.

## Acceptance observations

- Default requests omit provider seed fields and report `not_requested`.
- Supporting adapters forward integer seed `0` without treating it as absent.
- A completed supporting-provider call reports `accepted`.
- A completed non-supporting-provider call reports `not_honored`.
- Tool-loop follow-up requests preserve the same seed.
- Experiment artifacts distinguish the requested seed from its acceptance
  observation and retain `best_effort` determinism language.

