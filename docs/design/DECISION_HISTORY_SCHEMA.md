# Decision History Metadata Schema

**Status:** Version 1
**Date:** 2026-06-13

## Purpose

Decision-history metadata preserves why a hypothesis looked promising, what
application was evaluated, and its current disposition. It is deterministic
metadata recorded at decision time, not a reconstructed knowledge base.

Existing ADRs remain valid without this metadata. Add it incrementally when an
ADR is created or materially revised.

## Front Matter

An ADR may begin with YAML front matter:

```yaml
---
decision_history_version: 1
hypotheses:
  - id: example-hypothesis
    application_scope: example-application
    resolution_status: unresolved
    mechanism_status: not_demonstrated
    mechanism_evidence: []
    earlier_support:
      basis: Display-only explanation of why the hypothesis was considered.
      evidence:
        - docs/example.md#supporting-heading
    resolution_evidence: []
    superseded_by: null
    current_guidance: Display-only current guidance.
---
```

## Closed Vocabularies

`resolution_status`:

- `supported`
- `qualified`
- `contested`
- `resolved_against`
- `unresolved`
- `historical`

`mechanism_status`:

- `operational`
- `not_demonstrated`
- `not_applicable`

The decision key is the exact pair `(id, application_scope)`. Identifiers use
lowercase kebab case. Application scope must name the concrete role being
decided, not only a package or subsystem.

## Logic Boundary

Only closed enums, identifiers, and references affect validator logic.
`earlier_support.basis` and `current_guidance` are display-only. Validators and
renderers must never infer a status, contradiction, or relation from their
prose.

The schema records hypothesis/application dispositions. It does not record
parameter-level reversals such as changing `value_dim` from 64 to 32; those
remain in ADR prose.

## Evidence Rules

- `mechanism_status: operational` requires at least one
  `mechanism_evidence` reference.
- `not_demonstrated` and `not_applicable` require
  `mechanism_evidence: []`.
- `resolved_against` requires at least one `resolution_evidence` reference.
- Every referenced path must resolve inside the repository.
- A `#fragment` must match a generated heading slug in the referenced Markdown
  file.

Successful validation means references resolve. It does not verify that a
referenced document actually supports the associated claim; that remains a
human responsibility at write time.

## Heading Slugs

The repository pins this GitHub-style subset:

1. remove Markdown heading markers;
2. lowercase the heading;
3. remove punctuation except `_`, `-`, and whitespace;
4. replace each whitespace character with `-`;
5. preserve repeated hyphens;
6. suffix duplicate slugs with `-1`, `-2`, and so on in document order.

Headings inside fenced code blocks are ignored.

## Contradictions

The validator checks exact-key collisions only. Two records with the same
`(id, application_scope)` and different `resolution_status` values are an
error. It performs no cross-hypothesis or semantic contradiction inference.

## Supersession Boundary

`superseded_by` identifies the ADR controlling the hypothesis/application
disposition. It does not represent parameter changes or imply semantic
relationships between differently keyed hypotheses.
