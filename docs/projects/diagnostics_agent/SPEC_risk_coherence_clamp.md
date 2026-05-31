# Build Spec — Risk-Coherence Clamp (`diagnostics_agent`)

**File:** `examples/diagnostics_agent/src/diagnostics_agent/interpret.py`
**Type:** deterministic post-processing, additive. No schema change, no prompt change.
**Why:** The model can return a concern at e.g. `high` severity while reporting
`security_risk: none` and `operational_risk: low`. That state is incoherent and is
reachable today: the existing `_apply_operational_floor` only raises
`operational_risk` for findings in `_OPERATIONAL_FLOOR_CATEGORIES` (disk/memory/
stability). Auth concerns are deliberately *not* floored, so an auth concern rated
`high` by the model leaves both axes unraised. This clamp closes that gap.

## Invariant to enforce

After all processing, the following must hold for every `Interpretation`:

    max(security_risk, operational_risk) >= max(c.severity for c in prioritized_concerns)

i.e. at least one risk axis must be at or above the strongest concern. If neither
axis reaches it, raise the **higher** of the two axes to the strongest concern
severity.

### Why bound the higher axis, not a specific one

Concerns carry no security-vs-operational tag, so the code cannot know which axis a
given concern belongs to without inventing a classification the model did not
provide. Raising the already-higher axis guarantees coherence while making the
minimal change to the model's stated judgment. This respects the locked decision
"treat LLM output as commentary to verify, not fact to trust" for *structural*
consistency, without overriding the model's security-vs-operational *framing*.

## Scope / non-goals

- Do **not** lower anything. Clamp is monotonic-up only.
- Do **not** touch `_apply_operational_floor`. This runs *after* it.
- Do **not** add or reclassify concerns. Operate only on the two axis fields.
- `RiskLevel` (concern severity) and `OverallRisk` (axis) share ranks for the
  overlapping labels but differ at the bottom: concerns use `info`, axes use
  `none`. `_RISK_RANK` already covers both label sets — reuse `_risk_rank`; do not
  build a second rank table. If a concern severity has no axis-label equivalent
  (`info` has no axis form), map it up to the nearest valid `OverallRisk` when
  assigning to an axis (`info` -> `low`). Add a tiny helper for this mapping rather
  than inlining it.

## Implementation

1. Add a pure function:

   ```python
   def _apply_risk_coherence(interpretation: Interpretation) -> Interpretation:
       """Ensure at least one risk axis is >= the strongest concern severity.

       Raises the higher of security_risk / operational_risk to meet the
       strongest concern; never lowers either axis. No-op when already coherent
       or when there are no concerns.
       """
   ```

   - If `prioritized_concerns` is empty -> return unchanged.
   - Compute `strongest = max(_risk_rank(c.severity) for c in concerns)`.
   - If `max(_risk_rank(security_risk), _risk_rank(operational_risk)) >= strongest`
     -> return unchanged.
   - Else pick the axis with the higher current rank (tie -> `operational_risk`,
     since operational is the more common floor path and keeps behavior
     predictable), and set it to the axis-label form of the strongest concern
     severity via the `info -> low` mapping helper. Return
     `interpretation.model_copy(update={<that axis>: <new value>})`.

2. Call it in `LogInterpreter.interpret`, immediately after the operational floor,
   so the floor's possibly-raised concerns are included in the strongest-concern
   computation:

   ```python
   interpretation = Interpretation.model_validate_json(response.text)
   interpretation = _apply_operational_floor(interpretation, summary)
   return _apply_risk_coherence(interpretation)
   ```

3. Order matters: floor first (it may raise a concern's severity), coherence
   second (it reads final concern severities). Do not reverse.

## Tests (`examples/diagnostics_agent/tests/`, mirror existing interpret-test style)

Construct `Interpretation` objects directly; no engine/model needed.

1. **auth gap (the motivating case):** one concern `severity="high"`,
   `security_risk="none"`, `operational_risk="low"`, no floorable findings ->
   after clamp, `max(axes) == "high"`; the raised axis is `operational_risk`
   (higher of `none`/`low`); concerns untouched.
2. **already coherent:** concern `medium`, `security_risk="high"` -> object
   returned unchanged (assert identity or field equality; no axis moved).
3. **no concerns:** empty `prioritized_concerns` -> unchanged.
4. **tie-break:** concern `high`, both axes `low` -> `operational_risk` raised to
   `high`, `security_risk` stays `low`.
5. **info concern maps up:** concern `severity="info"`, both axes `none` -> the
   chosen axis becomes `low`, not an invalid `info`/`none` mismatch. (Guards the
   `RiskLevel` vs `OverallRisk` label-set difference.)
6. **interaction with floor:** a disk `CRITICAL` finding (floored to `high`) with
   the model returning `operational_risk="low"` and no concern referencing it ->
   floor adds a `high` concern AND raises `operational_risk` to `high`; coherence
   clamp is then a no-op (already coherent). Asserts the two stages compose without
   double-raising or fighting.

## Acceptance

- `make test-core` green (or the diagnostics_agent package test subset).
- New tests pass.
- No change to `models.py`, prompts, schema, or `_apply_operational_floor`.
- `git diff` confined to `interpret.py` plus one test file.
