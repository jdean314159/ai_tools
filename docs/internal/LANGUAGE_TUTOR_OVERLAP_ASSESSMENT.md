# Language-tutor overlap assessment

**Date:** 2026-08-31
**Status:** Decision accepted; superseded by single-application consolidation.

## Decision

Keep `examples/language_tutor_reference_app` as the sole application. The user
selected retirement of `examples/language_tutor` instead of narrowing it to a
tutorial. Retire the reference-app generator rather than maintaining another
embedded application copy.

This preserves two distinct teaching levels instead of two competing apps:

- the tutorial proves direct use of public `engram`, `llm_engines`, and
  `llm_harness_core` surfaces; those imports are visible in
  `examples/language_tutor/session.py:12-20`, and the public-surface assertions
  are in `examples/language_tutor/test_language_tutor.py:70-73`;
- the reference app remains the composed HTTP/UI integration vehicle, the role
  explicitly assigned in `examples/language_tutor_reference_app/README.md:28-39`
  and supported by its documented architecture at lines 81-104.

## Confirmed overlap

The small example currently claims the breadth of an application, not a narrow
tutorial: drills, persistence, voice-shaped behavior, history, stats, a web UI,
and numerous HTTP endpoints are listed in
`examples/language_tutor/README.md:33-70`. Its single full-flow test exercises
those same features at `examples/language_tutor/test_language_tutor.py:14-67`,
and its graphical test covers a second web surface at lines 76-110.

The reference app owns those obligations already:

- its source layout assigns web, session, persistence, drills, voice, routes,
  and templates explicitly (`examples/language_tutor_reference_app/README.md:81-104`);
- its supported HTTP surface is enumerated at
  `examples/language_tutor_reference_app/README.md:186-202`;
- its package is expressly the integration test vehicle at lines 206-222.

The implementations are not interchangeable. The tutorial directly constructs
`ProjectMemory` and combines planning, persistence, drills, and traces inside
`LanguageTutor` (`examples/language_tutor/session.py:89-124`). The reference app
instead owns a `TutorMemoryBackend` protocol and Engram adapter in
`examples/language_tutor_reference_app/src/language_tutor/memory_backend.py:8-108`.
Consolidation should therefore narrow the tutorial, not copy classes between
the trees.

## Exact future file map

No file in this map is changed by this assessment.

### Small public-API tutorial

| Disposition | Paths | Reason |
|---|---|---|
| Keep, simplify | `README.md`, `session.py`, `test_language_tutor.py` | Document and test only start → turn → interop/public-contract behavior. |
| Keep | `LICENSE`, `pyproject.toml`, `__init__.py`, `_bootstrap.py`, `run_demo.py`, `stub_engine.py` | Packaging, direct-checkout support, deterministic CLI execution, and a fake public engine remain tutorial infrastructure. |
| Delete after `session.py` is narrowed | `drills.py`, `profiles.py`, `store.py` | These implement application-domain breadth already owned by the reference app. Retain only a tiny inline tutorial configuration; do not transplant reference-app content. |
| Delete | `web_app.py`, `web_index.html` | A second FastAPI/UI application conflicts with the reference app's canonical role. |
| Delete after checking for unique migration facts | `API_CHANGES.md` | Historical migration notes should not remain as tutorial product documentation; move any still-relevant architectural fact to the assessment or an ADR first. |

The retained tutorial test should assert public import provenance, deterministic
start/turn behavior, memory provenance, and `OperationResult`/trace output. It
should stop asserting drills, audio, SQLite history, stats, and web routes.

### Canonical reference application

| Disposition | Paths | Reason |
|---|---|---|
| Keep | `src/language_tutor/**`, `tests/**`, `README.md`, `REFERENCE_APP_GUIDE.md`, `LICENSE`, `MANIFEST.in`, `pyproject.toml`, `main_example.py`, `start.sh` | These are the canonical application, its verification, packaging, and entry surfaces. |
| Replace with a short redirect or archive its remaining future items | `TODO.md` | It mixes a mostly completed historical tracker with future XTTS and deployment ideas (`TODO.md:120-152`). Current future work belongs in repo project planning, not a second authoritative tracker. |
| Delete | `create_language_tutor_project.py` | The generator embeds an obsolete incomplete application: it emits missing-content TODOs (`:240-279`), unmounted routes (`:700-727`), nonfunctional echo UI handlers (`:1007-1052`), stale project status (`:1254-1260`), and a license statement inconsistent with this repository (`:1262-1265`). |

### Move map

- Move still-desired XTTS and deployment questions from `TODO.md:124-152` to a
  single future-work section in `REFERENCE_APP_GUIDE.md` or the repo roadmap.
- Move no Python, HTML, or JavaScript files between the two implementations.
- Add a link from the small tutorial README to the canonical reference app, and
  a reciprocal “minimal tutorial” link from the reference-app guide.

## Must be built (does not exist yet)

- A narrowed tutorial session object that demonstrates only public engine,
  memory, and interop composition. The current `LanguageTutor` depends on the
  modules proposed for deletion (`examples/language_tutor/session.py:22-24`),
  so deletion cannot precede this replacement.
- Focused tutorial tests replacing the current broad full-flow and web tests.
- A concise future-work home for the still-active items in `TODO.md`.
- Cross-links that make the tutorial/reference-app distinction explicit.

## Assumptions to verify before implementation

- Search external documentation and downstream repositories for imports of
  `examples.language_tutor` or invocations of its web app. This assessment only
  establishes in-repository ownership.
- Read `API_CHANGES.md` end to end and preserve any architectural decision not
  already represented by an ADR or current guide.
- Confirm that project generation is not an externally promised workflow. The
  in-repository generator is stale, but external use has not been measured.

## Implementation boundaries

Perform consolidation in separate reviewable commits:

1. narrow and test the small CLI tutorial;
2. remove its redundant domain/web files and add cross-links;
3. relocate valid future-work notes and retire the stale generator.

Do not change canonical reference-app runtime behavior during those commits.

## Implemented outcome

The user selected the simpler single-application outcome after reviewing this
assessment. `examples/language_tutor` was removed rather than narrowed. Its
public-export assertions were retained in the canonical reference-app suite.
The stale embedded generator and redundant task tracker were also removed;
remaining future voice and deployment questions now live in the reference-app
README. Historical evidence above is intentionally retained as the basis for
the decision, even though it cites paths that no longer exist at HEAD.
