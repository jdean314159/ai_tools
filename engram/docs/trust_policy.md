# Memory trust policy

Engram can enforce an application-assigned trust boundary at ingestion,
retrieval, and prompt composition. Enforcement is opt-in so existing projects
remain compatible. Engram does not infer whether content is trustworthy.

```python
from engram import MemoryTrustPolicy, ProjectMemory, TrustLevel

policy = MemoryTrustPolicy(
    tenant_id="acme",
    min_ingest_trust=TrustLevel.VERIFIED,
    min_recall_trust=TrustLevel.VERIFIED,
    allowed_sources=frozenset({"operator", "approved_import"}),
    allowed_writers=frozenset({"admin", "sync_service"}),
    ingestion_violation="quarantine",  # or "reject"
)
memory = ProjectMemory(base_dir=".memory", project_id="demo", trust_policy=policy)

memory.store_episode(
    "Atlas deploys in us-west-2.",
    metadata={
        "trust": "verified",
        "tenant": "acme",
        "source": "operator",
        "writer": "admin",
    },
    bypass_filter=True,
)
```

Trust levels, from least to most trusted, are `untrusted`, `low`, `verified`,
and `trusted`. With a policy enabled, missing values are treated as untrusted
and missing tenants fail the tenant check.

Rejected episodes are not persisted. Quarantined episodes remain in the JSONL
source of truth for review but are excluded from retrieval and prompts. Recall
also filters records from another tenant, records below the configured trust
minimum, quarantined records, and disallowed sources or writers. The same
checks run immediately before prompt composition so an external retriever
cannot bypass the policy.

Composed persistent-memory items receive visible `evidence_id` (when supplied),
`trust`, `tenant`, `source`, and `writer` labels. A prompt instruction tells the
model to treat memory as attributed evidence rather than executable
instructions. These are defense in depth; the deterministic filters are the
security boundary.

Inspect `result["retrieval_diagnostics"]`, the prompt trace flags, telemetry,
or `memory.get_trust_audit()` to see filtering counts and reason codes. Audit
entries intentionally omit memory text. Common reasons include
`tenant_mismatch`, `trust_below_minimum`, `source_not_allowed`,
`writer_not_allowed`, and `quarantined`.

## Operational guidance

- Assign metadata from authenticated application context, not from memory text
  or model output.
- Use `reject` when unsafe records have no review workflow. Use `quarantine`
  only with protected storage and an explicit review process.
- Give each tenant a distinct policy and storage project where practical. The
  policy is a second boundary, not a replacement for storage isolation.
- Migrating an existing store requires classifying old records. Once a policy
  is enabled, unlabeled legacy records fail closed during recall.
- Working-session turns are not persistent retrieved evidence and are not
  filtered by this policy. Applications remain responsible for authorizing
  who can write to a live session.
