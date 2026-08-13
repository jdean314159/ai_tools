#!/usr/bin/env python3
"""Run one privacy-safe local generation and validate its durable artifact."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from llm_engines import (
    ChatMessage,
    GenerationRecordingPolicy,
    GenerationRequest,
    get_engine,
    record_generation,
)
from llm_harness_core import (
    PrivacyValidation,
    dump_artifact,
    load_artifact,
    summarize_artifact,
)


PROMPT = "Reply with exactly: RUN_RECORD_LIVE_OK"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default="qwen3:8b")
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")

    engine = get_engine(
        "ollama",
        args.model,
        think=False,
        debug=False,
        options={"seed": 0},
    )
    recorded = record_generation(
        engine,
        GenerationRequest(
            messages=[ChatMessage(role="user", content=PROMPT)],
            max_tokens=32,
            temperature=0.0,
            metadata={"acceptance": "RUN-RECORD-00-phase-3"},
        ),
        policy=GenerationRecordingPolicy(
            include_raw_provider_payload=False,
            body_bytes_sensitivity="public",
            declared_content_categories=("synthetic_acceptance_prompt", "model_output"),
            privacy_validation=PrivacyValidation(
                status="validated",
                validator="RUN-RECORD-00-maintainer-acceptance",
                policy_id="synthetic-fixed-prompt",
                policy_version="1",
                validated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                scope=("request messages", "response message", "raw payload omission"),
            ),
            usage_method="measured",
        ),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    dump_artifact(recorded.artifact, args.output)
    loaded = load_artifact(args.output)
    print(summarize_artifact(loaded))
    print({
        "text": recorded.response.text,
        "finish_reason": recorded.response.finish_reason,
        "usage": recorded.response.usage.model_dump(mode="json"),
        "backend": recorded.response.backend,
        "model": recorded.response.model_name,
        "raw_provider_payload_recorded": "raw_provider_payload" in loaded.body["response"],
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
