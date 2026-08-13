# RUN-RECORD-00 Phase 6 — portable artifact bundles

**Status:** Complete, 2026-08-13.
**Scope:** Confined bundle writing, exact-byte attachment integrity,
reader-computed resolution, experiment-child packaging, and Inspector bundle
visibility. No archive format, network/content-URI resolver, redaction engine,
UI, or producer rewrite.

## Result

`llm_harness_core` now owns dependency-free bundle mechanics:

- deterministic UTF-8 artifact serialization;
- atomic creation of a previously absent bundle directory;
- exact-byte SHA-256 attachment verification before publication;
- bundle-relative path and symbolic-link confinement;
- load-time `resolved`, `unresolved`, and `digest_mismatch` observations; and
- explicit handling of intentionally detached attachments.

The portable directory layout is deliberately small:

```text
bundle/
  record.json
  children/<child-record-id>.json
```

`record.json` is the root artifact. Every bundled file must be declared by an
attachment containing a unique ID, unique bundle-relative path, exact digest,
digest algorithm, inclusion intent, requirement, and matching privacy
reference-sensitivity entry. The writer refuses unknown bytes, missing bundled
bytes, digest mismatches, path collisions, and existing output targets.

## Identity boundary

Adding attachment declarations is not treated as a byte-only copy of the Phase
5 experiment. `prepare_experiment_bundle()` creates a new deterministic
experiment artifact identity with a `derived_from` relationship to the
unbundled experiment snapshot. It retains semantic `contains` relationships to
the child runs and adds one optional `child_run_artifact` attachment per
published child.

This avoids the invalid alternative of changing durable attachment declarations
while retaining the source artifact's `record_id`. Repeating preparation from
identical source and child bytes yields the same derived identity; different
child bytes or membership change it.

## Digest scope

The initial portable profile supports SHA-256 over the exact bytes stored in
the attachment file. Artifact children use the same deterministic pretty JSON,
sorted-key, trailing-newline serialization as `dump_artifact()`. Digests are
not computed over an abstract JSON object, filesystem metadata, or a model
identity.

Unsupported digest algorithms resolve as unavailable and cannot be written by
the core writer. Adding algorithms later does not change the declared byte
scope.

## Resolution and safety

Resolution is reader-computed and never persisted back into the artifact.
Missing files, changed bytes, and the location from which a bundle is read are
facts about that copy, not about the immutable record.

The reader resolves both the root artifact filename and attachment paths under
the bundle root after symbolic-link expansion. A symlink escape is unresolved;
it is never followed as trusted bundle content. Inspector reports resolution
status and errors but omits resolved absolute paths from its normal summary so
inspection does not leak a local filesystem location.

An optional detached attachment remains a normal unresolved state and produces
no corruption notice. A bundled unresolved attachment, digest mismatch, or
required detached attachment produces an explicit notice.

## Privacy boundary

Every attachment ID must have a corresponding
`privacy.reference_sensitivity` entry, and stale sensitivity entries are
invalid. Experiment-child bundle preparation conservatively declares each
child reference `unknown`; the child artifact retains its own privacy
declaration. A resolved digest is integrity evidence, not export authorization
or privacy validation.

## Inspector support

`inspect_artifact_path()` accepts either an artifact JSON file or a bundle
directory. For a directory it loads `record.json`, resolves attachments, and
adds sanitized resolution facts and notices to the ordinary kind-specific
inspection. The existing CLI therefore supports:

```text
llm-inspect artifact show /path/to/bundle [--format text|json]
```

## Validation

```text
focused core/adapter/Inspector/integration/API gate: 53 passed
agent_lib + core + Inspector (historical known golden omitted): 238 passed, 8 skipped
committed ASC campaign acceptance: 15/15 child attachments resolved
```

Tests include atomic failure, existing-target refusal, missing files, digest
mismatch, detached optional material, root-artifact traversal, attachment
path/symlink escape, privacy-reference alignment, new derived identity,
tampering detection, Inspector sanitization, and CLI directory loading.

This historical gate omitted the optional-tokenizer-dependent Engram golden
documented in Phase 4. That test now carries a strict conditional `xfail` when
`tiktoken` is absent.

## Gate assessment

Phase 6 closes ADR-021's required bundle-resolution forcing cases for local
directory bundles and proves them on a real experiment. It does not define a
zip/tar interchange format, remote resolver registry, encryption, signing, or
redaction. The next bounded choice should be driven by a concrete consumer:
course fixtures are now viable without a GPU, while signing/export policy and
remote resolution should wait for an actual exchange boundary.
