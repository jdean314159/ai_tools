# llm_inspector_ui — Workbench Teaching Guide

This guide explains how to use `llm_inspector_ui` as a **teaching workbench**, not just as a debug console.

Use it during **Stage 2** of the root `LEARNING_PATH.md`, and again in later stages when comparing baseline, memory, retrieval, and agent runs.

## Teaching objective

A learner using the workbench should be able to answer four questions for any run:

1. What context reached the model?
2. What evidence or retrieved support was exposed for inspection?
3. What changed between the baseline branch and the augmented branch?
4. Did the added complexity improve the result enough to justify its token and system cost?

## Startup panel

Teach learners to distinguish among:

- engine registration
- engine reachability
- model availability
- true readiness for comparison runs

This matters because infrastructure failure should not be confused with memory or retrieval failure.

## Compare panel

Treat the compare panel as the primary classroom surface.

A good comparison walkthrough should include:

- baseline as the control branch
- at least one augmented branch (`engram` or `rag`)
- inspection of the final prompt, not only the final answer
- inspection of evidence and retrieval-stage diagnostics
- explicit discussion of token cost and whether the extra context earned its place

## Retrieval tab

The retrieval tab should teach that RAG is a process, not a magic feature.

Learners should look for:

- how many documents were selected
- whether the selected documents actually answer the question
- whether the events suggest filtering, reranking, or stage-specific loss of relevant evidence

## Agent tab

The agent tab should be used to teach that **successful execution** and **safe execution** are different.

Learners should look for:

- blocked actions
- degraded execution
- approval gates
- whether a fallback path occurred and what that means operationally

## Instructor note

If a learner cannot explain what changed in the prompt or why a branch exposed the evidence it did, do not move on to more advanced orchestration topics yet.


## Beginner explanations mode

Enable **Beginner explanations** when teaching early-stage learners. This keeps the full traces visible, but adds plain-language guidance about what to inspect first and what each panel means.

Use it especially when introducing:

- baseline vs augmented branches
- prompt inspection
- evidence and retrieval relevance
- readiness and setup troubleshooting
- the difference between blocked/degraded execution signals and hard isolation
