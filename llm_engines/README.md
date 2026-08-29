# llm_engines

## Tier: stable

## Scope

One interface over multiple LLM backends (Ollama, Anthropic, OpenAI, vLLM,
llama.cpp). Does not handle memory, retrieval, or agent orchestration.

## Quick start

```python
from llm_engines import get_engine, ChatMessage, GenerationRequest

engine = get_engine("ollama", "qwen3:8b")
response = engine.generate(GenerationRequest(
    messages=[ChatMessage(role="user", content="What is RAG?")]
))
print(response.text)
```

Connect to a vLLM server on another machine:

```python
from llm_engines import get_engine

engine = get_engine(
    "vllm",
    "organization/model-name",
    base_url="http://inference-host:8000/v1",
    max_context=262_144,
    timeout=120,
)
```

Select thinking per request when the server and model support it:

```python
response = engine.generate(GenerationRequest(
    messages=[ChatMessage(role="user", content="Analyze the competing designs.")],
    thinking=True,
))
```

`thinking=None` preserves the server default, `True` requests thinking, and
`False` requests suppression. The vLLM and local OpenAI-compatible adapters
send this as a Qwen-compatible chat-template option; cloud OpenAI calls do not.
The adapters return the final answer but do not persist or expose the model's
separate reasoning text.

The vLLM server must enable the model-appropriate tool-call parser before
`ToolExecutor` can use automatic tool calls. Memory, RAG indexes, tools, and
application state can remain on the client machine; only model requests cross
the HTTP boundary.

`ToolExecutor` requires a direct tool-capable engine. Use
`EngineFactory.from_engine_name("spark_qwen")` for the configured Spark engine;
the current `FailoverEngine` returned by `from_profile()` does not define
tool-aware failover semantics.

For a separate `llama-server` process, use the non-cloud OpenAI-compatible
backend:

```python
engine = get_engine(
    "openai",
    "served-model-name",
    base_url="http://127.0.0.1:8080/v1",
    api_key="dummy",
    is_cloud=False,
)
```

Local OpenAI-compatible endpoints report embeddings as unavailable by default,
because many `llama-server` launches expose generation only. Set
`supports_embeddings=True` only when that endpoint was started with embedding
support. Vision remains unavailable through this adapter until ai_tools has a
typed image-content request contract.

When the endpoint supports OpenAI-compatible token log probabilities, inspect
them through the public protocol:

```python
result = engine.generate_with_logprobs(request, top_logprobs=3)
print(result.mean_logprob, result.perplexity)
```

The `llamacpp` backend is different: it loads a GGUF in the Python process and
requires `llama-cpp-python`. Do not use it to connect to `llama-server`.

For server-enforced structured output, set `GenerationRequest.json_schema`.
The OpenAI-compatible adapter forwards it as a strict `json_schema` response
format for both ordinary and streamed generation:

```python
response = engine.generate(GenerationRequest(
    messages=[ChatMessage(role="user", content="Describe the rollback window.")],
    json_schema={
        "type": "object",
        "properties": {"rollback_minutes": {"type": "integer"}},
        "required": ["rollback_minutes"],
        "additionalProperties": False,
    },
))
```

For streamed tool decisions, use the separate typed event interface. Tool
argument fragments stay private until they form a complete JSON object:

```python
from llm_engines import StreamFinishedEvent, TextDeltaEvent, ToolCallEvent

async for event in engine.stream_with_tools_async(request, available_tools):
    if isinstance(event, TextDeltaEvent):
        print(event.text, end="")
    elif isinstance(event, ToolCallEvent):
        dispatch(event.tool_call)
    elif isinstance(event, StreamFinishedEvent):
        print(event.finish_reason)
```

This method streams one model response. It does not execute the tool or run a
multi-turn tool loop. Malformed or incomplete argument JSON raises an error;
ai_tools does not repair it or expose a partial executable call.

Thinking tokens count against `max_tokens`. A thinking request can therefore
finish before producing answer text if its output budget is too small. Reserve
enough tokens for both reasoning and the final answer.

Record the same single engine call as a durable artifact without replacing the
runtime response contract:

```python
from llm_engines import record_generation
from llm_harness_core import dump_artifact

recorded = record_generation(engine, GenerationRequest(
    messages=[ChatMessage(role="user", content="What is RAG?")],
))
print(recorded.response.text)
dump_artifact(recorded.artifact, "generation-record.json")
```

Prompts and outputs are sensitive by default. Raw provider payloads and error
messages are omitted unless an explicit `GenerationRecordingPolicy` includes
them. A failed call raises `RecordedGenerationError`, whose `artifact` records
the aborted attempt without issuing a second engine call.

With tool calling:

```python
from llm_engines import get_engine, ToolExecutor, tool

@tool
def add(a: int, b: int) -> int:
    return a + b

engine = get_engine("ollama", "qwen3:8b")
executor = ToolExecutor(tools=[add])
```

