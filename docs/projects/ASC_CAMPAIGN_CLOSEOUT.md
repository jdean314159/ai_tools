# ASC Campaign Close-out — SPEC-ASC-00 through SPEC-ASC-02

**Status:** Closed as a forcing-function campaign.

## Outcome

ASC exercised the existing runtime, workspace policy, local-model adapter, and
probe harness against deterministic and live local-model tasks. The campaign
found and corrected six **probe-side** defects. It found no defect requiring a
change to `agent_lib` or `llm_engines`.

## Probe defects found and fixed

1. **Oracle validity:** weak checks and held-out expectations were reconciled
   with the stated task contracts, including the square, bucket-label, and
   adjacent-interval cases.
2. **Request timeout:** unavailable models and stalled requests produce durable
   timeout records rather than hanging the experiment.
3. **Checkpoint/resume:** successful task records and an atomic aggregate
   report survive interrupted matrix runs.
4. **Dropped local-model payload variant:** the probe promotes Qwen's nested
   `arguments.tool_name` before it reaches the stable agent action contract.
5. **Step observability:** every run record now persists tool calls, results,
   output, and metadata needed for post-run diagnosis.
6. **Dual visible-oracle confound:** behavioral-test tasks expose only their
   pytest oracle; containment checks are reserved for containment-only tasks.

## Library-gap verdicts

- **#3 cost cap — not forced.** The completed old-set same-model-review runs
  had bounded two-escalation recoveries; no escalation loop exceeded the
  runtime step bound or showed an economically uncontained retry pattern.
- **#4 typed approve/revise/redirect — not forced.** In the same runs, the
  free-text critic takeover recovered objective failures and completed without
  observed thrashing.

These verdicts rest on the completed old-set same-model-review data, where the
critic genuinely engaged following failed objective tool results. They do not
claim that the gaps can never matter; a future concrete failing run is the
mandate for either capability.

## Stopping condition

The campaign's objective was library exercise, not a permanent integrity
benchmark. It produced clean live telemetry after the probe defects were
removed, and no library-side defect was forced. Further task expansion should
begin only if a consuming application surfaces a concrete failure that the
current libraries cannot express or recover from.
