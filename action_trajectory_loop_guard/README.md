# action-trajectory-loop-guard

`action_trajectory_loop_guard` is a pure advisor for agent control loops. It
examines typed tool actions and their returned evidence; it does not inspect
model reasoning text, call an engine, cancel work, or resubmit a request.

```python
from action_trajectory_loop_guard import assess_trajectory, detect_and_redirect

intervention = detect_and_redirect(agent_steps)
if intervention is not None:
    preserved_steps = agent_steps[: intervention.truncation_point]
```

For replay-fidelity diagnostics, `assess_trajectory()` returns the canonical,
JSON-safe action stream actually used by the detector, each action's comparison
window, near-duplicate matches, evidence counts, novelty, redundancy decision,
and the proposed intervention. Its serialized `actions` can be passed directly
back to `assess_trajectory()` without reconstructing events from a run record.

When enabled through `agent_lib`, this data is recorded incrementally under
`run.meta["action_guard"]["detector_trace"]`. The NAV replay script prefers that
captured stream and reports decision mismatches; it falls back to reconstructed
run steps only for older records.

The input can be `agent_lib.AgentStep` objects or their serialized mappings.
The detector currently requires two consecutive low-novelty near-duplicate
actions after an eight-tool-action warmup. Reads are compared by canonical path
and range overlap; evidence novelty is measured from returned `(path, line)`
coordinates. Search/list actions use their normalized arguments and returned
paths or evidence coordinates.

Historical run-record replay passed the original four-trajectory gate, but a
live seed0 smoke test did not reproduce the recorded seed0 firing. Treat those
older replay results only as coarse regression fixtures until captured-input
shadow runs establish whether the divergence is model behavior or replay-input
fidelity. The package remains experimental and NAV defaults to shadow mode.

`agent_lib.eval.repo_navigation.build_navigation_harness` is the first active
consumer. Its between-step hook owns context selection, strict single-shot
finalization, budget preflight, and telemetry; this package remains a pure
detector/advisor.
