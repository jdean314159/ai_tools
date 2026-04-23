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
- `engram_lite/`
- `rag_lib/`
- `language_tutor/` later

## First 30 minutes

### 1. Confirm you are in the right repo

```bash
pwd
ls
```

You should see files such as `README.md`, `LEARNING_PATH.md`, and the `course/` directory.

### 2. Install the editable packages

```bash
make install
```

If you only want to read first and install later, that is fine. The next two commands are the fastest way to get a visible result after install.

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
- `llm_harness_core/EVALUATION_WALKTHROUGH.md`

### 6. Open the first notebook

Start with:
- `course/notebooks/01_engine_basics.ipynb`

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
3. `engram_lite`
4. `rag_lib`
5. `language_tutor`
6. `agent_lib` last

## Where to go next

- Want the full teaching sequence? Go to `LEARNING_PATH.md`.
- Want the course assets only? Go to `course/README.md`.
- Want the reference application? Go to `language_tutor/REFERENCE_APP_GUIDE.md` after Stages 1–4.
- Want the workbench? Go to `llm_inspector_ui/WORKBENCH_TEACHING_GUIDE.md`.
