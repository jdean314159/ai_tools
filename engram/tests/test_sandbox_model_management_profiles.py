from __future__ import annotations

import importlib
import sys
import types

import pytest

import pytest
pytest.importorskip("engram_ui", reason="engram_ui not installed")

from engram.engine import model_manager as mm
from engram.engine.model_manager import HFModelInfo

# Skip entire module if engram_ui is not installed
pytest.importorskip(
    "engram_ui",
    reason="engram_ui not installed — skipping sandbox model management UI tests",
)


def _load_model_management_module():
    stub = types.SimpleNamespace(
        expander=lambda *a, **k: _NullContext(),
        caption=lambda *a, **k: None,
        markdown=lambda *a, **k: None,
        code=lambda *a, **k: None,
        success=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        info=lambda *a, **k: None,
        write=lambda *a, **k: None,
        columns=lambda *a, **k: [],
        text_input=lambda *a, **k: "",
        button=lambda *a, **k: False,
        spinner=lambda *a, **k: _NullContext(),
        subheader=lambda *a, **k: None,
        number_input=lambda *a, **k: 0,
        session_state={},
        selectbox=lambda *a, **k: (k.get("options") or [""])[k.get("index", 0)] if k.get("options") else "",
        error=lambda *a, **k: None,
    )
    sys.modules.setdefault("streamlit", stub)
    return importlib.import_module("engram_ui.model_management")


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_recommend_format_for_hf_model_exposes_resource_advisor_profiles(monkeypatch) -> None:
    model = HFModelInfo(
        repo_id="org/model-14b-awq",
        name="model-14b-awq",
        has_awq=True,
        has_safetensors=True,
        estimated_params_b=14.0,
        estimated_size_gb_fp16=28.0,
    )

    shared = [
        {
            "profile": "safe",
            "backend": "vllm",
            "parameters": {
                "gpu_memory_utilization": 0.75,
                "max_num_seqs": 2,
                "max_num_batched_tokens": 2048,
                "optimizations": {
                    "speculative_decoding": False,
                    "kv_cache_compression": "turboquant",
                },
            },
            "estimate": {
                "fits": True,
                "estimated_total_mb": 12288,
                "estimated_headroom_mb": 4096,
            },
            "rationale": ["Conservative fit for a 24 GB GPU."],
        },
        {
            "profile": "balanced",
            "backend": "vllm",
            "parameters": {"gpu_memory_utilization": 0.82},
            "estimate": {"fits": True, "estimated_total_mb": 13312, "estimated_headroom_mb": 3072},
            "rationale": ["Balanced concurrency and headroom."],
        },
    ]

    monkeypatch.setattr(mm, "_shared_launch_recommendations", lambda *args, **kwargs: shared)

    rec = mm.recommend_format_for_hf_model(model, vram_gb=24.0)

    assert rec.engine == "vllm"
    assert rec.resource_advisor == shared
    assert "Shared engine-fit advisor" in rec.reason


