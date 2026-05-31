# Build Spec — Relocate `diagnostics_agent` to `examples/`

**Type:** repository restructure (file move + config/doc updates). No source-logic
change. No import-statement change (nothing imports `diagnostics_agent` as a
package; verified).
**Why:** `diagnostics_agent` fails the MEMBERSHIP "is this a reusable block?" test
— nothing imports it; it is domain-specific (host log diagnostics); it is built
*with* the blocks (`llm_engines`, later `engram`/`llm_inspector`). That makes it an
**example**, the same classification as `language_tutor`. It is currently an active
multi-session campaign, so it is an example in the *campaign* stage, not yet a
frozen reference — state that honestly in its README rather than implying it is
finished.

## Decisions already made (do not relitigate)

- **Code moves to `examples/diagnostics_agent/`.**
- **Campaign/process docs stay at `docs/projects/diagnostics_agent/`** (CAMPAIGN.md,
  DIAGNOSTICS_AGENT_STATUS.md, the PHASE_*/UI/FOLLOWUP specs). These are working
  state, which is what `docs/` is for. Do not move them.
- Follow the **existing `language_tutor` pattern** in the Makefile (it is already an
  example that is installed editable and has its own test target). Do not invent a
  new mechanism.

## Pre-move verification (run first; abort and report if any is non-empty)

```bash
grep -rn "diagnostics_agent" Makefile pytest.ini conftest.py root_pyproject.toml
grep -rn "import diagnostics_agent\|from diagnostics_agent" --include="*.py" . | grep -v "/diagnostics_agent/"
```

Both were empty at spec-writing time. If either now returns hits, stop and list
them — the move plan below assumes no code/config references the root path.

## Steps

### 1. Move the package tree

```bash
git mv diagnostics_agent examples/diagnostics_agent
```

Use `git mv` so history follows. The package keeps its `src/` layout, its own
`pyproject.toml`, and its `tests/` — unchanged.

### 2. Remove the stray tarball

`diagnostics_agent.tar.gz` sits at repo root (a build/handoff artifact). It should
not be tracked.

```bash
git rm --cached diagnostics_agent.tar.gz   # if tracked
rm -f diagnostics_agent.tar.gz
```

Add `*.tar.gz` (or at least `diagnostics_agent.tar.gz`) to `.gitignore` if not
already covered. While there, confirm `*.egg-info/` is gitignored (recurring
backlog item — DIAGNOSTICS_AGENT_STATUS.md open item #6); add it if missing.

### 3. Makefile — mirror the `language_tutor` treatment

- **`install` target:** add a line installing the example editable, matching the
  existing `language_tutor` line (line ~42). Use the new path and the `[dev]` extra
  for tests; the `[ui]` (streamlit) extra stays opt-in, NOT in the default install:

  ```make
  $(PIP) install -e './examples/diagnostics_agent[dev]'
  ```

  Place it after the block packages, alongside the other example(s).

- **Add a dedicated test target** following the `test-tutor` / `test-agent` pattern:

  ```make
  .PHONY: test-diagnostics
  test-diagnostics:
  	cd examples/diagnostics_agent && $(TEST_PYTHON) -m pytest tests/ -v
  ```

  Do **not** fold diagnostics_agent tests into `test-core`. `test-core` is the
  "no torch, no network" block gate; keep it about the blocks. The example gets its
  own named target so its 116-test suite is a runnable gate instead of tribal
  knowledge, without muddying what "core green" means.

- Update the help/echo text (the `make install` success echo around line 45, and
  the header comment block lines 11–15) to mention `test-diagnostics`.

### 4. README path fixes inside the moved package

In `examples/diagnostics_agent/README.md`, update every path that assumed the root
location:

- `cd examples/diagnostics_agent` / `cd ~/ai_tools/examples/diagnostics_agent`
  → `cd examples/diagnostics_agent` / `cd ~/ai_tools/examples/diagnostics_agent`
- the editable-install line `pip install -e ".[ui]"` is fine as-is (relative), but
  any line referencing `~/ai_tools/examples/diagnostics_agent` in the dependency-order
  install block must gain `examples/`.
- the `streamlit run src/diagnostics_agent/ui/app.py` line: the relative path is
  unchanged (still run from inside the package dir), but confirm the surrounding
  `cd` was updated.

Add a short tier note near the top of the README, after the one-line description:

> **Status: active campaign, not a frozen reference.** This example is the current
> co-evolution driver for `ai_tools` (see `docs/projects/diagnostics_agent/`). Its
> public-facing shape may still move. Treat it as a worked, in-progress
> demonstration of composing `llm_engines` (and, in later phases, `engram` /
> `llm_inspector`) — not as a stability-committed library.

### 5. `examples/README.md` — give it real content

This file is currently empty (whitespace only). Add a minimal index listing the
three examples with one line each and their status:

- `language_tutor` — spaced-repetition tutor; composes `llm_engines` + `engram`.
- `agent_coordination_teaching` — `agent_lib` coordination teaching example.
- `diagnostics_agent` — read-only local-LLM system diagnostics; **active campaign**
  (process docs under `docs/projects/diagnostics_agent/`).

Keep it short; this is a signpost, not documentation.

### 6. Update path references in the campaign docs (prose, light touch)

The docs under `docs/projects/diagnostics_agent/` stay put, but any that give a
concrete code path (`DIAGNOSTICS_AGENT_STATUS.md` "Launch reference" block uses
`~/ai_tools/examples/diagnostics_agent`) should be updated to
`~/ai_tools/examples/diagnostics_agent`. Grep the dir and fix path-style refs only;
do not rewrite prose.

```bash
grep -rn "ai_tools/examples/diagnostics_agent\|cd examples/diagnostics_agent\|examples/diagnostics_agent/src\|examples/diagnostics_agent/tests" docs/projects/diagnostics_agent/
```

## MEMBERSHIP.md — document the campaign→example lifecycle (one-line addition)

The current `examples/` entries are finished reference apps; MEMBERSHIP only
describes that finished state. Add a sentence so an in-flight example is documented,
not implicit. In the "Examples: harvest, not port" section (or the verdicts table
notes), add:

> An example may begin as an **active campaign** (in-flight, its own continuity in
> `docs/projects/<name>/`) and graduate to a frozen reference once its shape
> settles. `diagnostics_agent` is currently in the campaign stage. Campaign status
> is declared in the example's README tier note.

Optionally add a row to the verdicts table:
`| diagnostics_agent | example (campaign) | — | n/a | Built with the blocks; code in examples/, campaign docs in docs/projects/. |`

## Acceptance

- `make install` succeeds and installs `examples/diagnostics_agent` editable.
- `make test-core` still green and unchanged in scope (no diagnostics tests pulled
  in).
- `make test-diagnostics` runs the suite: 116 passed, 1 skipped (matching current).
- `.venv/bin/python -c "import diagnostics_agent; print(diagnostics_agent.__file__)"`
  resolves to `.../examples/diagnostics_agent/src/diagnostics_agent/__init__.py`.
- `git status` shows the move as renames (history preserved), the tarball removed,
  no stray references to the old root path:
  `grep -rn "diagnostics_agent" Makefile` shows only the new `examples/` paths.
- `git grep -n "ai_tools/examples/diagnostics_agent"` shows only intended current-path
  references (all old root paths updated to
  `ai_tools/examples/diagnostics_agent`).

## Out of scope

- No change to any `.py` source logic, schema, or prompts.
- No change to the campaign's phase plan or backlog.
- Do not touch the separate question of whether `examples/language_tutor` still
  installs from the old root `./language_tutor` path — flag it if seen, fix
  separately.
