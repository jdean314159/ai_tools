"""Formatter-only feasibility probe for NAV-VERIFIABLE-00 relation claims."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from llm_engines.contracts import (
    ChatMessage,
    GenerationRequest,
    GenerationResponse,
    UsageStats,
)

from .verifiable_navigation import (
    RELATION_CLAIMS_SCHEMA,
    PythonRelationOracle,
    RelationClaim,
    VerifiableTask,
    load_verifiable_task_set,
    relation_claims_shape_error,
    score_verifiable_claims,
)


PROBE_TASK_IDS = ("direct_callers", "call_path", "mutation_target")

RELATION_PROBE_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"relation_claims": RELATION_CLAIMS_SCHEMA},
    "required": ["relation_claims"],
}


class ProbeModel(Protocol):
    def generate(self, request: GenerationRequest) -> GenerationResponse: ...


def run_relation_schema_probe(
    *,
    engine: ProbeModel,
    fixture_root: str | Path,
    task_set_path: str | Path,
    temperature: float = 0.0,
    max_tokens: int = 1_024,
) -> dict[str, Any]:
    root = Path(fixture_root).resolve(strict=True)
    tasks = {
        task.task_id: task for task in load_verifiable_task_set(task_set_path, source_root=root)
    }
    oracle = PythonRelationOracle(root)
    source_text = {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*.py"))
    }
    trials: list[dict[str, Any]] = []
    for task_id in PROBE_TASK_IDS:
        task = tasks[task_id]
        messages = _probe_messages(task, source_text)
        response = engine.generate(
            GenerationRequest(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                json_schema=RELATION_PROBE_RESPONSE_SCHEMA,
                metadata={
                    "eval": "NAV-VERIFIABLE-00-schema-probe",
                    "task_id": task.task_id,
                },
            )
        )
        trials.append(
            _score_probe_response(
                task=task,
                response=response,
                oracle=oracle,
                observed_lines={
                    path: set(range(1, len(text.splitlines()) + 1))
                    for path, text in source_text.items()
                },
            )
        )
    return {
        "schema_version": 1,
        "track": "NAV-VERIFIABLE-00",
        "probe": "relation-schema-formatter",
        "formatter_only": True,
        "temperature": temperature,
        "trials": trials,
        "passed": all(bool(trial["passed"]) for trial in trials),
    }


def replay_relation_schema_probe(
    record: dict[str, Any],
    *,
    fixture_root: str | Path,
    task_set_path: str | Path,
) -> dict[str, Any]:
    """Rescore saved response text without another model invocation."""

    root = Path(fixture_root).resolve(strict=True)
    tasks = {
        task.task_id: task for task in load_verifiable_task_set(task_set_path, source_root=root)
    }
    oracle = PythonRelationOracle(root)
    observed_lines = {
        path.relative_to(root).as_posix(): set(
            range(1, len(path.read_text(encoding="utf-8").splitlines()) + 1)
        )
        for path in sorted(root.rglob("*.py"))
    }
    rescored: list[dict[str, Any]] = []
    for saved in record.get("trials") or []:
        task_id = str(saved.get("task_id") or "")
        usage = saved.get("usage") if isinstance(saved.get("usage"), dict) else {}
        response = GenerationResponse(
            message=ChatMessage(
                role="assistant",
                content=str(saved.get("response_text") or ""),
            ),
            finish_reason=str(saved.get("finish_reason") or "unknown"),
            usage=UsageStats(**usage),
            model_name=str(saved.get("model") or "saved"),
            backend=str(saved.get("backend") or "replay"),
        )
        rescored.append(
            _score_probe_response(
                task=tasks[task_id],
                response=response,
                oracle=oracle,
                observed_lines=observed_lines,
            )
        )
    return {
        "schema_version": 1,
        "track": "NAV-VERIFIABLE-00",
        "probe": "relation-schema-formatter-replay",
        "formatter_only": True,
        "source_record_probe": record.get("probe"),
        "trials": rescored,
        "passed": all(bool(trial["passed"]) for trial in rescored),
    }


def _probe_messages(
    task: VerifiableTask,
    source_text: dict[str, str],
) -> list[ChatMessage]:
    rendered_sources = []
    for path, text in source_text.items():
        numbered = "\n".join(
            f"{index}: {line}" for index, line in enumerate(text.splitlines(), start=1)
        )
        rendered_sources.append(f"FILE {path}\n{numbered}")
    return [
        ChatMessage(
            role="system",
            content=(
                "Return only JSON matching the supplied schema. Report exact static "
                "relations from the provided source. `path` is always the literal FILE "
                "path. Canonical symbols include the module derived from that path "
                "(sample.py -> sample.Pipeline.ingest). For a direct-callers task, emit "
                "only call_edge claims, one per direct caller. For a call-path task, emit "
                "exactly one call_path claim, not its component edges, and list every "
                "canonical symbol in order. For a named-site task, emit exactly one "
                "mutation_target whose target is the exact call expression. "
                "path_symbols must be empty except on call_path. Evidence paths must "
                "equal `path` and cite the minimal provided source lines."
            ),
        ),
        ChatMessage(
            role="user",
            content=(
                f"Task: {task.question}\n\n"
                + "\n\n".join(rendered_sources)
                + "\n\nReturn relation_claims only."
            ),
        ),
    ]


def _score_probe_response(
    *,
    task: VerifiableTask,
    response: GenerationResponse,
    oracle: PythonRelationOracle,
    observed_lines: dict[str, set[int]],
) -> dict[str, Any]:
    raw = response.message.content or ""
    errors: list[str] = []
    claims: list[RelationClaim] = []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        payload = {}
        errors.append(f"invalid JSON: {exc}")
    raw_claims = payload.get("relation_claims") if isinstance(payload, dict) else None
    shape_error = relation_claims_shape_error(raw_claims)
    if shape_error:
        errors.append(shape_error)
    elif isinstance(raw_claims, list):
        claims = [RelationClaim.from_mapping(item) for item in raw_claims if isinstance(item, dict)]
    score = score_verifiable_claims(
        task,
        claims,
        oracle=oracle,
        observed_lines=observed_lines,
    )
    errors.extend(score.errors)
    return {
        "task_id": task.task_id,
        "passed": not errors and score.correct,
        "schema_valid": shape_error is None
        and not any(error.startswith("invalid JSON") for error in errors),
        "relation_correct": score.relation_correct,
        "evidence_complete": score.evidence_complete,
        "evidence_precise": score.evidence_precise,
        "exact_correct": score.exact_correct,
        "errors": errors,
        "unsupported_claims": list(score.unsupported_claims),
        "incomplete_evidence_claims": list(score.incomplete_evidence_claims),
        "normalized_claims": list(score.normalized_claims),
        "imprecise_claims": list(score.imprecise_claims),
        "response_text": raw,
        "usage": response.usage.model_dump(),
        "model": response.model_name,
        "backend": response.backend,
        "finish_reason": response.finish_reason,
    }
