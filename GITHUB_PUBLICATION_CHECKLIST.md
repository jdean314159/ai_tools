# GitHub Publication Checklist

Last updated: 2026-05-20

## Current publication posture

The repo has been pushed to GitHub and verified through a disposable clone
workflow. The next publication gate is a clean fresh-clone install/test pass.

Use this checklist before treating GitHub as the canonical release snapshot.

## 1. Confirm branch state

From the real working repo, not the disposable clone:

```bash
cd ~/ai_tools
git status --short --branch
git log --oneline --decorate --max-count=5
git remote -v
```

Expected:

- on `main`, not detached HEAD,
- branch up to date with `origin/main`, unless intentional local changes exist,
- no unresolved merge/rebase state.

## 2. Clean generated artifacts

```bash
find . -type d -name '__pycache__' -prune -exec rm -rf {} +
find . -type f -name '*.pyc' -delete
find . -type d -name '*.egg-info' -prune -exec rm -rf {} +
rm -rf .pytest_cache .mypy_cache .ruff_cache
```

## 3. Dry-run Makefile targets

```bash
make -n install
make -n test-core
```

Expected:

- install uses `<repo>/.venv/bin/python -m pip`,
- tests use absolute `<repo>/.venv/bin/python` even after `cd package`,
- no `$(TEST_PYTHON)-m` or `$(TEST_PYTHON)scripts/...` concatenation appears.

## 4. Baseline install and tests

```bash
rm -rf .venv
make install
make test-core
```

Default install should not require PyTorch. Torch-only tests should skip unless
ML extras are installed.

## 5. Optional ML/GPU tests

CPU/default ML extras:

```bash
make install-ml
make test-ml
```

CUDA/GPU path:

```bash
make install-gpu
make test-ml
```

If the CUDA PyTorch wheel index is wrong for the machine, use the official
PyTorch installer guidance for the OS/Python/CUDA target, then rerun
`make install-ml`.

## 6. Import provenance check

```bash
.venv/bin/python - <<'PY'
import engram
print(engram.__file__)
PY
```

Expected path:

```text
<repo>/engram/src/engram/__init__.py
```

Do not publish if this resolves to `engram/__init__.py`, `engram/engram`, or
another obsolete path.

## 7. Hygiene and teaching checks

```bash
PYTHONDONTWRITEBYTECODE=1 python scripts/check_publication_hygiene.py
PYTHONDONTWRITEBYTECODE=1 python scripts/check_teaching_artifacts.py
```

Expected:

```text
Publication hygiene check passed.
```

and no missing notebooks/tutorial examples.

## 8. Fresh clone verification

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

Only edit in `~/ai_tools`. Treat `~/ai_tools_clone_check` as disposable.

## Do not publish if

- branch is detached or mid-rebase,
- default install requires system `python3-torch`, PyTorch, or sentence-transformers,
- `make -n test-core` shows relative `.venv/bin/python` after `cd`,
- publication hygiene fails,
- `import engram` resolves outside `engram/src/engram`,
- generated caches or package metadata are present.
