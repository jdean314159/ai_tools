"""Capture a privacy-bounded llama.cpp endpoint fingerprint for paired runs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


SCHEMA = "temporary-llamacpp-endpoint-snapshot/v1"
MODEL_META_KEYS = ("n_vocab", "n_ctx", "n_ctx_train", "n_embd", "n_params", "size", "ftype")


def _get_json(base_url: str, path: str, *, timeout: float) -> tuple[Any, dict[str, str]]:
    request = Request(f"{base_url.rstrip('/')}{path}", headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator-supplied endpoint
        headers = {key.lower(): value for key, value in response.headers.items()}
        return json.loads(response.read()), headers


def _basename(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return Path(value).name


def sanitize_snapshot(
    health: Any,
    models: Any,
    props: Any,
    slots: Any,
    *,
    server_header: str | None,
    reference: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reduce endpoint responses to configuration evidence without prompts or paths."""
    model_rows = models.get("data", []) if isinstance(models, dict) else []
    model_row = model_rows[0] if model_rows and isinstance(model_rows[0], dict) else {}
    meta = model_row.get("meta", {}) if isinstance(model_row.get("meta"), dict) else {}
    model_label = _basename(model_row.get("id"))

    props = props if isinstance(props, dict) else {}
    default_settings = props.get("default_generation_settings", {})
    if not isinstance(default_settings, dict):
        default_settings = {}
    default_params = default_settings.get("params", {})
    if not isinstance(default_params, dict):
        default_params = {}

    slot_rows = slots if isinstance(slots, list) else []
    safe_slots = []
    for row in slot_rows:
        if not isinstance(row, dict):
            continue
        params = row.get("params", {})
        if not isinstance(params, dict):
            params = {}
        safe_slots.append(
            {
                "id": row.get("id"),
                "is_processing": row.get("is_processing"),
                "n_ctx": row.get("n_ctx"),
                "speculative": row.get("speculative"),
                "speculative_types": row.get("speculative.types")
                or params.get("speculative.types"),
            }
        )

    reference = reference or {}
    fingerprint = {
        "launch_configuration": reference.get("launch_configuration"),
        "llama_build": props.get("build_info") or reference.get("llama_build"),
        "model_label": model_label or _basename(props.get("model_path")),
        "model_meta": {key: meta.get(key) for key in MODEL_META_KEYS},
        "model_ftype": props.get("model_ftype"),
        "total_slots": props.get("total_slots"),
        "default_n_ctx": default_settings.get("n_ctx"),
        "default_speculative_types": default_params.get("speculative.types"),
        "slots": safe_slots,
    }
    canonical = json.dumps(fingerprint, sort_keys=True, separators=(",", ":")).encode()
    return {
        "schema": SCHEMA,
        "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "privacy": {
            "endpoint_retained": False,
            "model_directory_retained": False,
            "prompts_or_slot_tasks_retained": False,
        },
        "health": health.get("status") if isinstance(health, dict) else None,
        "http_server_header": server_header,
        "fingerprint": fingerprint,
        "fingerprint_sha256": hashlib.sha256(canonical).hexdigest(),
    }


def capture(base_url: str, *, timeout: float, reference: dict[str, Any] | None = None) -> dict:
    health, health_headers = _get_json(base_url, "/health", timeout=timeout)
    models, _ = _get_json(base_url, "/v1/models", timeout=timeout)
    props, _ = _get_json(base_url, "/props", timeout=timeout)
    slots, _ = _get_json(base_url, "/slots", timeout=timeout)
    return sanitize_snapshot(
        health,
        models,
        props,
        slots,
        server_header=health_headers.get("server"),
        reference=reference,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-fingerprint", type=Path)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    if args.output.exists():
        parser.error(f"refusing to overwrite {args.output}")

    reference = None
    if args.reference_fingerprint:
        reference = json.loads(args.reference_fingerprint.read_text(encoding="utf-8"))
    snapshot = capture(args.base_url, timeout=args.timeout, reference=reference)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    print(snapshot["fingerprint_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
