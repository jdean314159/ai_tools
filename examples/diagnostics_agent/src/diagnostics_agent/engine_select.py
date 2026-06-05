from __future__ import annotations

from dataclasses import dataclass

from diagnostics_agent.engine_guard import require_local_engine
from llm_engines import FailoverEngine, FailoverPolicy, get_engine


@dataclass(frozen=True)
class EngineChoice:
    backend: str
    model: str
    base_url: str | None = None
    n_gpu_layers: int | None = None
    n_ctx: int | None = None
    n_batch: int | None = None
    n_ubatch: int | None = None
    cache_type_k: str = "f16"
    cache_type_v: str = "f16"
    flash_attn: bool = False
    fallback: "EngineChoice | None" = None


DIAGNOSTICS_POLICY = FailoverPolicy(
    allow_cloud_failover=False,
    reduce_output_on_oom=True,
)


def build_single_engine(choice: EngineChoice):
    backend = choice.backend.lower()
    if backend == "ollama":
        kwargs = {"base_url": choice.base_url} if choice.base_url else {}
        engine = get_engine("ollama", choice.model, **kwargs)
    elif backend == "llamacpp":
        kwargs = {}
        if choice.n_gpu_layers is not None:
            kwargs["n_gpu_layers"] = choice.n_gpu_layers
        if choice.n_ctx is not None:
            kwargs["n_ctx"] = choice.n_ctx
        if choice.n_batch is not None:
            kwargs["n_batch"] = choice.n_batch
        if choice.n_ubatch is not None:
            kwargs["n_ubatch"] = choice.n_ubatch
        kwargs["cache_type_k"] = choice.cache_type_k
        kwargs["cache_type_v"] = choice.cache_type_v
        if choice.flash_attn:
            kwargs["flash_attn"] = True
        engine = get_engine("llamacpp", choice.model, **kwargs)
    elif backend == "vllm":
        kwargs = {"base_url": choice.base_url} if choice.base_url else {}
        engine = get_engine("vllm", choice.model, **kwargs)
    else:
        raise ValueError(f"unsupported backend: {choice.backend}")

    require_local_engine(engine)
    return engine


def build_engine(choice: EngineChoice):
    engines = [build_single_engine(choice)]
    if choice.fallback is not None:
        engines.append(build_single_engine(choice.fallback))
    if len(engines) == 1:
        return engines[0]
    return FailoverEngine(engines, policy=DIAGNOSTICS_POLICY, name="diagnostics")
