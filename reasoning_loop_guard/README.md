# reasoning-loop-guard

`reasoning_loop_guard` is a small, engine-neutral control-loop detector. It
examines already-decoded reasoning text and advises its caller when sustained
repetition indicates a loop. It never cancels a request, calls an engine, or
resubmits a prompt.

```python
from reasoning_loop_guard import detect_and_redirect

intervention = detect_and_redirect(reasoning_events)
if intervention is not None:
    preserved_reasoning = full_reasoning[: intervention.truncation_point]
    # agent_lib owns cancellation and resubmission using intervention.instruction.
```

The input may be an iterable of strings, mappings with a string `text` field,
or typed events exposing a string `.text` attribute. A plain string is also
accepted. `truncation_point` is a character offset in the exact concatenation
of those text values.

Version 1 deliberately uses only normalized text. Its conservative fixed
defaults are 4-grams, a 96-token sliding window, a 35% repeated-ngram
threshold, and three consecutive overlapping confirmations. These are module
policy rather than engine controls and should be calibrated with Stage A traces
before becoming configurable.

## Validation status

The v1 defaults **failed NAV-TEST-00 Stage A validation**. They fired on all
three budget-exhausted runs, but also fired on the successful control run and
often preceded the manually identified navigation-loop boundary. Those runs
had model thinking disabled; repeated JSON actions are not a reasoning stream.
Do not wire this detector into the NAV runtime. See
[`NAV-TEST-00-LOOP-GUARD-VALIDATION.md`](../docs/projects/agent_lib/NAV-TEST-00-LOOP-GUARD-VALIDATION.md).
