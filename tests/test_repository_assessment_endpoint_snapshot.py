from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs/projects/repository_assessment/tools/capture_llamacpp_endpoint.py"
)
SPEC = importlib.util.spec_from_file_location("capture_llamacpp_endpoint", SCRIPT_PATH)
assert SPEC is not None
snapshotter = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(snapshotter)


def test_snapshot_excludes_endpoint_paths_prompts_and_unapproved_slot_fields() -> None:
    result = snapshotter.sanitize_snapshot(
        {"status": "ok"},
        {
            "data": [
                {
                    "id": "/home/operator/models/model.gguf",
                    "meta": {
                        "n_ctx": 262144,
                        "n_params": 35,
                        "ftype": "Q4_K - Medium",
                        "private": "drop-me",
                    },
                }
            ]
        },
        {
            "build_info": "build-1",
            "model_path": "/home/operator/models/model.gguf",
            "model_ftype": "Q4_K - Medium",
            "total_slots": 1,
            "default_generation_settings": {
                "n_ctx": 262144,
                "params": {"speculative.types": "none", "generation_prompt": "secret"},
            },
            "chat_template": "drop-me",
        },
        [
            {
                "id": 0,
                "is_processing": False,
                "n_ctx": 262144,
                "speculative": True,
                "prompt": "private task",
                "params": {
                    "prompt": "private task",
                    "speculative.types": "none,draft-mtp",
                },
            }
        ],
        server_header="llama.cpp",
        reference={"launch_configuration": {"cache_type_k": "q4_0"}},
    )

    assert result["health"] == "ok"
    assert result["fingerprint"]["model_label"] == "model.gguf"
    assert result["fingerprint"]["launch_configuration"] == {"cache_type_k": "q4_0"}
    assert result["fingerprint"]["slots"] == [
        {
            "id": 0,
            "is_processing": False,
            "n_ctx": 262144,
            "speculative": True,
            "speculative_types": "none,draft-mtp",
        }
    ]
    rendered = str(result)
    assert "/home/operator" not in rendered
    assert "private task" not in rendered
    assert "generation_prompt" not in rendered


def test_snapshot_hash_ignores_capture_time_but_detects_configuration_change() -> None:
    args = (
        {"status": "ok"},
        {"data": [{"id": "model.gguf", "meta": {"n_ctx": 100}}]},
        {"build_info": "build-1", "total_slots": 1},
        [{"id": 0, "n_ctx": 100, "is_processing": False}],
    )
    first = snapshotter.sanitize_snapshot(*args, server_header="llama.cpp")
    second = snapshotter.sanitize_snapshot(*args, server_header="llama.cpp")
    changed = snapshotter.sanitize_snapshot(
        args[0],
        args[1],
        {"build_info": "build-2", "total_slots": 1},
        args[3],
        server_header="llama.cpp",
    )

    assert first["fingerprint_sha256"] == second["fingerprint_sha256"]
    assert first["fingerprint_sha256"] != changed["fingerprint_sha256"]
