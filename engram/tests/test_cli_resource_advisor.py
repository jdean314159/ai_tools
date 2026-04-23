from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml

from engram import cli


def _write_config(tmp_path: Path) -> Path:
    cfg = {
        "engines": {
            "worker": {
                "type": "ollama",
                "model": "qwen3:8b",
                "base_url": "http://localhost:11434/v1",
                "max_context": 8192,
            }
        },
        "profiles": {
            "default_local": {
                "engines": ["worker"],
                "allow_cloud_failover": False,
            }
        },
    }
    path = tmp_path / "llm_engines.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _fake_hardware_profile() -> SimpleNamespace:
    return SimpleNamespace(
        gpus=[SimpleNamespace(id=0, name="RTX 3090", vram_mb=24576, free_vram_mb=20480)],
        vram_total_mb=24576,
        vram_free_mb=20480,
        memory_total_mb=131072,
        has_cuda=True,
        detection_sources=["fake_shared"],
        warnings=["shared warning"],
    )


def test_detect_hardware_prefers_shared_resource_profile(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_probe_system_resources_shared", lambda: _fake_hardware_profile())
    hw = cli._detect_hardware()
    assert hw.accel == "cuda"
    assert hw.vram_gb == 24.0
    assert hw.free_vram_gb == 20.0
    assert hw.detection_sources == ("fake_shared",)
    assert hw.warnings == ("shared warning",)
    assert hw.hardware_profile is not None


def test_run_recommend_includes_shared_resource_advisor(monkeypatch, tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    fake_profile = _fake_hardware_profile()
    monkeypatch.setattr(cli, "_probe_system_resources_shared", lambda: fake_profile)
    monkeypatch.setattr(
        cli,
        "_build_shared_profile_advice",
        lambda cfg, current_profile, hw_profile=None: {
            "available": True,
            "profile": current_profile,
            "profile_mode": "failover_chain",
            "summary": "Shared advisor summary.",
            "engine_launch_recommendations": [{"engine": "worker"}],
            "hardware_profile": {"detection_sources": ["fake_shared"]},
        },
    )

    payload = cli.run_recommend(profile="default_local", config=str(config_path))

    assert payload["recommendation"] == "Shared advisor summary."
    assert payload["resource_advisor"]["summary"] == "Shared advisor summary."
    assert payload["hardware"]["detection_sources"] == ["fake_shared"]
    assert payload["hardware_profile"]["detection_sources"] == ["fake_shared"]


def test_run_doctor_carries_resource_advisor_payload(monkeypatch, tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    fake_profile = _fake_hardware_profile()
    monkeypatch.setattr(cli, "_probe_system_resources_shared", lambda: fake_profile)
    monkeypatch.setattr(cli, "_ollama_version", lambda base_url: (False, "offline"))
    monkeypatch.setattr(cli, "_ollama_model_present", lambda base_url, model: (False, "unreachable"))
    monkeypatch.setattr(cli, "_build_shared_profile_advice", lambda cfg, current_profile, hw_profile=None: {
        "available": True,
        "profile": current_profile,
        "profile_mode": "failover_chain",
        "summary": "Doctor shared advisor summary.",
        "engine_launch_recommendations": [{"engine": "worker"}],
        "hardware_profile": {"detection_sources": ["fake_shared"]},
    })

    payload = cli.run_doctor(profile="default_local", config=str(config_path), include_recommend=True)

    assert payload["recommendation"] == "Doctor shared advisor summary."
    assert payload["resource_advisor"]["summary"] == "Doctor shared advisor summary."
    assert payload["hardware"]["detection_sources"] == ["fake_shared"]
    assert payload["hardware_profile"]["detection_sources"] == ["fake_shared"]
