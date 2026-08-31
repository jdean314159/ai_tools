"""
llm_engines/discovery.py

Hardware detection, Ollama utilities, and ModelRegistry.
Implements contracts/discovery.py.

Design: all Ollama communication uses raw urllib — no ollama package required.
This matches Engram's proven approach and works in environments where the
ollama package is not installed.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

from llm_engines.contracts import (
    BackendUnavailableError,
    EngineCapabilities,
    GPU,
    HardwareProfile,
    ModelInfo,
    ModelNotFoundError,
    TaskType,
)

logger = logging.getLogger(__name__)

_OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


class OllamaModelResolutionError(ValueError):
    """Raised when an Ollama model cannot be resolved to a local GGUF blob."""


# ---------------------------------------------------------------------------
# Hardware detection
# ---------------------------------------------------------------------------


def detect_hardware() -> HardwareProfile:
    """
    Probe the current machine and return a HardwareProfile.

    Detection order:
      1. pynvml  (most accurate — includes free/used VRAM)
      2. torch.cuda  (good accuracy, requires torch)
      3. nvidia-smi subprocess  (no Python GPU packages needed)
      4. CPU-only fallback

    Never raises. Always returns a valid HardwareProfile.
    """
    warnings: list[str] = []
    sources: list[str] = []

    gpus = _detect_gpus_pynvml()
    if gpus:
        sources.append("pynvml")
    else:
        gpus = _detect_gpus_torch(warnings=warnings)
        if gpus:
            sources.append("torch.cuda")
    if not gpus:
        gpus = _detect_gpus_nvidiasmi()
        if gpus:
            sources.append("nvidia-smi")

    vram_total = sum(g.vram_mb for g in gpus)
    vram_free = sum((g.free_vram_mb if g.free_vram_mb is not None else g.vram_mb) for g in gpus)
    return HardwareProfile(
        gpus=gpus,
        vram_total_mb=vram_total,
        vram_free_mb=vram_free,
        cpu_cores=os.cpu_count() or 1,
        memory_total_mb=_detect_system_ram_mb(),
        has_cuda=len(gpus) > 0,
        detection_sources=sources,
        warnings=warnings,
    )


def _detect_gpus_pynvml() -> list[GPU]:
    try:
        import pynvml

        pynvml.nvmlInit()
        gpus = []
        for i in range(pynvml.nvmlDeviceGetCount()):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode()
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            try:
                util = float(pynvml.nvmlDeviceGetUtilizationRates(handle).gpu)
            except Exception:
                util = None
            try:
                cc = pynvml.nvmlDeviceGetCudaComputeCapability(handle)
                compute = [cc[0], cc[1]]
            except Exception:
                compute = [0, 0]
            gpus.append(
                GPU(
                    id=i,
                    name=name,
                    vram_mb=mem.total // (1024 * 1024),
                    free_vram_mb=mem.free // (1024 * 1024),
                    used_vram_mb=mem.used // (1024 * 1024),
                    utilization_pct=util,
                    source="pynvml",
                    compute_capability=compute,
                )
            )
        pynvml.nvmlShutdown()
        return gpus
    except Exception:
        return []


def _detect_gpus_torch(*, warnings: list[str] | None = None) -> list[GPU]:
    try:
        import torch

        if not torch.cuda.is_available():
            return []
        gpus: list[GPU] = []
        for i in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(i)
            free_vram_mb = None
            used_vram_mb = None
            try:
                with torch.cuda.device(i):
                    free_bytes, total_bytes = torch.cuda.memory.mem_get_info()
                free_vram_mb = int(free_bytes // (1024 * 1024))
                used_vram_mb = int((total_bytes - free_bytes) // (1024 * 1024))
            except Exception as exc:
                if warnings is not None:
                    warnings.append(f"torch.cuda detected GPU {i}, but mem_get_info failed: {exc}")
            gpus.append(
                GPU(
                    id=i,
                    name=props.name,
                    vram_mb=props.total_memory // (1024 * 1024),
                    free_vram_mb=free_vram_mb,
                    used_vram_mb=used_vram_mb,
                    source="torch.cuda",
                    compute_capability=[props.major, props.minor],
                )
            )
        return gpus
    except Exception as exc:
        if warnings is not None and shutil.which("nvidia-smi"):
            warnings.append(
                f"CUDA GPUs may exist, but torch.cuda could not initialize in this process: {exc}"
            )
        return []


def _detect_gpus_nvidiasmi() -> list[GPU]:
    try:
        lines = (
            subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,memory.free,memory.used,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                timeout=5,
                text=True,
            )
            .strip()
            .splitlines()
        )
        gpus = []
        for i, line in enumerate(lines):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 5:
                continue
            gpus.append(
                GPU(
                    id=i,
                    name=parts[0],
                    vram_mb=int(parts[1]),
                    free_vram_mb=int(parts[2]),
                    used_vram_mb=int(parts[3]),
                    utilization_pct=float(parts[4]) if parts[4] else None,
                    source="nvidia-smi",
                    compute_capability=[0, 0],
                )
            )
        return gpus
    except Exception:
        return []


def _detect_system_ram_mb() -> int:
    try:
        import psutil

        return int(psutil.virtual_memory().total // (1024 * 1024))
    except Exception:
        pass
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return 0


# ---------------------------------------------------------------------------
# Ollama utilities (urllib-based, no ollama package)
# ---------------------------------------------------------------------------


def check_ollama_running(base_url: str = _OLLAMA_BASE) -> bool:
    """Return True if the Ollama server is reachable."""
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=3):
            return True
    except Exception:
        return False


@dataclass
class OllamaModelInfo:
    """A model currently present in the local Ollama store."""

    name: str
    size_gb: float
    model_id: str = ""


def list_ollama_models(base_url: str = _OLLAMA_BASE) -> list[OllamaModelInfo]:
    """Return models currently pulled in Ollama, sorted by size descending."""
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=5) as resp:
            data = json.loads(resp.read())
        models = [
            OllamaModelInfo(
                name=m.get("name", ""),
                size_gb=round(m.get("size", 0) / (1024**3), 1),
                model_id=(m.get("digest") or "")[:12],
            )
            for m in data.get("models", [])
        ]
        return sorted(models, key=lambda m: m.size_gb, reverse=True)
    except Exception:
        return []


def resolve_ollama_gguf_path(
    model: str,
    *,
    models_dir: str | Path | None = None,
) -> Path:
    """Resolve an Ollama model name[:tag] to the on-disk GGUF blob path.

    Ollama's manifest/blob layout is an implementation detail, not a stable
    public API. This helper fails loudly and names the path it inspected so a
    future layout change produces an actionable diagnostic instead of a guessed
    model path.
    """
    root = _ollama_models_dir(models_dir)
    manifests_root = root / "manifests"
    if not manifests_root.exists():
        searched = ", ".join(
            str(path / "manifests") for path in _ollama_models_dir_candidates(models_dir)
        )
        raise OllamaModelResolutionError(
            f"Ollama manifests directory not found: {manifests_root}. Searched: {searched}"
        )

    model_parts, tag = _split_ollama_model_ref(model)
    matches = [
        path
        for path in manifests_root.rglob(tag)
        if path.is_file() and list(path.parts[-(len(model_parts) + 1) :]) == [*model_parts, tag]
    ]
    if not matches:
        raise OllamaModelResolutionError(
            f"Ollama manifest for model '{model}' was not found under {manifests_root}"
        )
    if len(matches) > 1:
        rendered = ", ".join(str(path) for path in sorted(matches))
        raise OllamaModelResolutionError(
            f"Ollama model '{model}' is ambiguous; matching manifests: {rendered}"
        )

    manifest_path = matches[0]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OllamaModelResolutionError(
            f"Ollama manifest for model '{model}' could not be read as JSON: {manifest_path}"
        ) from exc

    layers = [
        layer
        for layer in manifest.get("layers", [])
        if isinstance(layer, dict) and "model" in str(layer.get("mediaType", "")).lower()
    ]
    if len(layers) != 1:
        raise OllamaModelResolutionError(
            f"Ollama manifest {manifest_path} must contain exactly one model layer; found {len(layers)}"
        )

    digest = layers[0].get("digest")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise OllamaModelResolutionError(
            f"Ollama model layer in {manifest_path} has no sha256 digest"
        )

    blob_path = root / "blobs" / digest.replace(":", "-", 1)
    if not blob_path.exists():
        raise OllamaModelResolutionError(
            f"Ollama GGUF blob for model '{model}' does not exist: {blob_path}"
        )
    return blob_path


def _ollama_models_dir(models_dir: str | Path | None) -> Path:
    candidates = _ollama_models_dir_candidates(models_dir)
    for candidate in candidates:
        if (candidate / "manifests").exists():
            return candidate
    return candidates[0]


def _ollama_models_dir_candidates(models_dir: str | Path | None) -> list[Path]:
    if models_dir is not None:
        return [Path(models_dir).expanduser()]
    env_dir = os.getenv("OLLAMA_MODELS")
    if env_dir:
        return [Path(env_dir).expanduser()]
    return [
        Path("~/.ollama/models").expanduser(),
        Path("/usr/share/ollama/.ollama/models"),
    ]


def _split_ollama_model_ref(model: str) -> tuple[list[str], str]:
    cleaned = model.strip()
    if not cleaned:
        raise OllamaModelResolutionError("Ollama model name must not be empty")
    name, separator, tag = cleaned.rpartition(":")
    if not separator:
        name = cleaned
        tag = "latest"
    parts = [part for part in name.split("/") if part]
    if not parts or not tag:
        raise OllamaModelResolutionError(f"Invalid Ollama model reference: {model!r}")
    return parts, tag


def pull_ollama_model(
    model_name: str,
    progress_callback: Callable[[float, float, float], None] | None = None,
    base_url: str = _OLLAMA_BASE,
) -> bool:
    """
    Pull a model from Ollama with optional progress reporting.

    Args:
        model_name:        e.g. "qwen3:8b"
        progress_callback: called with (pct_0_100, downloaded_gb, total_gb)
        base_url:          Ollama server URL

    Returns:
        True on success, False on failure.
    """
    payload = json.dumps({"name": model_name, "stream": True}).encode()
    req = urllib.request.Request(
        f"{base_url}/api/pull",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3600) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("error"):
                    return False
                if progress_callback and "completed" in event and "total" in event:
                    total = event["total"]
                    completed = event["completed"]
                    if total > 0:
                        progress_callback(
                            completed / total * 100,
                            completed / (1024**3),
                            total / (1024**3),
                        )
                if event.get("status") == "success":
                    return True
        return True
    except Exception as e:
        logger.warning("Failed to pull '%s': %s", model_name, e)
        return False


def ensure_ollama_model(
    model_name: str,
    base_url: str = _OLLAMA_BASE,
) -> bool:
    """
    Ensure a model is present in Ollama; pull if missing.

    Uses Ollama's native /api/show to check presence, then /api/pull.
    Returns True if the model is ready after this call.
    """
    show_url = f"{base_url}/api/show"
    req = urllib.request.Request(
        show_url,
        data=json.dumps({"name": model_name}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            return True  # already present
    except Exception:
        pass
    # Not present — pull it
    return pull_ollama_model(model_name, base_url=base_url)


def start_ollama(base_url: str = _OLLAMA_BASE) -> bool:
    """Attempt to start Ollama as a background process. Returns True if reachable."""
    if check_ollama_running(base_url):
        return True
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return False
    for _ in range(10):
        time.sleep(1)
        if check_ollama_running(base_url):
            return True
    return False


def check_ollama_logprobs_support(base_url: str = _OLLAMA_BASE) -> bool:
    """
    Return True if this Ollama instance supports logprobs (>= 0.12.11).

    Required by Engram's RTRL surprise filter. If False, the neural layer
    operates in conservative mode.
    """
    try:
        with urllib.request.urlopen(f"{base_url}/api/version", timeout=3) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        version = str(payload.get("version") or "").strip().lstrip("v")
        if not version:
            return True
        parts = version.split(".")
        ints: list[int] = []
        for p in parts[:3]:
            num = "".join(ch for ch in p if ch.isdigit())
            ints.append(int(num) if num else 0)
        while len(ints) < 3:
            ints.append(0)
        return tuple(ints) >= (0, 12, 11)
    except Exception:
        return True  # cannot check → optimistic


def check_api_key(engine_type: str) -> bool:
    """Return True if the required API key env var is set (or not needed)."""
    _KEY_MAP = {
        "gemini": "GOOGLE_API_KEY",
        "google": "GOOGLE_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "claude": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "chatgpt": "OPENAI_API_KEY",
    }
    env_var = _KEY_MAP.get(engine_type.lower())
    return True if env_var is None else bool(os.getenv(env_var))


@dataclass
class EngineAvailability:
    """Snapshot of what backends are available right now."""

    ollama_running: bool
    ollama_models: list[OllamaModelInfo] = field(default_factory=list)
    has_google_key: bool = False
    has_anthropic_key: bool = False
    has_openai_key: bool = False
    ollama_supports_logprobs: bool = True

    def has_model(self, name: str) -> bool:
        """True if name is pulled in Ollama (exact or prefix match)."""
        return any(
            m.name == name or m.name.startswith(name.split(":")[0]) for m in self.ollama_models
        )


def available_engines(base_url: str = _OLLAMA_BASE) -> EngineAvailability:
    """Return a full snapshot of available backends."""
    running = check_ollama_running(base_url)
    models = list_ollama_models(base_url) if running else []
    logprobs = check_ollama_logprobs_support(base_url) if running else False
    return EngineAvailability(
        ollama_running=running,
        ollama_models=models,
        has_google_key=check_api_key("gemini"),
        has_anthropic_key=check_api_key("anthropic"),
        has_openai_key=check_api_key("openai"),
        ollama_supports_logprobs=logprobs,
    )


# ---------------------------------------------------------------------------
# Model catalog
# ---------------------------------------------------------------------------


def _load_catalog() -> list[dict[str, Any]]:
    catalog_path = Path(__file__).parent / "data" / "model_catalog.yaml"
    with open(catalog_path) as f:
        return yaml.safe_load(f) or []


def _to_model_info(entry: dict[str, Any]) -> ModelInfo:
    caps_raw = entry.get("capabilities", {})
    return ModelInfo(
        name=entry["name"],
        backend=entry["backend"],
        size_gb=float(entry.get("size_gb", 0)),
        min_vram_mb=int(entry.get("min_vram_mb", 0)),
        recommended_vram_mb=int(entry.get("recommended_vram_mb", 0)),
        capabilities=EngineCapabilities(
            chat=caps_raw.get("chat", False),
            embeddings=caps_raw.get("embeddings", False),
            tool_calling=caps_raw.get("tool_calling", False),
            vision=caps_raw.get("vision", False),
        ),
        quantization=entry.get("quantization"),
    )


# ---------------------------------------------------------------------------
# ModelRegistry
# ---------------------------------------------------------------------------


class ModelRegistry:
    """
    Enumerate and recommend models.

    All Ollama I/O is via raw urllib — no ollama package required.
    VRAM requirements come from model_catalog.yaml (not the Ollama API).
    """

    def __init__(self, ollama_host: str = _OLLAMA_BASE) -> None:
        self.ollama_host = ollama_host
        self._catalog: dict[str, dict[str, Any]] = {e["name"]: e for e in _load_catalog()}

    def list_available_models(self, backend: str = "ollama") -> list[str]:
        if backend == "ollama":
            if not check_ollama_running(self.ollama_host):
                raise BackendUnavailableError(f"Ollama not reachable at {self.ollama_host}.")
            return sorted(m.name for m in list_ollama_models(self.ollama_host))
        return sorted(n for n, e in self._catalog.items() if e.get("backend") == backend)

    def get_model_info(self, model: str, backend: str = "ollama") -> ModelInfo:
        # 1. Exact match
        entry = self._catalog.get(model)
        if entry:
            return _to_model_info(entry)

        # 2. Match base:tag — e.g. "qwen3:32b" matches catalog key "qwen3:32b"
        #    (already covered by exact match above, but belt-and-suspenders)

        # 3. Prefix match only when no tag specified — e.g. "qwen3" → "qwen3:8b"
        #    Do NOT prefix-match when a tag is specified, to avoid qwen3:32b → qwen3:8b
        if ":" not in model:
            base = model
            entry = next(
                (
                    e
                    for n, e in self._catalog.items()
                    if e.get("backend") == backend and n.startswith(base + ":")
                ),
                None,
            )
            if entry:
                return _to_model_info(entry)

        raise ModelNotFoundError(f"Model '{model}' not found for backend='{backend}'.")

    def recommend_model(
        self,
        task: TaskType,
        hardware: HardwareProfile,
        backend: str = "ollama",
        prefer_speed: bool = False,
    ) -> str:
        try:
            available: set[str] | None = set(self.list_available_models(backend))
        except BackendUnavailableError:
            available = None  # catalog-only fallback

        candidates: list[ModelInfo] = []
        for name, entry in self._catalog.items():
            if entry.get("backend") != backend:
                continue
            if task not in entry.get("tasks", []):
                continue
            caps = entry.get("capabilities", {})
            if task == "embeddings" and not caps.get("embeddings"):
                continue
            if available is not None and name not in available:
                continue
            info = _to_model_info(entry)
            vram_needed = info.min_vram_mb if hardware.is_cpu_only else info.recommended_vram_mb
            if vram_needed <= hardware.vram_total_mb or hardware.is_cpu_only:
                candidates.append(info)

        if not candidates:
            raise ModelNotFoundError(
                f"No model fits task='{task}', backend='{backend}', "
                f"vram={hardware.vram_total_mb}MB."
            )
        candidates.sort(key=lambda m: m.recommended_vram_mb, reverse=not prefer_speed)
        return candidates[0].name

    def download_model(
        self,
        model: str,
        backend: str = "ollama",
        progress_callback: Callable[[float, float, float], None] | None = None,
    ) -> bool:
        if backend != "ollama":
            raise NotImplementedError(f"download_model not implemented for '{backend}'")
        return pull_ollama_model(model, progress_callback, self.ollama_host)