With a config-file profile (failover across backends):

```python
from llm_engines import EngineFactory
engine = EngineFactory.from_profile("default_local")
```

`llm_engines` is the backend and model abstraction layer for the `ai_tools` suite.

It provides a stable way to call LLM backends without forcing the rest of the stack to understand backend-specific quirks.

## Characterize an endpoint

`llm-characterize` runs fixed synthetic checks for exact chat output,
structured JSON, tool calls, and token log probabilities. A check is
`not_declared` when the selected adapter does not claim that capability;
endpoint rejection is `error`, while a completed but incorrect observation is
`failed`. These statuses do not constitute endpoint-feature discovery. The
result describes the endpoint behavior observed in that run; it does not expose
hidden reasoning or establish that the model is reliable on real work.

For the Qwen model served by llama.cpp on the Spark:

```bash
llm-characterize \
  --backend openai \
  --model /models/qwen-model.gguf \
  --base-url http://inference-host:8080/v1 \
  --artifact spark-qwen-characterization.json
```

Repeat the complete suite to measure short-run stability and chat latency:

```bash
llm-characterize \
  --backend openai \
  --model /models/qwen-model.gguf \
  --base-url http://inference-host:8080/v1 \
  --runs 5 \
  --thinking default \
  --artifact spark-qwen-characterization-campaign.json
```

Campaign reports include per-probe status counts, pass rates, status stability,
and minimum/median/maximum chat latency. These are observations from that
short run, not confidence intervals or general reliability estimates.

## Probe observable tool decisions

The separate tool-process probe presents four fixed synthetic situations: a
required single tool, a choice between relevant and irrelevant tools, a case
where no tool should be called, and typed argument construction. Tools are not
executed. This isolates the model and endpoint's selection/serialization
behavior from tool side effects:

```bash
llm-tool-process-probe \
  --backend openai \
  --model /models/qwen-model.gguf \
  --base-url http://inference-host:8080/v1 \
  --runs 3 \
  --thinking off \
  --artifact spark-qwen-tool-decisions.json
```

Use `--thinking default`, `--thinking off`, or `--thinking on` to preserve the
server setting, request suppression, or request thinking for every case. The
comparison concerns observable tool decisions only; it cannot explain the
model's internal process.

The durable artifact retains outcomes, scalar measurements, the reported
model-label basename, requested thinking setting, and declared capabilities.
It does not retain raw prompts, model responses, API keys, endpoint URLs, or
exception messages. The built-in probes
contain no user data. Use separate, explicitly governed experiments when you
later study application prompts, memory, RAG, or agent behavior.

## Using this with the rest of the suite

- pair it first with `llm_inspector` or `llm_inspector_ui`
- then add `engram` or `rag_lib`

## Current support status

This is a **core** package and is treated as **active and stable**.

## Responsibilities

- engine/backend abstraction
- capability discovery
- normalized generation responses
- backend diagnostics and readiness checks
- failover/fallback support where configured
- interop conversion into shared `llm_harness_core` objects

## Position in the stack

`llm_engines` sits near the bottom of the suite:

- `llm_inspector_ui` uses it for engine/model selection and execution
- `language_tutor` uses it for model access
- `agent_lib` uses it for agent-facing generation
- `llm_inspector` and the UI inspect metadata produced by it

## Architectural notes

Important settled decisions are recorded in:

- `../adr/ADR-001-engine-capability-model.md`
- `../adr/ADR-002-engine-response-schema.md`

Those ADRs mean callers should assume:

- engine capabilities are explicit, not universal
- engine responses are structured, not plain strings only

## Interop

`llm_engines` participates in the shared harness vocabulary through `llm_harness_core`.

Notable interop responsibilities include:

- describing engines with shared capability descriptors
- converting messages/tool calls to shared objects
- converting generation results to shared operation results

## Prefix-cache contract (backend integration deferred)

`GenerationRequest.session_id` and `GenerationResponse.cache_stats` reserve a
backend-neutral contract for future prefix-cache integration:

```python
from llm_engines import get_engine, ChatMessage, GenerationRequest

engine = get_engine("ollama", "qwen3:8b")

response = engine.generate(GenerationRequest(
    messages=[ChatMessage(role="user", content="Hello")],
    session_id="my-project-session-001",
))
print(response.cache_stats.hit_ratio)
```

The fields are implemented, but no current backend consumes `session_id` or
populates `cache_stats`; zero values therefore mean "not reported." Treat this
surface as forward-compatible scaffolding, not as an operational caching
feature.

See `../docs/design/INFERENCE_OPTIMIZATION.md` for the deferred backend work
and design rationale.


## Intended use

Use `llm_engines` when you want a common engine layer underneath memory, retrieval, inspection, or agents.

Do not use it as a dumping ground for UI logic, retrieval logic, or memory policy.
