"""
tests/test_discovery.py

Tests for hardware detection and ModelRegistry.
Hardware tests run on any machine.
ModelRegistry tests require Ollama.

    pytest tests/test_discovery.py -m "not ollama"     # offline
    pytest tests/test_discovery.py                     # all
"""
from __future__ import annotations

import pytest

from llm_engines.contracts import (
    GPU,
    HardwareProfile,
    ModelInfo,
    ModelNotFoundError,
)
from llm_engines.discovery import ModelRegistry, detect_hardware


# ---------------------------------------------------------------------------
# detect_hardware
# ---------------------------------------------------------------------------

class TestDetectHardware:

    def test_returns_hardware_profile(self) -> None:
        hw = detect_hardware()
        assert isinstance(hw, HardwareProfile)

    def test_cpu_cores_positive(self) -> None:
        hw = detect_hardware()
        assert hw.cpu_cores >= 1

    def test_vram_consistent_with_gpus(self) -> None:
        hw = detect_hardware()
        expected = sum(g.vram_mb for g in hw.gpus)
        assert hw.vram_total_mb == expected

    def test_has_cuda_matches_gpu_list(self) -> None:
        hw = detect_hardware()
        assert hw.has_cuda == (len(hw.gpus) > 0)

    def test_gpu_compute_capability_is_two_ints(self) -> None:
        hw = detect_hardware()
        for gpu in hw.gpus:
            assert isinstance(gpu.compute_capability, list)
            assert len(gpu.compute_capability) == 2
            assert all(isinstance(v, int) for v in gpu.compute_capability)

    def test_is_cpu_only_property(self) -> None:
        hw = detect_hardware()
        assert hw.is_cpu_only == (not hw.has_cuda or hw.vram_total_mb == 0)


# ---------------------------------------------------------------------------
# ModelRegistry — catalog-only tests (no Ollama required)
# ---------------------------------------------------------------------------

class TestModelRegistryCatalog:

    def test_get_model_info_known_model(self) -> None:
        registry = ModelRegistry()
        info = registry.get_model_info("qwen2.5:14b", backend="ollama")
        assert isinstance(info, ModelInfo)
        assert info.recommended_vram_mb > 0
        assert info.min_vram_mb <= info.recommended_vram_mb

    def test_get_model_info_unknown_raises(self) -> None:
        registry = ModelRegistry()
        with pytest.raises(ModelNotFoundError):
            registry.get_model_info("nonexistent:99b")

    def test_embedding_model_in_catalog(self) -> None:
        registry = ModelRegistry()
        info = registry.get_model_info("nomic-embed-text", backend="ollama")
        assert info.capabilities.embeddings is True

    def test_recommend_falls_back_on_offline_ollama(self) -> None:
        """When Ollama is unreachable, recommend_model should still work
        using catalog-only data (available_names = None path)."""
        registry = ModelRegistry(ollama_host="http://localhost:9")  # unreachable port
        hw = HardwareProfile(
            gpus=[GPU(id=0, name="RTX 3090", vram_mb=24576, compute_capability=[8, 6])],
            vram_total_mb=24576,
            cpu_cores=32,
            memory_total_mb=131072,
            has_cuda=True,
        )
        # Should return something without raising (falls back to catalog)
        model = registry.recommend_model(task="chat", hardware=hw, backend="ollama")
        assert isinstance(model, str)
        assert len(model) > 0

    def test_recommend_respects_vram_limit(self) -> None:
        registry = ModelRegistry(ollama_host="http://localhost:9")
        # Very small VRAM — should pick small model or raise
        hw = HardwareProfile(
            gpus=[GPU(id=0, name="GTX 1650", vram_mb=4096, compute_capability=[7, 5])],
            vram_total_mb=4096,
            cpu_cores=8,
            memory_total_mb=16384,
            has_cuda=True,
        )
        try:
            model = registry.recommend_model(task="chat", hardware=hw, backend="ollama")
            info = registry.get_model_info(model)
            assert info.recommended_vram_mb <= 4096
        except ModelNotFoundError:
            pass  # No model fits — acceptable

    def test_recommend_prefer_speed(self) -> None:
        registry = ModelRegistry(ollama_host="http://localhost:9")
        hw = HardwareProfile(
            gpus=[GPU(id=0, name="RTX 3090", vram_mb=24576, compute_capability=[8, 6])],
            vram_total_mb=24576,
            cpu_cores=32,
            memory_total_mb=131072,
            has_cuda=True,
        )
        fast = registry.recommend_model(task="chat", hardware=hw, prefer_speed=True)
        quality = registry.recommend_model(task="chat", hardware=hw, prefer_speed=False)
        fast_info = registry.get_model_info(fast)
        quality_info = registry.get_model_info(quality)
        # prefer_speed picks smaller model
        assert fast_info.recommended_vram_mb <= quality_info.recommended_vram_mb


# ---------------------------------------------------------------------------
# ModelRegistry — live Ollama tests (requires running Ollama)
# ---------------------------------------------------------------------------

@pytest.mark.ollama
class TestModelRegistryLive:

    def test_list_available_returns_list(self) -> None:
        registry = ModelRegistry()
        models = registry.list_available_models("ollama")
        assert isinstance(models, list)
        assert len(models) > 0

    def test_list_is_sorted(self) -> None:
        registry = ModelRegistry()
        models = registry.list_available_models("ollama")
        assert models == sorted(models)
