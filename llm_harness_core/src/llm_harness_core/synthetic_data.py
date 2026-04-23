from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from .documents import MemoryRecord, RetrievedDocument

Preset = Literal["clean", "noisy", "adversarial"]


@dataclass(frozen=True)
class SyntheticDataConfig:
    topic: str
    preset: Preset = "clean"
    memory_count: int = 24
    retrieval_count: int = 24
    seed: int = 7


@dataclass(frozen=True)
class SyntheticDataBundle:
    topic: str
    preset: Preset
    seed: int
    memory_records: tuple[MemoryRecord, ...] = ()
    retrieved_documents: tuple[RetrievedDocument, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


_CANONICAL_FACTS = [
    ("region", "us-west-2"),
    ("docs_policy", "Markdown files committed to the repo"),
    ("summary_model", "qwen3:32b"),
    ("analytics_db", "DuckDB"),
    ("review_time", "Wednesday at 2 PM"),
    ("sandbox", "docker"),
]


def _topic_slug(topic: str) -> str:
    return "-".join(part for part in topic.lower().replace("/", " ").split() if part)


def _make_memory_text(topic: str, key: str, value: str) -> str:
    if key == "region":
        return f"Update: deploy the {topic} nightly evaluation job in {value}."
    if key == "docs_policy":
        return f"Preference: keep durable {topic} docs in {value}."
    if key == "summary_model":
        return f"Correction: for long batch summaries in {topic}, prefer {value}."
    if key == "analytics_db":
        return f"Decision: use {value} for {topic} analytics work."
    if key == "review_time":
        return f"Update: the {topic} architecture review is scheduled for {value}."
    if key == "sandbox":
        return f"Decision: sandbox {topic} command execution through {value} when available."
    return f"Decision: {topic} {key} should use {value}."


def _make_memory_contradiction(topic: str, key: str, value: str) -> str:
    if key == "region":
        return f"Historical note: older {topic} deployment plans mentioned us-east-1 instead of {value}."
    if key == "docs_policy":
        return f"Historical note: some older {topic} notes referenced Google Docs instead of {value}."
    if key == "summary_model":
        return f"Historical note: earlier {topic} summaries used qwen3:8b instead of {value}."
    if key == "analytics_db":
        return f"Historical note: a past {topic} analytics prototype used SQLite instead of {value}."
    if key == "review_time":
        return f"Historical note: the {topic} review used to be on Tuesday morning instead of {value}."
    if key == "sandbox":
        return f"Historical note: an early {topic} prototype ran commands directly on the host instead of {value}."
    return f"Historical note: an older {topic} plan contradicted the current {key} value {value}."


def _make_memory_noise(topic: str, index: int) -> str:
    noise = [
        f"For this message only, answer cheerfully about {topic}.",
        f"Noise: the {topic} migration deck used a blue theme in Q1.",
        f"Transient note: someone once asked whether {topic} should be capitalized.",
        f"Assistant chatter: maybe add more comments to {topic} examples.",
        f"Noise: an old {topic} brainstorming session mentioned coffee mugs.",
    ]
    return noise[index % len(noise)]


def _make_doc_text(topic: str, key: str, value: str) -> str:
    title_map = {
        "region": f"{topic} deployment runbook",
        "docs_policy": f"{topic} documentation standard",
        "summary_model": f"{topic} batch summary policy",
        "analytics_db": f"{topic} analytics platform note",
        "review_time": f"{topic} architecture cadence",
        "sandbox": f"{topic} tool execution policy",
    }
    body_map = {
        "region": f"Current deployment guidance for {topic}: run the nightly evaluation job in {value}. This supersedes older region notes.",
        "docs_policy": f"Durable documentation for {topic} belongs in {value}; avoid external docs for canonical records.",
        "summary_model": f"For long batch summaries in {topic}, use {value} as the preferred model.",
        "analytics_db": f"For {topic} analytics workloads, the current local database choice is {value}.",
        "review_time": f"The current {topic} architecture review time is {value}.",
        "sandbox": f"When available, {topic} command execution should be sandboxed through {value}.",
    }
    return title_map.get(key, f"{topic} note") + "\n\n" + body_map.get(key, f"{topic} {key} uses {value}.")


def _make_doc_contradiction(topic: str, key: str, value: str) -> tuple[str, str]:
    if key == "region":
        return (f"Astronomy: Mercury observation region", f"The planet Mercury is often observed from east-facing facilities; this note is unrelated to the {topic} project.")
    if key == "docs_policy":
        return (f"Legacy {topic} wiki migration plan", f"A 2024 draft suggested Google Docs for {topic}, but it was never adopted.")
    if key == "summary_model":
        return (f"Legacy {topic} summary benchmark", f"A historical benchmark used qwen3:8b for {topic} summaries before the current policy changed.")
    if key == "analytics_db":
        return (f"Legacy {topic} prototype analytics", f"An earlier prototype used SQLite for {topic} analytics before the current database decision.")
    if key == "review_time":
        return (f"Archived {topic} meeting schedule", f"An archived schedule listed Tuesday morning for the {topic} review before the change.")
    if key == "sandbox":
        return (f"Draft {topic} execution note", f"An early draft said host execution was acceptable for {topic}, but that guidance is obsolete.")
    return (f"Legacy {topic} note", f"An older note contradicted the current {key} value {value}.")


def _make_doc_noise(topic: str, index: int) -> tuple[str, str]:
    items = [
        (f"{topic} style guide draft", f"The {topic} deck should use a blue title slide and larger footer text."),
        (f"{topic} office snack poll", f"The {topic} team preferred almonds over cookies in a 2025 office poll."),
        (f"{topic} glossary stub", f"This note only defines a few placeholder terms for {topic}."),
        (f"{topic} archived brainstorm", f"A brainstorm mentioned running {topic} in Antarctica; this was never serious."),
        (f"{topic} naming ideas", f"The {topic} codename shortlist included Atlas, Mercury, and Drift."),
    ]
    return items[index % len(items)]


def generate_memory_records(
    topic: str,
    *,
    count: int = 24,
    preset: Preset = "clean",
    seed: int = 7,
) -> list[MemoryRecord]:
    rng = random.Random(seed)
    slug = _topic_slug(topic)
    records: list[MemoryRecord] = []
    facts = list(_CANONICAL_FACTS)
    rng.shuffle(facts)

    target_noise_ratio = {"clean": 0.1, "noisy": 0.3, "adversarial": 0.25}[preset]
    target_contradiction_ratio = {"clean": 0.1, "noisy": 0.2, "adversarial": 0.4}[preset]
    noise_slots = max(1, int(count * target_noise_ratio))
    contradiction_slots = max(1, int(count * target_contradiction_ratio))

    i = 0
    while len(records) < count:
        key, value = facts[i % len(facts)]
        text = _make_memory_text(topic, key, value)
        records.append(
            MemoryRecord(
                text=text,
                source="synthetic_memory",
                record_id=f"mem-{slug}-{len(records):03d}",
                score=round(rng.uniform(0.72, 0.98), 3),
                metadata={
                    "topic": topic,
                    "fact_key": key,
                    "record_kind": "canonical",
                    "preset": preset,
                },
            )
        )
        i += 1
        if len(records) >= count:
            break
        if contradiction_slots > 0:
            records.append(
                MemoryRecord(
                    text=_make_memory_contradiction(topic, key, value),
                    source="synthetic_memory",
                    record_id=f"mem-{slug}-{len(records):03d}",
                    score=round(rng.uniform(0.15, 0.65), 3),
                    metadata={
                        "topic": topic,
                        "fact_key": key,
                        "record_kind": "contradiction",
                        "preset": preset,
                    },
                )
            )
            contradiction_slots -= 1
        if len(records) < count and noise_slots > 0:
            records.append(
                MemoryRecord(
                    text=_make_memory_noise(topic, len(records)),
                    source="synthetic_memory",
                    record_id=f"mem-{slug}-{len(records):03d}",
                    score=round(rng.uniform(0.01, 0.3), 3),
                    metadata={
                        "topic": topic,
                        "record_kind": "noise",
                        "preset": preset,
                    },
                )
            )
            noise_slots -= 1

    return records[:count]


def generate_retrieval_documents(
    topic: str,
    *,
    count: int = 24,
    preset: Preset = "clean",
    seed: int = 7,
) -> list[RetrievedDocument]:
    rng = random.Random(seed + 101)
    slug = _topic_slug(topic)
    docs: list[RetrievedDocument] = []
    facts = list(_CANONICAL_FACTS)
    rng.shuffle(facts)

    target_noise_ratio = {"clean": 0.15, "noisy": 0.35, "adversarial": 0.25}[preset]
    target_contradiction_ratio = {"clean": 0.1, "noisy": 0.2, "adversarial": 0.45}[preset]
    noise_slots = max(1, int(count * target_noise_ratio))
    contradiction_slots = max(1, int(count * target_contradiction_ratio))

    i = 0
    while len(docs) < count:
        key, value = facts[i % len(facts)]
        text = _make_doc_text(topic, key, value)
        docs.append(
            RetrievedDocument(
                text=text,
                source="synthetic_retrieval",
                doc_id=f"doc-{slug}-{len(docs):03d}",
                title=text.split("\n", 1)[0],
                score=round(rng.uniform(0.72, 0.98), 3),
                metadata={
                    "topic": topic,
                    "fact_key": key,
                    "doc_kind": "canonical",
                    "preset": preset,
                },
            )
        )
        i += 1
        if len(docs) >= count:
            break
        if contradiction_slots > 0:
            title, body = _make_doc_contradiction(topic, key, value)
            docs.append(
                RetrievedDocument(
                    text=f"{title}\n\n{body}",
                    source="synthetic_retrieval",
                    doc_id=f"doc-{slug}-{len(docs):03d}",
                    title=title,
                    score=round(rng.uniform(0.1, 0.65), 3),
                    metadata={
                        "topic": topic,
                        "fact_key": key,
                        "doc_kind": "contradiction",
                        "preset": preset,
                    },
                )
            )
            contradiction_slots -= 1
        if len(docs) < count and noise_slots > 0:
            title, body = _make_doc_noise(topic, len(docs))
            docs.append(
                RetrievedDocument(
                    text=f"{title}\n\n{body}",
                    source="synthetic_retrieval",
                    doc_id=f"doc-{slug}-{len(docs):03d}",
                    title=title,
                    score=round(rng.uniform(0.01, 0.3), 3),
                    metadata={
                        "topic": topic,
                        "doc_kind": "noise",
                        "preset": preset,
                    },
                )
            )
            noise_slots -= 1

    return docs[:count]


def generate_synthetic_bundle(config: SyntheticDataConfig) -> SyntheticDataBundle:
    memory_records = tuple(
        generate_memory_records(
            config.topic,
            count=config.memory_count,
            preset=config.preset,
            seed=config.seed,
        )
    )
    retrieved_documents = tuple(
        generate_retrieval_documents(
            config.topic,
            count=config.retrieval_count,
            preset=config.preset,
            seed=config.seed,
        )
    )
    metadata = {
        "topic": config.topic,
        "preset": config.preset,
        "seed": config.seed,
        "memory_count": len(memory_records),
        "retrieval_count": len(retrieved_documents),
    }
    return SyntheticDataBundle(
        topic=config.topic,
        preset=config.preset,
        seed=config.seed,
        memory_records=memory_records,
        retrieved_documents=retrieved_documents,
        metadata=metadata,
    )


def write_synthetic_bundle(bundle: SyntheticDataBundle, output_dir: str | Path) -> dict[str, Path]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    memory_path = out / "memory_records.jsonl"
    retrieval_path = out / "retrieved_documents.jsonl"
    manifest_path = out / "manifest.json"

    with memory_path.open("w", encoding="utf-8") as f:
        for record in bundle.memory_records:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    with retrieval_path.open("w", encoding="utf-8") as f:
        for doc in bundle.retrieved_documents:
            f.write(json.dumps(asdict(doc), ensure_ascii=False) + "\n")

    manifest = {
        "topic": bundle.topic,
        "preset": bundle.preset,
        "seed": bundle.seed,
        "memory_count": len(bundle.memory_records),
        "retrieval_count": len(bundle.retrieved_documents),
        "files": {
            "memory_records": memory_path.name,
            "retrieved_documents": retrieval_path.name,
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {
        "memory_records": memory_path,
        "retrieved_documents": retrieval_path,
        "manifest": manifest_path,
    }
