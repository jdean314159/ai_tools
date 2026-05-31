from __future__ import annotations

from dataclasses import dataclass
import json
import urllib.error
import urllib.request


class ModelDiscoveryError(Exception):
    """Local model discovery failed."""


@dataclass(frozen=True)
class LocalModel:
    name: str
    size_bytes: int
    fit: str


def estimate_fit(size_bytes: int, available_vram_bytes: int | None) -> str:
    if available_vram_bytes is None:
        return "unknown"
    need = int(size_bytes * 1.2)
    if available_vram_bytes >= need:
        return "fits"
    if available_vram_bytes >= int(need * 0.85):
        return "tight"
    return "unlikely"


def detect_available_vram_bytes() -> int | None:
    try:
        from llm_engines.discovery import detect_hardware

        profile = detect_hardware()
        if profile.vram_free_mb <= 0:
            return None
        return int(profile.vram_free_mb * 1024 * 1024)
    except Exception:
        return None


def list_local_models(
    *,
    ollama_host: str = "http://localhost:11434",
    available_vram_bytes: int | None = None,
) -> list[LocalModel]:
    url = f"{ollama_host.rstrip('/')}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise ModelDiscoveryError(f"Ollama model discovery failed at {url}: {exc}") from exc

    vram = detect_available_vram_bytes() if available_vram_bytes is None else available_vram_bytes
    models = []
    for item in data.get("models", []):
        name = item.get("name")
        size = item.get("size")
        if not isinstance(name, str) or not isinstance(size, int):
            continue
        models.append(
            LocalModel(
                name=name,
                size_bytes=size,
                fit=estimate_fit(size, vram),
            )
        )
    return sorted(models, key=lambda model: model.size_bytes, reverse=True)
