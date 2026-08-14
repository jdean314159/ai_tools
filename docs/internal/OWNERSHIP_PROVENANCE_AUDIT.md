# ai_tools ownership and provenance audit

**Date:** 2026-08-14  
**Status:** Open — repository evidence collected; owner declarations required  
**Purpose:** Determine whether the current publication tree may be licensed as
Apache-2.0. This is an engineering provenance audit, not legal advice.

## Scope

The audit covers the entire tracked publication tree, not only the seven core
LLM packages. Fourteen tracked `pyproject.toml` files currently define
distribution candidates:

| Distribution | Path | Current license metadata |
|---|---|---|
| `action-trajectory-loop-guard` | `action_trajectory_loop_guard/` | MIT |
| `agent-lib` | `agent_lib/` | MIT |
| `engram` | `engram/` | MIT |
| `diagnostics-agent` | `examples/diagnostics_agent/` | absent |
| `language-tutor-example` | `examples/language_tutor/` | absent |
| `language-tutor` | `examples/language_tutor_reference_app/` | absent |
| `ai-tools-mail-assistant-example` | `examples/mail_assistant/` | absent |
| `llm-engines` | `llm_engines/` | MIT |
| `llm-harness-core` | `llm_harness_core/` | MIT |
| `llm_inspector` | `llm_inspector/` | MIT |
| `llm-inspector-ui` | `llm_inspector_ui/` | MIT |
| `mail-lib` | `mail_lib/` | MIT |
| `rag-lib` | `rag_lib/` | MIT |
| `reasoning-loop-guard` | `reasoning_loop_guard/` | MIT |

The root `LICENSE` is MIT. Commit `50eb4a2` changed four package metadata
declarations from Apache-2.0 to MIT to match that root, but did not record the
license-direction decision in an ADR.

## Repository-grounded findings

### Contributor identity

`git shortlog -sne --all` reports three display names, all using
`jdean314159@gmail.com`:

- Jeffrey Dean
- Jeff Dean
- jdean314159

No other Git author email appears for current tracked blobs. This establishes
the recorded commit identity only. It does **not** establish copyright
ownership, authority to relicense predecessor work, or the absence of
work-for-hire obligations.

### Current third-party source

The only current tracked artifact identified as vendored source is
`examples/mail_assistant/static/htmx.min.js`:

- upstream: `bigskysoftware/htmx` 2.0.4;
- license: Zero-Clause BSD;
- exact SHA-256 and upstream URL recorded in
  `examples/mail_assistant/static/HTMX-PROVENANCE.txt`;
- local bytes match that digest as of this audit;
- license text is preserved in `THIRD_PARTY_NOTICES.md`.

No Git submodule or Git LFS object is present.

The tracked SQLite and mbox fixtures under `tests/fixtures/mail_lib/` use the
reserved `.test` domain and explicitly synthetic names and message bodies. No
real mailbox content was observed in the inspected fixture strings. They are
generated test data, not an imported mail corpus.

### Historical third-party source

Commit `3d7ee71` imported `asc/mcp_agent_mail/` and
`asc/super-claude-kit/`; commit `3dceb3e` removed them. They remain reachable
in Git history but are absent from the current tree and current wheels. Their
MIT attributions are preserved in `THIRD_PARTY_NOTICES.md`.

A prior comparison recorded in `THIRD_PARTY_NOTICES.md` found no nonempty
exact-file or normalized six-line-block match between the current tree and the
four reviewed `Toms_coder` repositories. A fresh SHA-256 comparison during
this audit likewise found no nonempty exact-file match against the current
local `Toms_coder` trees. These results answer that known-source question;
they are not proof of independent authorship across the whole tree.

### Internal predecessor and recovered code markers

Current source explicitly identifies these predecessor relationships:

- `llm_engines/router.py` was ported from Engram's router;
- `llm_engines/utils/structured_output.py` was adapted from mature Engram
  utility code;
- `examples/language_tutor_reference_app/` contains files ported or adapted
  from the standalone `spanish_tutor` project;
- `engram/neural/core.py` implements Dean (1994) subgrouped RTRL and was
  introduced by recovery commit `3dceb3e`; the handoff describes the neural
  core as vendored/reintroduced;
- `engram/neural/surprise_filter.py` cites TITANS papers as design sources.

All corresponding commits carry the same Git email identity listed above.
That supports a same-maintainer lineage but does not prove that the maintainer
owns every predecessor implementation or has authority to relicense it.

### Dependencies versus copied source

Ordinary declared Python dependencies are linked/imported dependencies and
are not included in this repository merely because a `pyproject.toml` names
them. They retain their own licenses. This audit separately concerns source or
assets copied into the publication tree.

## Declarations required to close the audit

The copyright owner must confirm all of the following:

1. The three Git display names above identify the same person.
2. That person owns, or is authorized to relicense, the current `ai_tools`
   source attributed to that identity.
3. The predecessor Engram implementation and the standalone `spanish_tutor`
   material were owned by that person or incorporated with relicensing rights.
4. The recovered RTRL/TITANS implementation is an original implementation the
   person may license, not copied code governed by an unrecorded license.
5. No employer, client, institution, collaborator, or other party owns any
   portion of the current publication tree or restricts its relicensing.
6. No other copied source or asset is known beyond the items recorded above.

A negative or uncertain answer does not imply the whole repository cannot be
published. It means the affected path must be identified, attributed, kept
under its compatible original license, replaced, or removed before the root
license changes.

## Packaging defects to repair after ownership closes

- Replace the root MIT license with the canonical Apache-2.0 text.
- Use PEP 639 `license = "Apache-2.0"` consistently for every distribution
  shipped from this repository.
- Add `license-files` configuration and verify the exact license files inside
  every wheel and source distribution.
- Do not create an Apache `NOTICE` file accidentally. The existing
  `THIRD_PARTY_NOTICES.md` remains attribution bookkeeping unless a later
  explicit decision designates or replaces it as `NOTICE`.
- Rebuild all distributions and inspect `License-Expression` and included
  license files before publication.

## Current gate

ADR-023 is Proposed. Do not change license text or package declarations until
the six owner declarations above are answered and recorded. The separate
`llm-failure-lab` repository remains MIT by deliberate design.

## Primary references

- Apache License 2.0: <https://www.apache.org/licenses/LICENSE-2.0.txt>
- Python Packaging User Guide, license metadata and files:
  <https://packaging.python.org/en/latest/guides/writing-pyproject-toml/#license-and-license-files-pep-639>
