# Repository-assessment experiments

This directory retains controlled autonomous repository-assessment evidence.
Model claims, model-gathered evidence, and independent adjudication are kept
separate. Files under `runs/` are exact run evidence or normalized
adjudication records; tools under `tools/` are maintained external graders.

- [Qwen3-Coder known-defect baseline](QWEN3-CODER-30B-A3B-KNOWN-DEFECT-BASELINE-2026-09-06.md)
- [Planner rerun preregistration](QWEN3-CODER-30B-A3B-PLANNER-RERUN-PREREGISTRATION-2026-09-06.md)
- [Planner comparison result](QWEN3-CODER-30B-A3B-PLANNER-COMPARISON-2026-09-07.md)
- [KV-cache comparison preregistration](QWEN3-CODER-30B-A3B-KV-CACHE-COMPARISON-PREREGISTRATION-2026-09-07.md)
- [KV-cache comparison result](QWEN3-CODER-30B-A3B-KV-CACHE-COMPARISON-2026-09-07.md)
- [Ornith 1.5 35B preregistration](ORNITH-1.5-35B-KNOWN-DEFECT-PREREGISTRATION-2026-09-07.md)
- [Ornith 1.5 35B result](ORNITH-1.5-35B-KNOWN-DEFECT-BASELINE-2026-09-07.md)
- [Ornith staged-assessment preregistration](ORNITH-1.5-35B-STAGED-ASSESSMENT-PREREGISTRATION-2026-09-07.md)
- [Ornith staged-assessment result](ORNITH-1.5-35B-STAGED-ASSESSMENT-2026-09-07.md)
- [Adaptive staged v2 plan](ORNITH-ADAPTIVE-STAGED-V2-PLAN-2026-09-07.md)
- [Adaptive staged v2 preregistration](ORNITH-ADAPTIVE-STAGED-V2-PREREGISTRATION-2026-09-07.md)
- [Adaptive staged v2.1 mechanical-repair preregistration](ORNITH-ADAPTIVE-STAGED-V2-1-PREREGISTRATION-2026-09-07.md)
- [Adaptive staged v2.2 mechanical-repair preregistration](ORNITH-ADAPTIVE-STAGED-V2-2-PREREGISTRATION-2026-09-07.md)
- [Adaptive staged v2.2 result](ORNITH-ADAPTIVE-STAGED-V2-2-ASSESSMENT-2026-09-08.md)
- [Post-v2.2 next-round recommendation for review](ORNITH-POST-V2-2-NEXT-ROUND-RECOMMENDATION-2026-09-08.md)

The retained temporary metadata is not the production
`repository-assessment/v1` profile. That profile and recorder remain deferred
until an explicit schema draft is accepted.

## Capture habit for future Spark work

Before sending a repository snapshot to a Spark-hosted model, record these
three identities together:

1. the full source commit from `git rev-parse <revision>^{commit}`;
2. its tree from `git rev-parse <revision>^{tree}`;
3. the SHA-256 of the uncompressed `git archive --format=tar` bytes.

After creating the archive, confirm its embedded commit with
`git get-tar-commit-id`. Put the commit, tree, archive digest, archive prefix,
and exact archive command in the preregistration or run metadata before the
model run. Do not reconstruct the tree field after a history rewrite. This is
a local capture practice for temporary experiments, not a new production
artifact schema or an ADR decision.
