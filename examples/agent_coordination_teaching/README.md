# agent_coordination_teaching

A small teaching example for inspectable coordination between external coding
agents, built as a public ai_tools API consumer.

The slice is intentionally narrow: a planner creates assignments, workers
receive messages, advisory file reservations are recorded, workers are launched,
and every exchange is written to durable artifacts.

## What this is — and isn't

**Is:** a focused demonstration of `agent_lib`'s coordination primitives
(`CoordinationMessage`, `ExternalSessionCoordinator`, mailbox), planner backend
selection via `llm_engines`, multiple worker shapes (mock, Codex CLI, Claude
Code CLI, in-process `llm_engines`), and durable exchange logs with
`llm_harness_core.TraceEvent`.

**Is not** the worker/mentor ASC rebuild described in
`docs/design/AGENT_BUILD_NOTES.md` §4. There is no mentor role, no critic /
verifier, no escalation seam gated on objective signals, no stall detection,
no cost circuit-breaker, no typed worker↔mentor contract, and no long-horizon
loop with termination criteria. This is single-pass fan-out dispatch with
logging. Per the co-evolution rule in §0, the worker/mentor loop gets built
when a concrete run demands it — not before.

**Experimental dependency.** `agent_lib` is marked experimental and its API
may move (see `agent_lib/AGENT.md`). This example exercises that surface; it
is not a stable reference.

## What it demonstrates

- public `agent_lib` coordination primitives
- planner backend selection through `llm_engines`
- planner output parsed via the public `llm_engines.StructuredOutputHandler`
  against a Pydantic schema (no hand-rolled JSON regex parsing)
- mock, Codex, Claude Code, and ai_tools-native `llm_engines` worker adapters
- a live console monitor with full-message inspection
- `llm_harness_core.TraceEvent` export
- run manifests and append-only exchange logs

## Isolation status (read this before pointing real workers at a real workspace)

This example does not provide its own isolation. Per ADR-011, that is
insufficient for an autonomous worker loop. Concretely:

- **Codex worker** uses `codex exec --sandbox workspace-write --ask-for-approval
  on-request` — the Codex CLI's own sandbox does real work here.
- **Claude Code worker** does not add Claude-side sandboxing flags (those vary
  by installation). For non-toy use, wrap the runner in a container with the
  workspace bind-mounted and `--network none`.
- **In-process `llm_engine` worker** has *no* boundary, so it is deliberately
  **text-only** — it describes what it would do and does not write into the
  workspace. Do not extend it to perform real edits without first putting it
  behind an OS-level boundary.
- **`_run_command`** provides only a wall-clock timeout. The recommended
  baseline is rootless Podman / Docker with `--network none` and the workspace
  as the only writable bind-mount; see ADR-011.

## Run offline

```bash
python -m examples.agent_coordination_teaching.run_demo --workers mock
```

Dry-run without launching workers:

```bash
python -m examples.agent_coordination_teaching.run_demo --workers mock,codex,claude_code,llm_engine --dry-run
```

Use the simple monitor after a run:

```bash
python -m examples.agent_coordination_teaching.run_demo --workers mock --monitor
```

In the monitor, use `messages` for recent rows and `open <id>` to show the
full body for any exchange. Before launch, you can also inject guidance:

```text
guidance codex_worker Keep the scope to documentation only.
broadcast Pause if you see unrelated local changes.
continue
```

Guidance is written into the mailbox and preserved in the exchange log before
worker prompts are assembled.

## Real workers

Codex uses `codex exec` when `codex` is available on `PATH`.

Claude Code support is intentionally configurable because installations vary.
The default adapter looks for `claude` and uses a common print-mode invocation.

The `llm_engine` worker uses `llm_engines` directly, so it can run local or cloud
models without launching an external agent CLI. Ollama is the default:

```bash
python -m examples.agent_coordination_teaching.run_demo \
  --workers llm_engine \
  --worker-backend ollama \
  --worker-model qwen3:8b
```

For llama.cpp, pass a GGUF file as `--worker-model`. `--worker-n-gpu-layers`
controls split offload: `0` is CPU-only, `-1` asks llama.cpp to offload all
possible layers, and a positive number offloads that many layers to GPU while
the rest run on CPU.

```bash
python -m examples.agent_coordination_teaching.run_demo \
  --planner-backend anthropic \
  --planner-model claude-sonnet-4-6 \
  --workers llm_engine \
  --worker-backend llamacpp \
  --worker-model /models/qwen2.5-32b-instruct-q4_k_m.gguf \
  --worker-n-gpu-layers 40 \
  --worker-n-ctx 8192
```

This is the intended cloud-planner/local-worker shape: a strong cloud model can
plan, while llama.cpp executes the worker role with partial GPU offload.

## Artifacts

Each run writes:

```text
runs/<run_id>/
  manifest.json
  exchanges.jsonl
  trace_events.jsonl
  messages/
```

The short console rows are only previews; full message bodies are preserved in
`messages/`.
