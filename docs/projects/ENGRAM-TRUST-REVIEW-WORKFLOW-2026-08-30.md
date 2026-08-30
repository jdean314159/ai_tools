# Engram trust review workflow — 2026-08-30

## Motivation

The live availability characterization found no unexpected rejection among
three fully conforming records, but five legitimate workflow cases were
unavailable. The most direct missing capabilities were explicit tenant aliases
and a controlled path for classifying existing records or releasing reviewed
quarantine.

## Implemented surface

`MemoryTrustPolicy.tenant_aliases` accepts only explicit, normalized aliases.
Aliases pass the tenant boundary but do not alter stored tenant provenance.

`ProjectMemory.review_episode_trust(...)` operates on one exact episode ID and:

- requires an enabled trust policy and a non-empty reviewer;
- re-runs ingestion and recall checks over the proposed classification;
- makes no persistent change when checks fail;
- requires `release_quarantine=True` to clear quarantine;
- persists reviewer, review time, and API-appended history in JSONL;
- mirrors metadata into Chroma when configured; and
- emits privacy-minimized audit and telemetry events.

The API does not authenticate reviewers. Authentication and authorization are
application responsibilities, stated explicitly in the API documentation.
The JSONL history is inspectable but not tamper-evident; applications needing a
compliance audit must also send telemetry to a protected external sink.
Bulk migration, alias discovery, and automatic trust promotion are intentionally
not provided because they would weaken the exact, reviewable boundary.

## Verification boundary

Unit tests cover alias authorization, legacy classification across cold reopen,
failed non-mutating release, and successful explicit release. Existing
security, temporal, prompt, and availability probes remain regression gates.