def test_resource_profile_rows_formats_profiles_for_ui() -> None:
    module = _load_model_management_module()

    rows = module._resource_profile_rows(
        [
            {
                "profile": "safe",
                "backend": "vllm",
                "parameters": {
                    "gpu_memory_utilization": 0.75,
                    "max_num_seqs": 2,
                    "max_num_batched_tokens": 2048,
                    "optimizations": {
                        "speculative_decoding": False,
                        "kv_cache_compression": "turboquant",
                        "kv_cache_bits": 4,
                    },
                },
                "estimate": {
                    "fits": True,
                    "estimated_total_mb": 12288,
                    "estimated_headroom_mb": 4096,
                },
                "rationale": ["Conservative fit for a 24 GB GPU."],
            }
        ]
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["profile"] == "safe"
    assert row["estimated"] == "12.0 GB"
    assert row["headroom"] == "4.0 GB"
    assert row["fits"] == "yes"
    assert "gpu_memory_utilization=0.75" in row["settings"]
    assert "kv_cache_compression=turboquant" in row["settings"]
    assert "Conservative fit" in row["rationale"]



def test_default_resource_profile_name_prefers_balanced_then_safe() -> None:
    module = _load_model_management_module()
    profiles = [
        {"profile": "safe", "estimate": {"fits": True}},
        {"profile": "balanced", "estimate": {"fits": True}},
        {"profile": "aggressive", "estimate": {"fits": True}},
    ]
    assert module._default_resource_profile_name(profiles) == "balanced"
    assert module._default_resource_profile_name(profiles, preference="headroom") == "safe"
    assert module._default_resource_profile_name(profiles, preference="throughput") == "aggressive"


def test_launch_priority_preference_defaults_and_persists_in_session_state() -> None:
    module = _load_model_management_module()
    module.st.session_state.clear()

    assert module._launch_priority_preference() == "balanced"
    assert module.st.session_state[module._K_LAUNCH_PRIORITY] == "balanced"

    assert module._remember_launch_priority_preference("headroom") == "headroom"
    assert module._launch_priority_preference() == "headroom"
    assert module.st.session_state[module._K_LAUNCH_PRIORITY] == "headroom"

    module.st.session_state[module._K_LAUNCH_PRIORITY] = "invalid"
    assert module._launch_priority_preference() == "balanced"
    assert module.st.session_state[module._K_LAUNCH_PRIORITY] == "balanced"


def test_resource_profile_engine_extra_flattens_selected_vllm_profile() -> None:
    module = _load_model_management_module()
    extra = module._resource_profile_engine_extra(
        [
            {
                "profile": "safe",
                "backend": "vllm",
                "parameters": {
                    "gpu_memory_utilization": 0.75,
                    "max_num_seqs": 2,
                    "max_num_batched_tokens": 2048,
                    "optimizations": {
                        "speculative_decoding": False,
                        "draft_model": "qwen2.5:3b",
                        "kv_cache_compression": "turboquant",
                        "kv_cache_bits": 4,
                    },
                },
            }
        ],
        "safe",
    )
    assert extra["launch_profile"] == "safe"
    assert extra["gpu_memory_utilization"] == 0.75
    assert extra["max_num_seqs"] == 2
    assert extra["draft_model"] == "qwen2.5:3b"
    assert extra["kv_cache_compression"] == "turboquant"


def test_vllm_launch_extra_args_from_settings_maps_known_flags() -> None:
    module = _load_model_management_module()
    args, notes = module._vllm_launch_extra_args_from_settings(
        {
            "gpu_memory_utilization": 0.75,
            "max_num_seqs": 2,
            "max_num_batched_tokens": 2048,
            "speculative_decoding": True,
            "draft_model": "qwen2.5:3b",
            "kv_cache_compression": "turboquant",
            "kv_cache_bits": 4,
        }
    )
    assert "--gpu-memory-utilization" in args
    assert "--max-num-seqs" in args
    assert "--max-num-batched-tokens" in args
    assert "--speculative-config" in args
    assert any("turboquant" in note for note in notes)



def test_vllm_launch_preview_cfg_builds_command_with_profile_settings() -> None:
    module = _load_model_management_module()
    cfg, notes = module._vllm_launch_preview_cfg(
        source="/models/demo",
        engine_name="demo_engine",
        launch_profile_extra={
            "gpu_memory_utilization": 0.75,
            "max_num_seqs": 2,
            "max_num_batched_tokens": 2048,
            "speculative_decoding": True,
            "draft_model": "qwen2.5:3b",
        },
    )
    from engram.engine.runtime_status import build_vllm_launch_command
    cmd = build_vllm_launch_command(cfg)
    assert cmd is not None
    assert "vllm serve /models/demo" in cmd
    assert "--served-model-name demo_engine" in cmd
    assert "--gpu-memory-utilization 0.75" in cmd
    assert "--max-num-seqs 2" in cmd
    assert "--max-num-batched-tokens 2048" in cmd
    assert "--speculative-config" in cmd
    assert notes == []


def test_do_register_applies_launch_profile_settings(monkeypatch) -> None:
    module = _load_model_management_module()
    captured = {}

    def fake_register_model_in_config(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(module, "register_model_in_config", fake_register_model_in_config)
    rec = mm.FormatRecommendation(engine="vllm", format="safetensors", quantization="awq", fits_in_vram=True, estimated_vram_gb=12.0)
    module._do_register(
        "demo_engine",
        "vllm",
        "org/model",
        rec,
        launch_profile_name="safe",
        launch_profile_extra={"gpu_memory_utilization": 0.75, "max_num_seqs": 2},
    )

    assert captured["extra"]["gpu_memory_utilization"] == 0.75
    assert captured["extra"]["max_num_seqs"] == 2
    assert captured["extra"]["launch"]["served_model_name"] == "demo_engine"
    assert "--gpu-memory-utilization" in captured["extra"]["launch"]["extra_args"]


def test_apply_launch_profile_to_existing_engine_updates_config(tmp_path, monkeypatch) -> None:
    module = _load_model_management_module()
    cfg_path = tmp_path / "llm_engines.yaml"
    monkeypatch.setattr(module, "_config_path", lambda: cfg_path)
    module._save_config({
        "engines": {
            "demo_engine": {
                "type": "vllm",
                "model": "demo_engine",
                "base_url": "http://localhost:8000/v1",
                "local_model_dir": "/models/demo",
                "resource_advisor": [
                    {
                        "profile": "safe",
                        "backend": "vllm",
                        "parameters": {
                            "gpu_memory_utilization": 0.75,
                            "max_num_seqs": 2,
                            "max_num_batched_tokens": 2048,
                        },
                    }
                ],
            }
        }
    })

    ok = module._apply_launch_profile_to_engine(
        "demo_engine",
        profile_name="safe",
        resource_advisor=module._load_config()["engines"]["demo_engine"]["resource_advisor"],
    )

    updated = module._load_config()["engines"]["demo_engine"]
    assert ok is True
    assert updated["gpu_memory_utilization"] == 0.75
    assert updated["max_num_seqs"] == 2
    assert updated["launch_profile"] == "safe"
    assert updated["launch"]["served_model_name"] == "demo_engine"
