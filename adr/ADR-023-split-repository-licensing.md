# ADR-023 — Split repository licensing

**Status:** Accepted
**Date:** 2026-08-14  
**Scope:** `ai_tools` and the extracted `llm-failure-lab` repository

## Context

The teaching material was extracted from `ai_tools` into
`llm-failure-lab`. The repositories now have different reuse patterns:

- `ai_tools` is reusable software infrastructure intended to be consumed as
  libraries and tools;
- `llm-failure-lab` is teaching material intended to be forked, edited, and
  remixed by students and instructors.

The former monorepo used a root MIT license while four package metadata files
had previously declared Apache-2.0. Commit `50eb4a2` aligned those metadata
files to MIT without recording why MIT was selected over Apache-2.0.

## Decision

The ownership declarations in
`docs/internal/OWNERSHIP_PROVENANCE_AUDIT.md` were confirmed by Jeff Dean on
2026-08-14. Therefore:

1. License the `ai_tools` repository under Apache License 2.0.
2. Keep `llm-failure-lab` under the MIT License.
3. Treat the difference as an intentional repository boundary, not metadata
   drift.

Apache-2.0 supplies downstream users with an express patent grant scoped to
claims necessarily infringed by each contributor's contribution, subject to
the license's termination condition. It also states redistribution,
modified-file notice, attribution, contribution, and trademark terms more
explicitly than MIT. Those terms fit reusable infrastructure.

MIT imposes less ceremony on students modifying teaching materials. That fits
the course repository's primary reuse mode. An MIT-licensed course depending
on separately distributed Apache-2.0 libraries is an ordinary permissive
license composition.

## Rejected alternatives

### MIT for both repositories

Rejected provisionally because it leaves patent licensing implicit for the
reusable toolkit and does not preserve the more explicit downstream contract
that motivated the earlier Apache-2.0 package declarations.

### Apache-2.0 for both repositories

Rejected because the course does not need the library's licensing policy, and
Apache-2.0's modified-file notice requirement adds friction to routine student
forking and adaptation.

### One root license plus per-package exceptions

Rejected for the current first-party source because it recreates the metadata
ambiguity this decision is intended to remove. Third-party artifacts retain
their own compatible licenses and attribution.

## NOTICE interpretation

`THIRD_PARTY_NOTICES.md` is not an Apache `NOTICE` file. It records attribution
and provenance. No Apache `NOTICE` file will be created unless a later explicit
decision identifies required informational notices and accepts the resulting
redistribution obligation.

## Preconditions for acceptance

- Close every declaration in the ownership/provenance audit.
- Resolve or remove any path whose relicensing authority is uncertain.
- Enumerate every distribution covered by the repository license.
- Update license metadata using current PEP 639 fields.
- Include and inspect license files in built wheels and source distributions.
- Keep third-party license texts and provenance intact.

## Consequences

The preconditions are closed. The license change was implemented across all
14 distribution build roots and verified by building 14 wheels and 14 source
distributions. Wheel metadata and embedded license bytes matched the accepted
decision. No Apache `NOTICE` file was created.

## References

- Apache License 2.0: <https://www.apache.org/licenses/LICENSE-2.0.txt>
- Python Packaging User Guide, license metadata and files:
  <https://packaging.python.org/en/latest/guides/writing-pyproject-toml/#license-and-license-files-pep-639>
