# Invalid adaptive staged v2 development attempt

Status: retained, invalid, and excluded from the v2.1 paired comparison.

The seed-17 v1/v2 pair was stopped after v2 failed the frozen structured-stage
and evidence-reference mechanical gates. The active llama.cpp template hid
backend tool-call IDs from model context, while the v2 schema required the
model to cite those IDs. The controller rejected the inaccessible references
and correctly marked the run incomplete.

The endpoint configuration fingerprint was identical before and after the
pair. No later seeds were run. The repair and complete-sequence restart are
frozen in
`../../ORNITH-ADAPTIVE-STAGED-V2-1-PREREGISTRATION-2026-09-07.md`.
