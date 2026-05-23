# START HERE

This is the fastest beginner-safe entry point into `ai_tools`.

Use this file if you are new to the repo and want one guided path instead of choosing among packages.

## Who this is for

**Level:** Beginner

You know basic Python and can run commands in a terminal, but you do not yet know the repo structure.

## What this repo is for

`ai_tools` teaches how to build LLM applications in layers:

1. call a model through a clean interface
2. inspect what happened
3. add memory carefully
4. add retrieval carefully
5. compose those layers into an application
6. study agents only after the earlier layers make sense

## What you can ignore for now

Do **not** start by reading everything at the repo root.

You can safely ignore these at first:

- `adr/`
- `docs/history/`
- agent isolation and red-team reports
- advanced `engram` internals
- `agent_lib` until later
- most release and stabilization reports

Focus first on:

- `README.md`
- `LEARNING_PATH.md`
- `course/`
- `llm_engines/`
- `llm_inspector/`
- `engram/`
- `rag_lib/`
- `language_tutor/` later

## First 30 minutes

### 1. Confirm you are in the right repo

```bash
pwd
ls
```

You should see files such as `README.md`, `LEARNING_PATH.md`, and the `course/` directory.


### 2. Install packages into the project virtual environment

The root `Makefile` creates and uses a project-local `.venv`. Do not install
into the system Python.

#### macOS / Linux

```bash
make install
source .venv/bin/activate
```

Verify that you are using the project virtual environment when running Python
commands manually:

```bash
which python
python --version
```

`which python` should point to `.venv/bin/python`.

#### Windows

The root `Makefile` is primarily maintained for macOS/Linux shell workflows.
On Windows, use WSL/Linux for the smoothest path, or create and activate the
virtual environment manually before installing packages.

```powershell
py -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e .\llm_harness_core[dev]
```
Then install the remaining packages using the order shown in the root
`Makefile`.

If you run Python package installation against the system Python on Debian or
Ubuntu, you may see an `externally-managed-environment` error. That is expected.
Use the project `.venv` created by `make install`.

#### Optional PyTorch / GPU features

The default install does not require PyTorch.

Install PyTorch-backed local ML features only if you want neural memory,
HuggingFace local model execution, sentence-transformers-backed local
embeddings, or optimization experiments.

CPU/default ML extras:

```bash
make install-ml
make test-ml
```

NVIDIA/CUDA path:

```bash
make install-gpu
make test-ml
```

#### Optional PyTorch features

The default install does not require PyTorch.

Install PyTorch-backed local ML features only if you want neural memory,
HuggingFace local model execution, sentence-transformers-backed embeddings,
or optimization experiments.

CPU/default install:

    make install-ml

NVIDIA/CUDA install:

    make install-gpu

If CUDA wheel selection fails, use the official PyTorch install selector
for your OS, Python version, and CUDA/ROCm/CPU target, then rerun:

    make install-ml

#### If activation differs in your shell

If CUDA wheel selection fails, use the official PyTorch install selector for
your OS, Python version, and CUDA/ROCm/CPU target, then rerun `make install-ml`.

If you only want to read first and install later, that is fine. The next two
commands are the fastest way to get a visible result after install.

### 3. Run the smallest starter project

```bash
python course/starter_projects/minimal_chat_app/main.py
```

You should see a minimal chat-app placeholder and a note telling you what the next engineering step would be.

### 4. Run the simplest evaluation walkthrough

```bash
python course/starter_projects/source_grounded_qa/eval.py
```

This shows an important idea early: **LLM applications should be compared and evaluated, not just admired when they produce text.**

### 5. Read the learning path before choosing packages

Open:

- `LEARNING_PATH.md`
- `course/README.md`
- `PACKAGE_ROLES.md`
- `course/CURRICULUM.md`
- `llm_harness_core/EVALUATION_WALKTHROUGH.md`

### 6. Open the first notebook

Start with:

- `course/notebooks/00_llm_fundamentals.ipynb`

Then continue in order.

## What success looks like today

By the end of this first pass, you should be able to say:

- what an engine abstraction is
- why inspection matters
- why evaluation matters
- which parts of the repo are beginner-safe
- which parts should wait until later

## Default beginner path

Use this order:

1. `llm_engines`
2. `llm_inspector`
3. `engram`
4. `rag_lib`
5. `language_tutor`
6. `agent_lib` last

## Where to go next

- Want the full teaching sequence? Go to `LEARNING_PATH.md`.
- Want the course assets only? Go to `course/README.md`.
- Want the reference application? Go to `language_tutor/REFERENCE_APP_GUIDE.md` after Stages 1–4.
- Want the workbench? Go to `llm_inspector_ui/WORKBENCH_TEACHING_GUIDE.md`.
