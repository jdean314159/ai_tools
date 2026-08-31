from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm_engines import OllamaModelResolutionError, resolve_ollama_gguf_path
from llm_engines import discovery


def test_resolve_ollama_gguf_path_reads_manifest_and_blob(tmp_path) -> None:
    digest = "a" * 64
    blob = tmp_path / "blobs" / f"sha256-{digest}"
    blob.parent.mkdir()
    blob.write_text("fake gguf", encoding="utf-8")
    manifest = tmp_path / "manifests" / "registry.ollama.ai" / "library" / "qwen3" / "8b"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "layers": [
                    {
                        "mediaType": "application/vnd.ollama.image.params",
                        "digest": "sha256:" + "b" * 64,
                    },
                    {
                        "mediaType": "application/vnd.ollama.image.model",
                        "digest": f"sha256:{digest}",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    assert resolve_ollama_gguf_path("qwen3:8b", models_dir=tmp_path) == blob


def test_resolve_ollama_gguf_path_defaults_to_latest_tag(tmp_path) -> None:
    digest = "c" * 64
    blob = tmp_path / "blobs" / f"sha256-{digest}"
    blob.parent.mkdir()
    blob.write_text("fake gguf", encoding="utf-8")
    manifest = tmp_path / "manifests" / "registry.example" / "custom" / "model" / "latest"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "layers": [
                    {
                        "mediaType": "application/vnd.ollama.image.model",
                        "digest": f"sha256:{digest}",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert resolve_ollama_gguf_path("custom/model", models_dir=tmp_path) == blob


def test_resolve_ollama_gguf_path_falls_back_to_system_service_store(
    monkeypatch,
    tmp_path,
) -> None:
    user_store = tmp_path / "home" / ".ollama" / "models"
    system_store = tmp_path / "usr" / "share" / "ollama" / ".ollama" / "models"
    monkeypatch.delenv("OLLAMA_MODELS", raising=False)
    monkeypatch.setattr(
        discovery,
        "_ollama_models_dir_candidates",
        lambda models_dir: [user_store, system_store] if models_dir is None else [Path(models_dir)],
    )
    digest = "e" * 64
    blob = system_store / "blobs" / f"sha256-{digest}"
    blob.parent.mkdir(parents=True)
    blob.write_text("fake gguf", encoding="utf-8")
    manifest = system_store / "manifests" / "registry.ollama.ai" / "library" / "qwen3" / "8b"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "layers": [
                    {
                        "mediaType": "application/vnd.ollama.image.model",
                        "digest": f"sha256:{digest}",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert resolve_ollama_gguf_path("qwen3:8b") == blob


def test_resolve_ollama_gguf_path_raises_when_manifest_missing(tmp_path) -> None:
    (tmp_path / "manifests").mkdir()

    with pytest.raises(OllamaModelResolutionError, match="manifest.*missing:tag"):
        resolve_ollama_gguf_path("missing:tag", models_dir=tmp_path)


def test_resolve_ollama_gguf_path_raises_on_ambiguous_manifest(tmp_path) -> None:
    for registry in ("registry.one", "registry.two"):
        manifest = tmp_path / "manifests" / registry / "library" / "qwen3" / "8b"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({"layers": []}), encoding="utf-8")

    with pytest.raises(OllamaModelResolutionError, match="ambiguous.*registry.one.*registry.two"):
        resolve_ollama_gguf_path("qwen3:8b", models_dir=tmp_path)


def test_resolve_ollama_gguf_path_raises_when_model_layer_missing(tmp_path) -> None:
    manifest = tmp_path / "manifests" / "registry.ollama.ai" / "library" / "qwen3" / "8b"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "layers": [
                    {"mediaType": "application/vnd.ollama.image.params", "digest": "sha256:abc"}
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(OllamaModelResolutionError, match="exactly one model layer"):
        resolve_ollama_gguf_path("qwen3:8b", models_dir=tmp_path)


def test_resolve_ollama_gguf_path_raises_when_blob_missing(tmp_path) -> None:
    digest = "d" * 64
    manifest = tmp_path / "manifests" / "registry.ollama.ai" / "library" / "qwen3" / "8b"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "layers": [
                    {
                        "mediaType": "application/vnd.ollama.image.model",
                        "digest": f"sha256:{digest}",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(OllamaModelResolutionError, match=f"sha256-{digest}"):
        resolve_ollama_gguf_path("qwen3:8b", models_dir=tmp_path)
