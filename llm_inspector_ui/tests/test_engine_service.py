from __future__ import annotations

from llm_inspector_ui.services.engine_service import (
    EngineService,
    ModelDescriptor,
    ProvisionResult,
)


class FakeRegistry:
    def list_engines(self):
        return [
            {"engine_id": "ollama", "label": "Ollama", "local": True},
            {"engine_id": "remote", "label": "Remote", "local": False},
        ]

    def list_models(self, engine_id: str):
        if engine_id == "ollama":
            return [
                {"model_id": "qwen3:8b", "label": "Qwen3 8B", "source": "ollama", "installed": True},
            ]
        return []

    def search_models(self, query: str, source=None):
        return [
            {"model_id": "Qwen/Qwen3-8B", "label": "Qwen3 8B", "source": source or "huggingface", "installed": False},
        ]

    def provision_model(self, request):
        return ProvisionResult(
            success=True,
            model_id=request.model_id,
            local_ref=f"/models/{request.model_id}",
            message="Provisioned.",
        )

    def create_engine(self, engine_id: str, config: dict):
        class Engine:
            def invoke(self, *, prompt: str, model_id=None, settings=None, session_id=None):
                return {"text": "ok", "metrics": {"engine_id": engine_id, "model_id": model_id}}
        return Engine()


def test_engine_service_registry_bridge():
    svc = EngineService(registry=FakeRegistry())

    engines = svc.list_engines()
    assert {e.engine_id for e in engines} == {"echo", "ollama", "remote"}

    models = svc.list_models("ollama")
    assert len(models) == 1
    assert models[0].model_id == "qwen3:8b"

    results = svc.search_models("qwen")
    assert len(results) == 1
    assert isinstance(results[0], ModelDescriptor)
    assert results[0].source == "huggingface"

    provision = svc.provision_model(source="huggingface", model_id="Qwen/Qwen3-8B")
    assert provision.success is True
    assert provision.local_ref == "/models/Qwen/Qwen3-8B"

    engine = svc.create_engine("ollama", {})
    response = engine.invoke(prompt="hello", model_id="qwen3:8b")
    assert response["text"] == "ok"