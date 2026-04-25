"""Thin wrapper around Engram's doctor/recommend logic for use in the UI.

Why this exists
---------------
The CLI (`engram doctor`, `engram recommend`) is built around argparse and
prints to stdout. For the UI we want *programmatic* access to the same
diagnostics payloads (Python dicts) without shelling out.

Config resolution
-----------------
The CLI defaults to reading ~/.engram/llm_engines.yaml. In a fresh install,
that file may not exist yet. For good UX, the UI will:

1) Prefer the user config at ~/.engram/llm_engines.yaml if present.
2) Otherwise fall back to the package-bundled default config shipped at
   engram/engine/llm_engines.yaml.

This makes the UI work out-of-the-box on Linux/Windows/macOS without any
manual config copying.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from engram.cli import run_doctor, run_recommend


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None or x == "":
            return None
        return float(x)
    except Exception:
        return None


def _gb_from_mb(value: Any) -> Optional[float]:
    numeric = _safe_float(value)
    if numeric is None:
        return None
    return numeric / 1024.0


def _hardware_status_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(payload or {})
    existing_hw = dict(out.get("hardware") or {})
    profile = dict(out.get("hardware_profile") or {})
    gpus = list(profile.get("gpus") or [])

    gpu_name = existing_hw.get("gpu_name") or (gpus[0].get("name") if gpus else None)
    total_vram_gb = _safe_float(existing_hw.get("vram_gb"))
    if total_vram_gb is None:
        total_vram_gb = _gb_from_mb(profile.get("vram_total_mb"))
    free_vram_gb = _safe_float(existing_hw.get("free_vram_gb"))
    if free_vram_gb is None:
        free_vram_gb = _gb_from_mb(profile.get("vram_free_mb"))

    torch_cuda_available = existing_hw.get("torch_cuda_available")
    gpu_detected = bool(existing_hw.get("gpu_detected")) or bool(gpus) or bool(total_vram_gb)
    accelerator = str(existing_hw.get("accelerator") or ("gpu" if gpu_detected else "cpu")).lower()
    if accelerator == "cuda":
        accelerator = "gpu"
    if accelerator == "mps":
        accelerator_class = "mps"
    elif gpu_detected and torch_cuda_available is False:
        accelerator_class = "gpu_unhealthy"
    elif gpu_detected:
        accelerator_class = "gpu"
    else:
        accelerator_class = "cpu"

    warnings = [str(item) for item in (profile.get("warnings") or []) if str(item).strip()]
    if out.get("hardware_warning"):
        warnings.append(str(out["hardware_warning"]))

    return {
        "accelerator_class": accelerator_class,
        "gpu_detected": gpu_detected,
        "gpu_name": gpu_name,
        "total_vram_gb": total_vram_gb,
        "free_vram_gb": free_vram_gb,
        "torch_cuda_available": torch_cuda_available,
        "torch_cuda_built": existing_hw.get("torch_cuda_built"),
        "torch_cuda_version": existing_hw.get("torch_cuda_version"),
        "torch_version": existing_hw.get("torch_version"),
        "torch_device_count": existing_hw.get("torch_device_count") or len(gpus),
        "torch_cuda_error": existing_hw.get("torch_cuda_error"),
        "nvidia_smi_error": existing_hw.get("nvidia_smi_error"),
        "detection_sources": list(profile.get("detection_sources") or []),
        "warnings": warnings,
    }


def _augment_payload_with_hardware(payload: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(payload or {})
    hw = _hardware_status_from_payload(out)

    existing_hw = dict(out.get("hardware") or {})
    existing_hw.update({
        "accelerator": hw["accelerator_class"],
        "gpu_detected": hw["gpu_detected"],
        "gpu_name": hw["gpu_name"],
        "vram_gb": hw["total_vram_gb"],
        "free_vram_gb": hw["free_vram_gb"],
        "torch_cuda_available": hw["torch_cuda_available"],
        "torch_cuda_built": hw["torch_cuda_built"],
        "torch_cuda_version": hw["torch_cuda_version"],
        "torch_version": hw["torch_version"],
        "torch_device_count": hw["torch_device_count"],
        "torch_cuda_error": hw["torch_cuda_error"],
        "nvidia_smi_error": hw["nvidia_smi_error"],
        "detection_sources": hw["detection_sources"],
    })
    out["hardware"] = existing_hw

    if hw["warnings"]:
        out["hardware_warning"] = hw["warnings"][0]
    elif hw["accelerator_class"] == "gpu_unhealthy":
        out["hardware_warning"] = (
            "GPU detected, but PyTorch CUDA initialization is currently failing. "
            "Recommendations may be pessimistic until CUDA is healthy."
        )

    return out


def _resolve_llm_engines_config() -> str:
    """Return a path to an llm_engines.yaml that exists.

    Returns a string path because the CLI helpers accept strings.
    """
    user_cfg = Path("~/.engram/llm_engines.yaml").expanduser()
    if user_cfg.exists():
        return str(user_cfg)

    # Fall back to the bundled config inside the installed package.
    import engram.engine  # local import to keep UI imports lightweight

    bundled = Path(engram.engine.__file__).resolve().parent / "llm_engines.yaml"
    if bundled.exists():
        return str(bundled)

    # As a last resort, raise a clear error.
    raise FileNotFoundError(
        "Could not find llm_engines.yaml. Expected either ~/.engram/llm_engines.yaml "
        "or the bundled engram/engine/llm_engines.yaml."
    )


def doctor(profile: str, pull_missing: bool = False) -> Dict[str, Any]:
    """Return the same dict payload as `engram doctor --json`, augmented with shared hardware status."""
    cfg = _resolve_llm_engines_config()
    payload = run_doctor(profile=profile, pull_missing=pull_missing, config=cfg)
    return _augment_payload_with_hardware(payload)


def recommend(profile: str) -> Dict[str, Any]:
    """Return the same dict payload as `engram recommend --json`, augmented with shared hardware status."""
    cfg = _resolve_llm_engines_config()
    payload = run_recommend(profile=profile, config=cfg)
    return _augment_payload_with_hardware(payload)


def system_info(profile: str = "default_local") -> Any:
    """Return a model_manager.SystemInfo built from the shared recommend payload."""
    payload = recommend(profile=profile)
    from engram.engine.model_manager import GPUInfo, SystemInfo

    hw = _hardware_status_from_payload(payload)
    profile_data = dict(payload.get("hardware_profile") or {})
    gpus = []
    for raw in list(profile_data.get("gpus") or []):
        gpus.append(
            GPUInfo(
                name=str(raw.get("name") or "GPU"),
                vram_gb=float(raw.get("vram_mb", 0) or 0) / 1024.0,
                index=int(raw.get("id", raw.get("index", 0)) or 0),
                accelerator="cuda" if hw["accelerator_class"] in {"gpu", "gpu_unhealthy"} else hw["accelerator_class"],
            )
        )

    if not gpus and hw.get("gpu_name") and hw.get("total_vram_gb"):
        gpus.append(
            GPUInfo(
                name=str(hw["gpu_name"]),
                vram_gb=float(hw["total_vram_gb"] or 0.0),
                index=0,
                accelerator="cuda" if hw["accelerator_class"] in {"gpu", "gpu_unhealthy"} else hw["accelerator_class"],
            )
        )

    warning = payload.get("hardware_warning")
    if not warning and hw["warnings"]:
        warning = hw["warnings"][0]

    return SystemInfo(
        ram_gb=_gb_from_mb(profile_data.get("memory_total_mb")),
        gpus=gpus,
        total_vram_gb=float(hw.get("total_vram_gb") or 0.0),
        accelerator=str(hw.get("accelerator_class") or "cpu"),
        warning=warning,
    )
