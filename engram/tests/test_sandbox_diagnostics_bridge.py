from __future__ import annotations

from apps.sandbox import diagnostics_bridge as bridge


def test_augment_payload_with_shared_hardware_profile() -> None:
    payload = {
        "hardware": {"accelerator": "cuda", "torch_cuda_available": True},
        "hardware_profile": {
            "memory_total_mb": 131072,
            "vram_total_mb": 24576,
            "vram_free_mb": 20480,
            "has_cuda": True,
            "detection_sources": ["torch", "nvidia-smi"],
            "warnings": [],
            "gpus": [
                {"id": 0, "name": "RTX 3090", "vram_mb": 24576, "free_vram_mb": 20480}
            ],
        },
    }

    augmented = bridge._augment_payload_with_hardware(payload)

    assert augmented["hardware"]["gpu_detected"] is True
    assert augmented["hardware"]["gpu_name"] == "RTX 3090"
    assert round(float(augmented["hardware"]["vram_gb"]), 1) == 24.0
    assert round(float(augmented["hardware"]["free_vram_gb"]), 1) == 20.0
    assert augmented["hardware"]["detection_sources"] == ["torch", "nvidia-smi"]


def test_system_info_uses_recommend_payload(monkeypatch) -> None:
    payload = {
        "hardware": {
            "accelerator": "gpu",
            "gpu_detected": True,
            "gpu_name": "RTX 3090",
            "vram_gb": 24.0,
            "free_vram_gb": 20.0,
            "torch_cuda_available": True,
        },
        "hardware_profile": {
            "memory_total_mb": 131072,
            "vram_total_mb": 24576,
            "vram_free_mb": 20480,
            "has_cuda": True,
            "detection_sources": ["torch"],
            "warnings": [],
            "gpus": [
                {"id": 0, "name": "RTX 3090", "vram_mb": 24576, "free_vram_mb": 20480}
            ],
        },
    }

    monkeypatch.setattr(bridge, "recommend", lambda profile="default_local": payload)

    sys_info = bridge.system_info()

    assert round(float(sys_info.ram_gb), 1) == 128.0
    assert round(float(sys_info.total_vram_gb), 1) == 24.0
    assert sys_info.accelerator == "gpu"
    assert sys_info.gpus and sys_info.gpus[0].name == "RTX 3090"
