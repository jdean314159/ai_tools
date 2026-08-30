# Engram trust-policy implementation

Date: 2026-08-30

## Why this change exists

The frozen five-case memory-security characterization showed that explicitly
untrusted records crossed storage, retrieval, and prompt-composition boundaries
in 5/5 cases. The tested Qwen model resisted all five prompt attacks, but model
behavior is not an enforceable security boundary.

## Implemented boundary

`MemoryTrustPolicy` is an opt-in, application-assigned policy over four metadata
fields: trust, tenant, source, and writer. It provides:

- ordered, typed trust levels;
- fail-closed validation of missing or insufficient trust and tenant metadata;
- reject or quarantine ingestion behavior;
- retrieval filtering for persisted episodes;
- a second composition filter covering custom/external retrievers;
- visible provenance labels and a memory-as-evidence prompt instruction;
- privacy-minimized audit entries, telemetry, and prompt diagnostics.

The implementation does not attempt to infer trust from content. Working
session turns remain outside the persistent-memory policy, and storage-level
tenant separation is still recommended as the primary isolation boundary.

## Compatibility

No policy is installed by default. Existing callers retain their prior storage,
retrieval, and prompt behavior. Once a policy is enabled, unlabeled legacy
records fail closed during recall and must be classified before use.

## Verification

Focused policy and adjacent Engram tests passed: 31 tests. The three frozen
memory-security artifact tests also passed. The repository suite passed with
1,228 tests, 301 skips, and three existing multiprocessing deprecation warnings.

## Live validation

The paired DGX Spark experiment is complete. Policy-on eliminated poison
storage, retrieval, and prompt inclusion in all five frozen cases. An initial
citation regression exposed a missing `evidence_id` in visible provenance
labels; after correction, the final run passed both security and exact-output
utility gates in 5/5 cases. The complete disclosed run history is in
`docs/projects/ENGRAM-TRUST-POLICY-LIVE-VALIDATION-2026-08-30.md`.
