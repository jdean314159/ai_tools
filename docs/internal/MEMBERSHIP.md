# MEMBERSHIP — what belongs in ai_tools

**Date:** 2026-05-22
**Status:** Active governance rule
**Purpose:** Prevent scope drift. Every package, app, and doc in this repo must
justify its place against the rule below. This document is the admission filter
and the current verdict for each entry.

---

## Why this exists

The repo accumulated crud because nothing said *no* at the boundary. The heavy
`engram` runtime and `engram_ui` are the visible cost of a drifting set of goals.
Cleaning them up once is not enough — without a standing rule, the drift recurs.
This document is that rule, plus its application to the current contents.

The repo's goal is now explicit: **`ai_tools` is a set of reusable tools that
others can use to build their own LLM-based projects.** Everything is judged
against that goal.

---

## The membership rule

For anything proposed to live in `ai_tools`, ask:

> **Is this a reusable building block, or something built *with* the blocks?**

- **Block** — a reusable library an outside developer imports. Stays as a package.
- **Tool** — a general-purpose application that ships with the kit (not tied to
  one domain). Stays.
- **Example** — something built *with* the blocks. Lives in `examples/`, and must
  be built against the public API (see "Harvest, not port" below).
- **Out** — fails the rule. Archived or moved to its own repo.
- **Infra** — repo scaffolding (build, test, CI, docs). Necessary, but kept at
  the edges, not the center.

If a thing cannot answer *"what reusable capability does this give an outside
developer?"*, it is not a block.

---

## Maturity tiers

Every block declares a tier in its README. Honesty here is part of usability —
a user must know what they can rely on and what will move under them.

- **stable** — public API committed; breaking changes are versioned and rare.
- **beta** — usable, public API mostly settled, may still shift.
- **experimental** — do not build on this expecting stability.

Overselling an experimental package as ready is *anti*-usability.

---

## Public API requirement

Every block must define:

1. **Scope** — one sentence on what it does and explicitly does not.
2. **Public API** — explicit `__all__`, a documented "import this, call that"
   entry point, internals clearly marked.
3. **Tier** — stable / beta / experimental, stated in the README.

**Falsifiable bar for "usable":** a stranger can `pip install` one package, read
its README, and build something useful in 15 minutes without reading the source.
If they must read source to use it, the public API or quickstart is not done.

---

## Current verdicts

| Entry | Verdict | Tier | Public API entry point | Action |
|---|---|---|---|---|
| `llm_harness_core` | block | stable | interop contracts / primitives | Document contracts as the public surface. |
| `llm_engines` | block | stable | engine factory / engine interface | Flagship "import and go" package. |
| `engram` | block | beta | `ProjectMemory` | Mark the six memory layers internal. |
| `rag_lib` | block | beta | pipeline object | Mark chunkers / rerankers internal. |
| `llm_inspector` | block | beta | trace / inspection API | Value gated by trace-taxonomy work. |
| `llm_inspector_ui` | tool | beta | run as workbench | General dev tool. Add chat panel (ADR-010). |
| `agent_lib` | block | **experimental** | coordination primitives | Mark experimental loudly. Do not oversell. |
| `language_tutor` | example | — | `examples/language_tutor_reference_app` | Recovered full app harvested against current public APIs; smaller public-API example remains separate pending later consolidation. |
| `diagnostics_agent` | example (campaign) | — | n/a | Built with the blocks; code in `examples/`, campaign docs in `docs/projects/`. |
| `netflow_behavior_lab` | out | — | n/a | Extracted 2026-06-20 to sibling repo `../netflow_behavior_lab` because it is a deterministic network-analysis research project with zero `ai_tools` coupling. |
| `engram_ui` | out | — | n/a | Archive (ADR-010). |
| `course/` | out | — | n/a | Split to its own repo (last step). |
| ASC | example (rebuild, later) | — | n/a | Built with `agent_lib`; gated on `agent_lib` reaching beta. |

### Notes on judgment calls

- **`llm_inspector_ui` is a tool, not a block.** It is run, not imported, but it
  is domain-agnostic (works against any engine/augmenter), so it stays. The
  contrast with `language_tutor` is that the tutor is domain-specific, which makes
  it an example.
- **ASC is never a peer package.** It is built with `agent_lib`, so it is an
  example or it moves out — never a block. Because `agent_lib` is experimental,
  an ASC example is deferred until `agent_lib` is at least beta.

---

## Examples: harvest, not port

Examples are documentation. A ported-as-is app imports whatever internal surfaces
it was built against and teaches users to reach into internals — and rots faster
than prose because it is executable. Examples must therefore be **built against
the final public API**, not migrated from earlier internal versions.

An example may begin as an **active campaign** (in-flight, with its own continuity
in `docs/projects/<name>/`) and graduate to a frozen reference once its shape
settles. `diagnostics_agent` is currently in the campaign stage. Campaign status
is declared in the example's README tier note.

- **Port** = move files, fix imports. **Forbidden** for examples.
- **Harvest** = extract the domain logic that is independent of how the app talks
  to `ai_tools`; rewrite the integration glue against the public API.

For `language_tutor`, harvest: SM-2 spaced repetition, Duolingo import +
enrichment, pronunciation scoring, Piper/whisper voice plumbing. Rewrite: every
call into `engram` and `llm_engines`.

For ASC, harvest: tmux orchestration, mailbox integration, worker-profile launch.
Rewrite: every call into `agent_lib` and `engram`.

### The rebuild is the API acceptance test

*"Can I build the tutor using only the public surface, without reading library
source?"* is the gate that proves a block's public API is done. If the rebuild
forces a reach past the public API, the API is incomplete — and the gap is found
before a stranger hits it. The same validation logic as the course split, one
level down.

---

## Documentation discipline

Doc sprawl is the same drift as package sprawl. The top level is for users, not
for working notes.

**Top level (user-facing):** `README.md`, `LICENSE`, `CONTRIBUTING.md`, `docs/`.

**`docs/internal/` (working/process):** `STATUS`, `ROADMAP`, `VISION`,
`NEXT_THREAD_HANDOFF`, `QUALITY_CLEANUP_PLAN`, `GITHUB_PUBLICATION_CHECKLIST`,
`PACKAGE_ROLES`, this file. ADRs stay in `adr/` with `ADR_INDEX.md`.

**With `agent_lib` or `docs/internal/`:** `AGENT.md`, `AGENT_FILE_SPEC.md`,
`TASK_MANIFEST_SPEC.md` — these are tied to the agent work, not the repo root.

---

## Execution sequence

The order compounds correctly; do not reorder.

1. **Finish consolidation** — ADR-010 (archive engram_ui), root doc sync, clean
   baseline, fresh-clone verification.
2. **Apply this filter** — sort every entry per the verdicts above; freeze
   `language_tutor` and ASC as reference sources.
3. **Define public APIs + tiers** — scope, `__all__`, quickstart README per block.
4. **Rebuild the flagship example** — `language_tutor` in `examples/`, harvested
   and rewritten against the public API. This validates step 3.
5. **Split the course** to its own repo, consuming `ai_tools` as an external
   dependency. Passing this cleanly proves steps 3–4 succeeded.

ASC as an example comes after `agent_lib` reaches beta; it does not block
publication.

---

## Loose ends caught by the filter

- `update_engram.sh` — deleted after consolidation.
- `artifacts/` — treated as generated output; gitignored and untracked.
- `LICENCE.txt` — resolved in favor of `LICENSE`.
