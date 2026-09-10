"""Run the frozen single-turn Ornith oracle-localization B/C matrix."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from typing import Any

from llm_engines.backends.openai import OpenAIEngine
from llm_engines.contracts import ChatMessage, GenerationRequest


TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parents[3]
CAMPAIGN_REL = Path(
    "docs/projects/repository_assessment/runs/2026-09-10-ornith-oracle-localization-abc"
)


def _load_scorer() -> Any:
    path = TOOLS_DIR / "score_oracle_localization.py"
    spec = importlib.util.spec_from_file_location("oracle_localization_scorer", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load scorer: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


scorer = _load_scorer()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_freeze(campaign_root: Path) -> dict[str, Any]:
    manifest_path = campaign_root / "freeze-manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("missing freeze-manifest.json")
    manifest = load_json(manifest_path)
    errors = []
    for relative, expected in manifest.get("sha256", {}).items():
        path = REPO_ROOT / relative
        if not path.is_file():
            errors.append(f"missing:{relative}")
        elif sha256_bytes(path.read_bytes()) != expected:
            errors.append(f"digest:{relative}")
    if errors:
        raise RuntimeError("freeze verification failed: " + ", ".join(errors))
    return manifest


def _language(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {".py": "python", ".yaml": "yaml", ".yml": "yaml"}.get(suffix, "text")


def render_messages(
    *, condition: str, item: dict[str, Any], oracle: dict[str, Any], prompts: dict[str, Any]
) -> list[ChatMessage]:
    values = {
        "path": item["path"],
        "start_line": item["start_line"],
        "end_line": item["end_line"],
        "language": _language(item["path"]),
        "text": item["text"],
        "hypothesis": oracle["hypothesis"],
    }
    template_key = "condition_b_user_template" if condition == "B" else "condition_c_user_template"
    return [
        ChatMessage(role="system", content=prompts["system"]),
        ChatMessage(role="user", content=prompts[template_key].format(**values)),
    ]


def run_one(
    *,
    engine: OpenAIEngine,
    run: dict[str, Any],
    item: dict[str, Any],
    oracle: dict[str, Any],
    prompts: dict[str, Any],
    matrix: dict[str, Any],
    fingerprint: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=False, exist_ok=False)
    messages = render_messages(condition=run["condition"], item=item, oracle=oracle, prompts=prompts)
    request_record = {
        "at": utc_now(),
        "event": "request",
        "run_id": run["run_id"],
        "condition": run["condition"],
        "item_id": run["item_id"],
        "seed": run["seed"],
        "temperature": matrix["temperature"],
        "thinking": matrix["thinking"],
        "max_tokens": matrix["max_tokens"],
        "messages": [message.model_dump(mode="json") for message in messages],
        "json_schema": scorer.response_schema(run["condition"]),
    }
    transcript_path = output_dir / "transcript.jsonl"
    transcript_path.write_text(json.dumps(request_record, sort_keys=True) + "\n", encoding="utf-8")
    started_at = utc_now()
    started = time.perf_counter()
    try:
        response = engine.generate(
            GenerationRequest(
                messages=messages,
                max_tokens=matrix["max_tokens"],
                temperature=matrix["temperature"],
                thinking=matrix["thinking"],
                seed=run["seed"],
                json_schema=scorer.response_schema(run["condition"]),
            )
        )
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        error_record = {
            "at": utc_now(),
            "event": "generation_error",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "elapsed_ms": elapsed_ms,
        }
        with transcript_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(error_record, sort_keys=True) + "\n")
        metadata = {
            "schema": "oracle-localization-run/v1",
            **run,
            "lifecycle": "aborted",
            "validity": "invalid",
            "invalid_reason": "generation_exception",
            "started_at": started_at,
            "finished_at": utc_now(),
            "elapsed_ms": elapsed_ms,
            "transcript_sha256": sha256_bytes(transcript_path.read_bytes()),
        }
        write_json(output_dir / "run-metadata.json", metadata)
        raise

    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    raw_text = response.text
    (output_dir / "raw-response.txt").write_text(raw_text, encoding="utf-8")
    parsed, parse_error = scorer.parse_response(raw_text, run["condition"])
    if parsed is not None:
        write_json(output_dir / "parsed-response.json", parsed)
    response_record = {
        "at": utc_now(),
        "event": "response",
        "content": raw_text,
        "finish_reason": response.finish_reason,
        "seed_status": response.seed_status,
        "usage": response.usage.model_dump(mode="json"),
        "model_name": response.model_name,
        "backend": response.backend,
        "elapsed_ms": elapsed_ms,
    }
    with transcript_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(response_record, sort_keys=True) + "\n")
    invalid_reasons = []
    if response.finish_reason != "stop":
        invalid_reasons.append(f"finish_reason:{response.finish_reason}")
    if response.seed_status != "accepted":
        invalid_reasons.append(f"seed_status:{response.seed_status}")
    if parse_error:
        invalid_reasons.append(parse_error)
    metadata = {
        "schema": "oracle-localization-run/v1",
        **run,
        "lifecycle": "final" if not invalid_reasons else "aborted",
        "validity": "valid" if not invalid_reasons else "invalid",
        "invalid_reasons": invalid_reasons,
        "started_at": started_at,
        "finished_at": utc_now(),
        "elapsed_ms": elapsed_ms,
        "model": fingerprint["fingerprint"]["model_label"],
        "fingerprint_sha256": fingerprint["fingerprint_sha256"],
        "temperature": matrix["temperature"],
        "thinking": matrix["thinking"],
        "max_tokens": matrix["max_tokens"],
        "finish_reason": response.finish_reason,
        "seed_status": response.seed_status,
        "usage": response.usage.model_dump(mode="json"),
        "span_sha256": item["sha256"],
        "prompt_sha256": {
            "system": sha256_bytes((messages[0].content or "").encode()),
            "user": sha256_bytes((messages[1].content or "").encode()),
        },
        "raw_response_sha256": sha256_bytes(raw_text.encode()),
        "transcript_sha256": sha256_bytes(transcript_path.read_bytes()),
    }
    write_json(output_dir / "run-metadata.json", metadata)
    if invalid_reasons:
        raise RuntimeError(f"invalid model response for {run['run_id']}: {invalid_reasons}")
    return metadata


def run_matrix(
    *, campaign_root: Path, generation_set: str, base_url: str, model: str, fingerprint_path: Path
) -> None:
    verify_freeze(campaign_root)
    spans = load_json(campaign_root / "span-manifest.json")
    oracle_payload = load_json(campaign_root / "oracle-manifest.json")
    prompts = load_json(campaign_root / "prompts.json")
    matrix = load_json(campaign_root / "run-matrix.json")
    fingerprint = load_json(fingerprint_path)
    if model != matrix["model"]:
        raise RuntimeError(f"model must be {matrix['model']}")
    if fingerprint["fingerprint"].get("model_label") != matrix["model"]:
        raise RuntimeError("endpoint fingerprint model does not match frozen matrix")
    items = {row["item_id"]: row for row in spans["items"]}
    oracles = {row["pair_id"]: row for row in oracle_payload["oracles"]}
    output_root = campaign_root / generation_set
    output_root.mkdir(parents=False, exist_ok=False)
    write_json(output_root / "endpoint-before.json", fingerprint)
    engine = OpenAIEngine(
        model=model,
        api_key="not-required",
        base_url=base_url,
        is_cloud=False,
        timeout=180,
    )
    for run in matrix["runs"]:
        item = items[run["item_id"]]
        run_one(
            engine=engine,
            run=run,
            item=item,
            oracle=oracles[item["pair_id"]],
            prompts=prompts,
            matrix=matrix,
            fingerprint=fingerprint,
            output_dir=output_root / run["run_id"],
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-root", type=Path, default=REPO_ROOT / CAMPAIGN_REL)
    parser.add_argument("--generation-set", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--fingerprint", type=Path, required=True)
    args = parser.parse_args()
    if not re_fullmatch_generation_set(args.generation_set):
        parser.error("generation-set must match generations or generations-rerun-N")
    run_matrix(
        campaign_root=args.campaign_root,
        generation_set=args.generation_set,
        base_url=args.base_url,
        model=args.model,
        fingerprint_path=args.fingerprint,
    )
    return 0


def re_fullmatch_generation_set(value: str) -> bool:
    import re

    return re.fullmatch(r"generations(?:-rerun-[1-9][0-9]*)?", value) is not None


if __name__ == "__main__":
    raise SystemExit(main())
