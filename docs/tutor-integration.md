# Spanish/Latin Tutor — llm_engines Integration Guide

**Purpose:** Replace the tutor's direct Ollama API calls with `llm_engines`  
**Estimated effort:** 2–3 hours  
**Prerequisite:** `pip install -e ~/ai_tools/llm_engines` in the tutor venv

---

## What changes and why

The tutor currently calls Ollama's native HTTP API directly. Replacing those
calls with `OllamaEngine` gives you:

- `FailoverEngine` with circuit breaker — if `qwen3:27b` OOMs, falls back to `qwen3:8b`
- `StructuredOutputHandler` for robust JSON parsing of structured LLM output
- `keep_alive=0` properly propagated to the native endpoint
- `think=False` enforced for both models (suppresses CoT for Qwen3)
- Future: swap to `AnthropicEngine` for the planner without changing tutor code

---

## 1. Add the tutor profile to `~/.engram/llm_engines.yaml`

The packaged default already has `tutor_planner` and `tutor_executor` profiles.
Verify they match your model names:

```yaml
engines:
  tutor_planner_engine:
    type: ollama
    model: qwen3:27b          # or whichever planner model you use
    keep_alive: 0             # CRITICAL: unload immediately after planning
    thinking: false
    num_gpu: null

  tutor_executor_engine:
    type: ollama
    model: qwen3:8b           # or qwen3:9b
    keep_alive: 300
    thinking: false
    num_gpu: null

profiles:
  tutor_planner:
    engines: [tutor_planner_engine]
    allow_cloud_failover: false
    max_attempts: 2

  tutor_executor:
    engines: [tutor_executor_engine]
    allow_cloud_failover: false
    max_attempts: 2
```

---

## 2. Engine initialisation (`language_tutor/engine.py` or equivalent)

**Before:**
```python
import requests

OLLAMA_URL = "http://localhost:11434"
PLANNER_MODEL = "qwen3:27b"
EXECUTOR_MODEL = "qwen3:8b"

def call_planner(messages: list[dict]) -> str:
    resp = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": PLANNER_MODEL,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {"temperature": 0.3},
        },
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]
```

**After:**
```python
from llm_engines import EngineFactory
from llm_engines.utils.structured_output import StructuredOutputHandler
from llm_engines.contracts import ChatMessage, GenerationRequest

# Initialise once at startup (module level or app lifespan)
planner = EngineFactory.from_profile("tutor_planner")
executor = EngineFactory.from_profile("tutor_executor")

def call_planner(messages: list[dict], temperature: float = 0.3) -> str:
    request = GenerationRequest(
        messages=[ChatMessage(role=m["role"], content=m["content"]) for m in messages],
        max_tokens=2048,
        temperature=temperature,
    )
    response = planner.generate(request)
    return response.message.content or ""
```

---

## 3. Structured output (plan generation)

The planner likely returns a JSON plan. Replace manual `json.loads` with
`StructuredOutputHandler` which handles markdown fences and malformed JSON:

**Before:**
```python
import json, re

raw = call_planner(messages)
# Fragile: breaks on "```json\n{...}\n```" format
match = re.search(r'\{.*\}', raw, re.DOTALL)
plan = json.loads(match.group())
```

**After:**
```python
from pydantic import BaseModel
from llm_engines.utils.structured_output import StructuredOutputHandler

class LessonPlan(BaseModel):
    topic: str
    exercises: list[str]
    vocabulary: list[str]
    difficulty: str

raw = call_planner(messages)
plan = StructuredOutputHandler.parse(raw, LessonPlan, allow_repair=True)
# plan.topic, plan.exercises, etc. — typed and validated
```

---

## 4. Streaming for the executor (FastAPI endpoint)

The tutor's voice mode needs async streaming. Replace direct Ollama streaming
with `stream_async` via `FailoverEngine`:

**Before (typical FastAPI SSE):**
```python
import httpx
from fastapi.responses import StreamingResponse

async def stream_response(messages):
    async def generate():
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", f"{OLLAMA_URL}/api/chat",
                                     json={"model": EXECUTOR_MODEL,
                                           "messages": messages,
                                           "stream": True,
                                           "think": False}) as r:
                async for line in r.aiter_lines():
                    if line:
                        chunk = json.loads(line)
                        if token := chunk.get("message", {}).get("content"):
                            yield f"data: {token}\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")
```

