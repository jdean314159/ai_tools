# Next Thread Handoff — ai_tools

Last updated: 2026-05-20

Use this file to rehydrate the next assistant/thread quickly.

## Current objective

The repo has just gone through GitHub publication recovery and packaging
stabilization. Before new feature work, verify the repo from a fresh clone and
make sure the docs, Makefile, package extras, and import paths all agree.

## What was just accomplished

- GitHub push succeeded after resolving merge conflict, remote divergence,
  detached HEAD / stale rebase confusion, and clone-verification confusion.
- Root `Makefile` was changed to create/use a project-local `.venv` with
  absolute paths.
- `make install` is the default lightweight install path.
- PyTorch is being moved behind explicit ML/GPU extras and Makefile targets.
- Full Engram canonical import path is `engram/src/engram`.
- Old Engram import-shadowing paths such as `engram/__init__.py` and
  `engram/engram` should remain absent.
- `Episode` was split into `engram.memory.episode_types` so base result types
  do not need to import the episodic backend.
- `engram_ui` is top-level at `engram_ui/src/engram_ui`.

## First commands in the next thread

```bash
cd ~/ai_tools
git status --short --branch
git log --oneline --decorate --max-count=5
make -n install
make -n test-core
```

Confirm:

- branch is `main`, not detached HEAD,
- `make -n install` uses `<repo>/.venv/bin/python -m pip`,
- `make -n test-core` uses absolute `<repo>/.venv/bin/python` after `cd`,
- no command contains `$(TEST_PYTHON)-m` or `$(TEST_PYTHON)scripts`.

## Required import check

```bash
rm -rf .venv
make install
.venv/bin/python - <<'PY'
import engram
print(engram.__file__)
PY
```

Expected:

```text
/home/cybernaif/ai_tools/engram/src/engram/__init__.py
```

If it resolves to `/home/cybernaif/ai_tools/engram/__init__.py` or an
`engram/engram` tree, stop and fix import shadowing before continuing.

## Validation gate

```bash
make test-core
python scripts/check_publication_hygiene.py
python scripts/check_teaching_artifacts.py
```

Then verify a disposable clone:

```bash
cd ~
rm -rf ai_tools_clone_check
git clone https://github.com/jdean314159/ai_tools ai_tools_clone_check
cd ai_tools_clone_check
make -n install
make -n test-core
make install
make test-core
```

Only edit in `~/ai_tools`. Delete/recreate `~/ai_tools_clone_check` whenever
checking GitHub state.

## Dependency policy to preserve

- `make install`: default, no PyTorch required.
- `make test-core`: default tests; torch-only tests should skip if torch absent.
- `make install-ml`: PyTorch-backed neural/local-model extras.
- `make install-gpu`: CUDA PyTorch + GPU-oriented extras.
- `make test-ml`: neural/optimization tests that require PyTorch.

Do not put unpublished sibling packages such as `llm-inspector` inside another
package's `dev` extra. The root `Makefile` handles sibling install order.

## Likely next work

1. Run the fresh-clone gate above.
2. If torch is missing, verify the relevant test uses `pytest.importorskip`.
3. If pip tries to install `llm-inspector` from PyPI through `engram[dev]`,
   remove that sibling dependency from `engram/pyproject.toml`.
4. If `import engram` pulls `sentence_transformers`, check that
   `result_types.py` imports `Episode` from `episode_types`, not
   `episodic_memory`.
5. Once validation passes, commit and push a small stabilization commit.
