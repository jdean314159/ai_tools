# ADR-012: Two-axis risk model with deterministic operational floor

**Date:** 2026-05-31
**Status:** Accepted
**Deciders:** Jeff Dean
**Related:** `diagnostics_agent/`, `docs/projects/diagnostics_agent/CAMPAIGN.md`, ADR-011 (agent execution isolation)

---

## Context

The original interpretation schema produced a single `overall_risk` field.
Empirical testing across multiple models and real journal runs surfaced two
failure modes that a single axis cannot cleanly resolve:

1. **False-critical auth escalation.** A single `pam_unix(cinnamon-screensaver)`
   unlock failure was rated "critical" because the model pattern-matched
   "PAM authentication failure → critical" without weighting by service or
   frequency. A local screensaver unlock is not a security incident.

2. **Operational under-rating.** After prompt-side calibration fixed the auth
   inflation, `ata10: softreset failed (device not ready)` was rated "low"
   overall despite the model's own rationale calling it a potential data-integrity
   risk. The model had anchored on "not a security threat" and conflated that
   with "low severity."

Both failures shared the same root cause: a single risk axis pulled toward
whichever framing dominated the prompt. Security framing → auth events
over-rated, hardware events under-rated. Operational framing → the reverse.

A third failure mode emerged from deterministic analysis of model outputs: even
with correctly-framed prompts, small models (3B-class) assigned labels before
writing their rationales, producing findings where the concern's severity label
contradicted its own explanation. This was traced to `ConcernAssessment`
generating `severity` before `rationale` — the model committed the label before
reasoning about the concern.

---

## Decision

### Two risk axes

Replace `overall_risk: Literal[...]` with two independent axes:

```python
class Interpretation(BaseModel):
    reasoning: str                    # free-text, generated FIRST
    summary: str
    security_risk: Literal["none", "low", "medium", "high", "critical"]
    operational_risk: Literal["none", "low", "medium", "high", "critical"]
    prioritized_concerns: list[ConcernAssessment]
    recommended_checks: list[str]
```

The prompt distinguishes the axes explicitly: `security_risk` reflects
compromise, credential exposure, or unauthorized access; `operational_risk`
reflects hardware failure, service degradation, or data-integrity risk. The two
are independent — a disk softreset is high operational risk and zero security
risk simultaneously.

### Rationale before label (field order)

`ConcernAssessment` generates `rationale` before `severity`:

```python
class ConcernAssessment(BaseModel):
    finding_ref: str
    rationale: str    # reason FIRST — model reasons before committing the label
    severity: Literal["info", "low", "medium", "high", "critical"]
```

Under grammar-constrained decoding, fields generate in declaration order. With
severity before rationale, the model commits a label via pattern-matching and
then writes a rationale that may (and did) contradict it. Rationale-first
conditions the label on the model's own explanation.

### Deterministic operational floor

After the model produces and validates its output, a deterministic post-processing
step clamps `operational_risk` and matching concern severities:

| Finding category | Finding severity | Floor |
|---|---|---|
| `disk`, `memory`, `stability` | `ERROR` | `operational_risk` ≥ medium |
| `disk`, `memory`, `stability` | `CRITICAL` | `operational_risk` ≥ high |
| `auth` | (any) | **not clamped** |

The floor raises but never lowers. `auth` is explicitly excluded because auth
risk is context-dependent: a screensaver unlock failure is benign; a cluster of
`sshd` failures from a foreign IP is not. The same PAM message warrants
different severity in different contexts, so the model's service-and-frequency
judgment is retained. Hardware/reliability signals are "presence implies
concern" — the floor is correct regardless of context.

Matching concerns (where `finding_ref` matches the finding's rule name or
template) are clamped to the same floor as `operational_risk`.

### Principle (non-negotiable)

> Push non-negotiable judgments into the deterministic layer. Treat LLM output
> as commentary to verify, not fact to trust.

The deterministic triage (parsing, clustering, rule matching, severity-from-
priority) has been consistently honest across all model sizes and all runs. The
LLM interpretation layer has failed on calibration, field order, grounding, and
OS-version fabrication. The floor, the self-noise exclusion, and the
conservation invariant are all enforcements of this principle.

---

## Consequences

**Positive:**
- Hardware findings surface at actionable operational severity regardless of
  model quality or prompt drift. On a 4 GB laptop with a 3B-class model, the
  deterministic layer remains trustworthy even when the LLM narrative is not.
- The two-axis split exposes the real finding pattern: workstation runs produce
  "security: none, operational: medium" cleanly, without either axis inflating
  the other.
- Internal consistency: rationale-before-label eliminated a documented class of
  within-concern contradictions (label says "critical," rationale says "local
  session noise").

**Ongoing limitation:**
- `overall_risk` is not automatically constrained to `≥ max(concern.severity)`.
  A medium concern can sit under a low/none overall if the model rates the
  overall independently. A future fix: deterministically clamp both risk axes to
  the maximum of their matching concern severities.
- The floor is one-directional: a floored-but-confirmed-benign signal (e.g.,
  `ata10: softreset failed` traced to standby wake latency) cannot be demoted
  without a user-disposition or baseline store override. This is by design — the
  correct channel is a structured baseline/disposition store, not relaxing the
  floor.

---

## Alternatives considered

**Single axis with explicit security-vs-operational framing in the prompt.**
Tried. The axis is pulled toward whichever framing the prompt emphasizes most
recently — first run underweighted operational, second run overweighted it. A
single number cannot simultaneously mean "security risk" and "operational risk"
without one dominating.

**Deterministic severity for auth findings as well.**
Rejected. Auth severity is genuinely context-dependent in a way that hardware
severity is not. A screensaver unlock failure and an `sshd` brute-force attempt
are both "PAM auth failure" — their severity differs by service, count, and time
pattern, not by presence alone. The LLM, given the calibration guidance, handles
this correctly. A deterministic auth floor would re-introduce the false-critical
that triggered this ADR.
