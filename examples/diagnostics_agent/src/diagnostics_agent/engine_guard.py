from __future__ import annotations

from diagnostics_agent.errors import RemoteEngineRefused


LOCAL_BACKENDS = {"ollama", "llamacpp", "llama.cpp", "llama-cpp", "vllm", "mock"}


def require_local_engine(engine, *, allow_remote: bool = False) -> None:
    backend = engine_backend_id(engine)
    if backend not in LOCAL_BACKENDS and not allow_remote:
        raise RemoteEngineRefused(
            f"refusing unapproved backend '{backend}' for local diagnostics interpretation"
        )


def engine_backend_id(engine) -> str:
    candidates = [
        getattr(engine, "backend", None),
        getattr(engine, "BACKEND", None),
        getattr(engine.__class__, "backend", None),
        getattr(engine.__class__, "BACKEND", None),
        engine.__class__.__name__.removesuffix("Engine"),
    ]
    module_name = getattr(engine.__class__, "__module__", "")
    if module_name:
        candidates.append(module_name.rsplit(".", maxsplit=1)[-1])

    for candidate in candidates:
        if isinstance(candidate, str) and candidate:
            return candidate.lower().replace("_", "-")
    return ""