**After:**
```python
from fastapi.responses import StreamingResponse
from llm_engines.contracts import ChatMessage, GenerationRequest

async def stream_response(messages: list[dict]) -> StreamingResponse:
    request = GenerationRequest(
        messages=[ChatMessage(role=m["role"], content=m["content"]) for m in messages],
        max_tokens=2048,
        temperature=0.7,
    )

    async def generate():
        # OllamaEngine implements StreamingModel (sync), not AsyncStreamingModel.
        # For FastAPI SSE, run the sync stream in a thread pool:
        import asyncio
        loop = asyncio.get_event_loop()
        stream_iter = await loop.run_in_executor(
            None, lambda: list(executor.stream(request))
        )
        for token in stream_iter:
            yield f"data: {token}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

> **Note on true async streaming:** `OllamaEngine` uses sync urllib and implements
> `StreamingModel` (sync iterator). If you need true async streaming without
> thread-pool overhead, switch the executor to `vLLMEngine` (implements
> `AsyncStreamingModel`) or use `AsyncStreamingModel.stream_async()` directly.

---

## 5. `keep_alive=0` after planning (VRAM management)

The tutor already handles this — `OLLAMA_KEEP_ALIVE=0` in `start.sh` and an
explicit unload POST after planning. With `llm_engines`, `keep_alive=0` is set
in the YAML config and applied automatically per request. No manual unload POST
needed. You can remove:

```python
# Remove this:
requests.post(f"{OLLAMA_URL}/api/chat", json={"model": PLANNER_MODEL, "keep_alive": 0})
```

The engine sends `keep_alive: 0` as part of every generation request payload.

---

## 6. SM-2 vocabulary scoring (no LLM changes needed)

The SM-2 spaced repetition logic is pure Python — no change needed there.
If you want LLM-assisted difficulty scoring, you could add:

```python
from pydantic import BaseModel

class VocabDifficulty(BaseModel):
    word: str
    difficulty: float  # 0.0 (easy) to 1.0 (hard)
    reasoning: str

def score_vocabulary(word: str, context: str) -> float:
    prompt = f"Rate the difficulty of '{word}' in context: {context}"
    raw = call_executor([{"role": "user", "content": prompt}], temperature=0.0)
    result = StructuredOutputHandler.parse_with_details(raw, VocabDifficulty)
    return result.data.difficulty if result.success else 0.5
```

---

## 7. Integration test

Add this to `language_tutor/tests/test_integration.py`:

```python
"""Smoke test the tutor's llm_engines wiring without a live Ollama server."""
from unittest.mock import patch
from llm_engines.backends.mock import MockEngine
from llm_engines import EngineFactory

def test_planner_returns_string(monkeypatch):
    # Patch EngineFactory to return MockEngines
    monkeypatch.setattr(
        "language_tutor.engine.planner",
        MockEngine(response_fn=lambda r: '{"topic": "verbs", "exercises": [], "vocabulary": []}')
    )
    from language_tutor.engine import call_planner
    result = call_planner([{"role": "user", "content": "Plan a lesson on verbs"}])
    assert "verbs" in result
```

---

## 8. `start.sh` changes

Remove the explicit `OLLAMA_KEEP_ALIVE=0` env var — it's no longer needed since
`keep_alive` is now per-request in the YAML config. Keep everything else.

```bash
# Remove this line:
export OLLAMA_KEEP_ALIVE=0

# Keep:
uvicorn language_tutor.app:app --host 0.0.0.0 --port 8443 \
    --ssl-keyfile certs/key.pem --ssl-certfile certs/cert.pem \
    --no-reload
```

---

## Migration order

1. Add tutor profiles to `~/.engram/llm_engines.yaml`
2. Replace `call_planner()` first — it's the simpler of the two calls
3. Verify the planner endpoint works end-to-end with `MockEngine` in tests
4. Replace streaming executor
5. Swap fragile `json.loads` calls for `StructuredOutputHandler.parse()`
6. Remove `OLLAMA_KEEP_ALIVE=0` from `start.sh`

Each step is independently rollbackable — the old `requests.post` calls and
the new engine calls can coexist during migration.
