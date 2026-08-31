from __future__ import annotations

from llm_inspector_ui.services.engine_service import EngineService


class FakeRegistry:
    def __init__(self):
        self.last_health_config = None
        self.last_models_config = None

    def list_engines(self):
        return [
            {"engine_id": "ollama", "label": "Ollama", "local": True},
            {"engine_id": "vllm", "label": "vLLM", "local": True},
        ]

    def get_engine_config_schema(self, engine_id: str):
        if engine_id == "ollama":
            return [
                {
                    "name": "base_url",
                    "label": "Base URL",
                    "field_type": "text",
                    "default": "http://localhost:11434",
                }
            ]
        return []

    def list_models(self, engine_id: str, config=None):
        self.last_models_config = config
        if engine_id == "ollama":
            if config and config.get("base_url") == "http://good-host:11434":
                return [
                    {
                        "model_id": "qwen3:8b",
                        "label": "Qwen3 8B",
                        "source": "ollama",
                        "installed": True,
                    }
                ]
            return []
        if engine_id == "vllm":
            return []
        raise RuntimeError("unknown engine")

    def health_check(self, engine_id: str, config=None):
        self.last_health_config = config
        if engine_id == "ollama":
            if config and config.get("base_url") == "http://good-host:11434":
                return {"reachable": True, "message": "Ollama reachable."}
            return {"reachable": False, "message": "Bad host."}
        if engine_id == "vllm":
            return {"reachable": False, "message": "vLLM is down."}
        return {"reachable": False, "message": "Unknown engine."}


def test_engine_run_readiness_blocks_missing_or_unavailable_model():
    registry = FakeRegistry()
    svc = EngineService(registry=registry)

    blocked_no_model = svc.get_run_readiness(
        "ollama",
        config={"base_url": "http://good-host:11434"},
        model_id=None,
    )
    assert blocked_no_model.can_run is False
    assert blocked_no_model.severity == "error"
    assert "Select a model" in blocked_no_model.message

    blocked_bad_model = svc.get_run_readiness(
        "ollama",
        config={"base_url": "http://good-host:11434"},
        model_id="missing:model",
    )
    assert blocked_bad_model.can_run is False
    assert blocked_bad_model.severity == "error"
    assert "not available" in blocked_bad_model.message

    ready = svc.get_run_readiness(
        "ollama",
        config={"base_url": "http://good-host:11434"},
        model_id="qwen3:8b",
    )
    assert ready.can_run is True
    assert ready.severity == "ok"


def test_engine_health_distinguishes_ready_states_and_uses_config():
    registry = FakeRegistry()
    svc = EngineService(registry=registry)

    schema = svc.get_engine_config_schema("ollama")
    assert len(schema) == 1
    assert schema[0].name == "base_url"

    ollama_bad = svc.get_engine_health("ollama", config={"base_url": "http://bad-host:11434"})
    assert ollama_bad.exists is True
    assert ollama_bad.reachable is False
    assert ollama_bad.models_available is False
    assert ollama_bad.status == "error"

    ollama_good = svc.get_engine_health("ollama", config={"base_url": "http://good-host:11434"})
    assert ollama_good.exists is True
    assert ollama_good.reachable is True
    assert ollama_good.models_available is True
    assert ollama_good.model_count == 1
    assert ollama_good.status == "ok"

    assert registry.last_health_config == {"base_url": "http://good-host:11434"}
    assert registry.last_models_config == {"base_url": "http://good-host:11434"}

    vllm = svc.get_engine_health("vllm")
    assert vllm.exists is True
    assert vllm.reachable is False
    assert vllm.models_available is False
    assert vllm.status == "error"

    missing = svc.get_engine_health("missing")
    assert missing.exists is False
    assert missing.status == "error"


def test_engine_service_recommends_best_default():
    registry = FakeRegistry()
    svc = EngineService(registry=registry)

    recommended = svc.recommend_default_engine(
        configs={"ollama": {"base_url": "http://good-host:11434"}}
    )
    assert recommended == "ollama"


def test_engine_service_heuristic_schema():
    svc = EngineService(registry=None)

    ollama_schema = svc.get_engine_config_schema("ollama")
    assert [field.name for field in ollama_schema] == ["base_url", "timeout_s"]

    vllm_schema = svc.get_engine_config_schema("vllm")
    assert [field.name for field in vllm_schema] == ["base_url", "timeout_s"]


def test_engine_service_describes_engine_capability():
    registry = FakeRegistry()
    svc = EngineService(registry=registry)

    descriptor = svc.describe_engine_capability(
        "ollama", config={"base_url": "http://good-host:11434"}
    )
    assert descriptor.provider in {"llm_engines", "llm_inspector_ui"}
    assert descriptor.metadata["engine_id"] == "ollama"
