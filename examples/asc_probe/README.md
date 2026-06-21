# ASC Probe

Disposable Phase 0/0.5 probe for the existing `agent_lib` worker/mentor loop.

This is not a finished ASC example. It provides a tiny refactoring fixture and a
deterministic harness that uses the current `AgentRuntime` plus programming
workspace tools to verify what the loop already does and which gaps are forced
by concrete runs.

Generated run artifacts belong under `examples/asc_probe/runs/`, which is
gitignored.

## Live integrity probe

`live_probe.py` drives the existing runtime with a local Ollama worker.  Its
headline condition is `worker-only`; `same-model-review` is deliberately
labelled as an escalation-mechanics condition, not independent mentor evidence.

```bash
python examples/asc_probe/live_probe.py --seeds 5 --mode both
```

Each run receives a visible weak check and a harness-owned held-out behavioral
oracle on disjoint inputs. The worker may edit only `target.py`; held-out
oracles are executed by the harness after the run and are never placed in the
workspace. Reports include visible/held-out outcomes, tamper attempts,
special-casing flags, escalation counts, model/quantization metadata, and raw
Ollama thinking payloads in ignored run artifacts.
