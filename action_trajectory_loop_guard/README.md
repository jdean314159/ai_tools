# action-trajectory-loop-guard

`action_trajectory_loop_guard` is a pure advisor for agent control loops. It
examines typed tool actions and their returned evidence; it does not inspect
model reasoning text, call an engine, cancel work, or resubmit a request.

```python
from action_trajectory_loop_guard import detect_and_redirect

intervention = detect_and_redirect(agent_steps)
if intervention is not None:
    preserved_steps = agent_steps[: intervention.truncation_point]
```

The input can be `agent_lib.AgentStep` objects or their serialized mappings.
The detector currently requires two consecutive low-novelty near-duplicate
actions after an eight-tool-action warmup. Reads are compared by canonical path
and range overlap; evidence novelty is measured from returned `(path, line)`
coordinates. Search/list actions use their normalized arguments and returned
paths or evidence coordinates.

These defaults passed the declared NAV-TEST-00 gate: detection before 120K on
seed0 and sampled seeds 1/3, with no fire on successful sampled seed2. The
four-run gate is small, so the package remains experimental.

`agent_lib.eval.repo_navigation.build_navigation_harness` is the first active
consumer. Its between-step hook owns context selection, strict single-shot
finalization, budget preflight, and telemetry; this package remains a pure
detector/advisor.
