from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from llm_harness_core import CapabilityDescriptor, CapabilityKind
from engram.contracts import AugmentRequest, AugmentResult, PromptAugmenter


@dataclass
class AugmenterReadiness:
    augmenter_id: str
    can_run: bool
    severity: str  # "ok" | "warning" | "error"
    message: str
    details: dict[str, Any] = field(default_factory=dict)


class BaselineAugmenter(PromptAugmenter):
    augmenter_id = "baseline"

    def __init__(self, system_prompt: str = ""):
        self.system_prompt = system_prompt
        self._turns: list[tuple[str, str]] = []

    def new_session(self, session_id: str) -> None:
        self._turns = []

    def add_turn(self, role: str, text: str, session_id: str) -> None:
        self._turns.append((role, text))

    def describe_component(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            kind=CapabilityKind.MEMORY,
            provider="llm_inspector_ui",
            component="BaselineAugmenter",
            version="0.1.0",
            summary="Deterministic prompt assembly without memory retrieval.",
            features=("prompt_augmentation", "baseline_prompt"),
            input_types=("augment_request",),
            output_types=("prompt", "trace_event[]"),
            metadata={"augmenter_id": self.augmenter_id},
        )

    def augment(self, request: AugmentRequest) -> AugmentResult:
        sections: list[dict[str, Any]] = []

        if self.system_prompt.strip():
            sections.append(
                {
                    "title": "System",
                    "origin": "system",
                    "text": self.system_prompt,
                }
            )

        sections.append(
            {
                "title": "User",
                "origin": "user",
                "text": request.user_text,
            }
        )

        prompt = "\n\n".join(f"## {s['title']}\n{s['text']}" for s in sections).strip()

        trace = {
            "sections": sections
            + [
                {
                    "title": "Final prompt",
                    "origin": "prompt",
                    "text": prompt,
                }
            ],
            "evidence": [],
            "token_accounting": {
                "target_tokens": request.max_prompt_tokens,
                "total_tokens": len(prompt.split()),
                "per_origin_budget": {},
                "per_origin_used": {
                    s["origin"]: len(s["text"].split()) for s in sections
                },
                "truncated": False,
                "compressed": False,
                "notes": [],
            },
            "flags": {
                "compressed": False,
                "truncated": False,
                "query": request.query or request.user_text,
            },
            "final_prompt": prompt,
        }

        return AugmentResult(
            prompt=prompt,
            trace=trace,
            prompt_tokens=len(prompt.split()),
            memory_tokens=0,
            compressed=False,
            metadata={"source": "baseline", "prompt": prompt},
        )


class EngramLiteAugmenter(PromptAugmenter):
    augmenter_id = "engram_lite"

    def __init__(
        self,
        *,
        base_dir: str | Path,
        project_id: str = "default",
        session_id: Optional[str] = None,
        system_prompt: str = "",
    ):
        self.base_dir = Path(base_dir)
        self.project_id = project_id
        self.session_id = session_id
        self.system_prompt = system_prompt
        self._pm = None

    def _ensure_pm(self):
        if self._pm is not None:
            return self._pm
        from engram import ProjectMemory

        self._pm = ProjectMemory(
            base_dir=self.base_dir,
            project_id=self.project_id,
            session_id=self.session_id,
            system_prompt=self.system_prompt,
        )
        return self._pm

    def new_session(self, session_id: str) -> None:
        self.session_id = session_id
        self._ensure_pm().new_session(session_id)

    def add_turn(self, role: str, text: str, session_id: str) -> None:
        self._ensure_pm().add_turn(role, text, session_id)

    def describe_component(self) -> CapabilityDescriptor:
        descriptor = self._ensure_pm().describe_component()
        return CapabilityDescriptor(
            kind=descriptor.kind,
            provider=descriptor.provider,
            component="EngramLiteAugmenter",
            version=descriptor.version,
            summary=descriptor.summary,
            features=descriptor.features,
            input_types=descriptor.input_types,
            output_types=descriptor.output_types,
            metadata={
                **dict(descriptor.metadata),
                "augmenter_id": self.augmenter_id,
                "project_id": self.project_id,
                "base_dir": str(self.base_dir),
            },
        )

    def augment(self, request: AugmentRequest) -> AugmentResult:
        result = self._ensure_pm().augment(request)
        return AugmentResult(
            prompt=result.prompt,
            trace=result.trace,
            prompt_tokens=result.prompt_tokens,
            memory_tokens=result.memory_tokens,
            compressed=result.compressed,
            raw_context=result.raw_context,
            metadata={"source": "engram_lite", **dict(result.metadata)},
        )


class EngramAugmenter(PromptAugmenter):
    augmenter_id = "engram"

    def __init__(
        self,
        *,
        base_dir: str | Path,
        project_id: str = "default",
        project_type: str = "programming_assistant",
        session_id: Optional[str] = None,
    ):
        self.base_dir = Path(base_dir)
        self.project_id = project_id
        self.project_type = project_type
        self.session_id = session_id
        self._pm = None

    def _ensure_pm(self):
        if self._pm is not None:
            return self._pm

        from engram.project_memory import ProjectMemory

        try:
            from engram import ProjectType  # type: ignore
        except Exception:
            from engram.project_memory import ProjectType  # type: ignore

        self._pm = ProjectMemory(
            project_id=self.project_id,
            project_type=ProjectType(self.project_type),
            base_dir=self.base_dir,
            session_id=self.session_id,
            llm_engine=None,
        )
        return self._pm

    def new_session(self, session_id: str) -> None:
        self.session_id = session_id
        pm = self._ensure_pm()
        pm.new_session(session_id)

    def add_turn(self, role: str, text: str, session_id: str) -> None:
        pm = self._ensure_pm()
        pm.add_turn(role, text)

    def describe_component(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            kind=CapabilityKind.MEMORY,
            provider="engram",
            component="EngramAugmenter",
            version="0.1.0",
            summary="Engram-backed prompt augmentation with multi-layer memory retrieval.",
            features=("prompt_augmentation", "working_memory", "episodic_memory", "trace_events"),
            input_types=("augment_request",),
            output_types=("prompt", "trace_event[]", "operation_result"),
            metadata={
                "augmenter_id": self.augmenter_id,
                "project_id": self.project_id,
                "project_type": self.project_type,
                "base_dir": str(self.base_dir),
            },
        )

    def augment(self, request: AugmentRequest) -> AugmentResult:
        pm = self._ensure_pm()
        result = pm.build_prompt(
            user_message=request.user_text,
            query=request.query or request.user_text,
            max_prompt_tokens=request.max_prompt_tokens,
            reserve_output_tokens=request.reserve_output_tokens,
            return_trace=True,
        )
        return AugmentResult(
            prompt=result.get("prompt", ""),
            trace=result.get("trace"),
            prompt_tokens=result.get("prompt_tokens"),
            memory_tokens=result.get("memory_tokens"),
            compressed=bool(result.get("compressed", False)),
            raw_context=result.get("context"),
            metadata={"source": "engram", "result": result},
        )


class RagAugmenter(PromptAugmenter):
    augmenter_id = "rag"

    def __init__(
        self,
        *,
        config: str | Path | dict | None = None,
        collection: str = "default",
        system_prompt: str = "",
    ):
        self.config = config
        self.collection = collection
        self.system_prompt = system_prompt
        self._pipeline = None

    def _ensure_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline
        from rag_lib import RAGPipeline
        self._pipeline = RAGPipeline(config=self.config)
        return self._pipeline

    def new_session(self, session_id: str) -> None:
        return None

    def add_turn(self, role: str, text: str, session_id: str) -> None:
        return None

    def describe_component(self) -> CapabilityDescriptor:
        pipeline = self._ensure_pipeline()
        descriptor = pipeline.describe_component() if hasattr(pipeline, "describe_component") else CapabilityDescriptor(
            kind=CapabilityKind.RAG_PIPELINE,
            provider="rag_lib",
            component="RagAugmenter",
            version="0.1.0",
            summary="RAG-backed prompt augmentation.",
            features=("hybrid_retrieval", "retrieval_trace_events", "prompt_assembly"),
            input_types=("augment_request",),
            output_types=("prompt", "trace_event[]", "operation_result"),
            metadata={},
        )
        return CapabilityDescriptor(
            kind=descriptor.kind,
            provider=descriptor.provider,
            component="RagAugmenter",
            version=descriptor.version,
            summary=descriptor.summary,
            features=tuple(sorted(set(descriptor.features + ("augment_request",)))),
            input_types=descriptor.input_types,
            output_types=descriptor.output_types,
            metadata={**dict(descriptor.metadata), "augmenter_id": self.augmenter_id, "collection": self.collection},
        )

    def augment(self, request: AugmentRequest) -> AugmentResult:
        pipeline = self._ensure_pipeline()
        trace = pipeline.inspect_query(
            request.query or request.user_text,
            collection=self.collection,
            max_context_tokens=request.max_prompt_tokens,
            system_prompt=self.system_prompt,
        )
        sections = []
        if self.system_prompt.strip():
            sections.append({"title": "System", "origin": "system", "text": self.system_prompt})
        sections.append({"title": "User", "origin": "user", "text": request.user_text})
        if trace.selected_results:
            sections.append({
                "title": "RAG retrieved context",
                "origin": "rag",
                "text": "\n\n".join(doc.text for doc in trace.selected_results),
            })
        sections.append({"title": "Final prompt", "origin": "prompt", "text": trace.assembled_prompt})
        evidence = [
            {
                "text": doc.text,
                "source": "rag",
                "score": doc.score,
                "meta": {"doc_id": doc.doc_id, "title": doc.title, **dict(doc.metadata)},
            }
            for doc in trace.selected_results
        ]
        serializable = {
            "turn": {"role": "user", "text": request.user_text, "session_id": request.session_id},
            "context": {
                "sections": sections,
                "evidence": evidence,
                "token_accounting": {
                    "target_tokens": request.max_prompt_tokens,
                    "total_tokens": len(trace.assembled_prompt.split()),
                    "per_origin_budget": {},
                    "per_origin_used": {
                        section["origin"]: len(section["text"].split())
                        for section in sections
                        if isinstance(section.get("text"), str)
                    },
                    "truncated": False,
                    "compressed": False,
                    "notes": [],
                },
                "signals": {
                    "retrieval_summary": dict(trace.diagnostics),
                    "retrieval_documents": trace.to_serializable_dict(),
                },
                "notes": [],
            },
            "metrics": {
                "engine": None,
                "model": None,
                "latency_ms": None,
                "prompt_tokens": len(trace.assembled_prompt.split()),
                "output_tokens": None,
                "error": None,
            },
            "events": [
                {
                    "event_type": event.event_type,
                    "source_package": event.source_package,
                    "source_component": event.source_component,
                    "payload": dict(event.payload),
                    "severity": event.severity,
                    "message": event.message,
                    "event_id": event.event_id,
                    "span_id": event.span_id,
                    "parent_span_id": event.parent_span_id,
                    "ts": event.ts,
                    "tags": list(event.tags),
                }
                for event in trace.events
            ],
        }
        return AugmentResult(
            prompt=trace.assembled_prompt,
            trace=serializable,
            prompt_tokens=len(trace.assembled_prompt.split()),
            memory_tokens=sum(len(doc.text.split()) for doc in trace.selected_results),
            compressed=False,
            raw_context=trace.to_serializable_dict(),
            metadata={"source": "rag", "collection": self.collection},
        )


class AugmenterService:
    def __init__(
        self,
        *,
        engram_base_dir: str | Path = "./data/memory",
        engram_project_id: str = "default",
        engram_project_type: str = "programming_assistant",
    ):
        self.engram_base_dir = Path(engram_base_dir)
        self.engram_project_id = engram_project_id
        self.engram_project_type = engram_project_type

    def list_augmenters(self) -> list[str]:
        augmenters = ["baseline"]
        try:
            import engram  # noqa: F401
            augmenters.append("engram_lite")
        except Exception:
            pass
        try:
            import engram  # noqa: F401
            augmenters.append("engram")
        except Exception:
            pass
        try:
            import rag_lib  # noqa: F401
            augmenters.append("rag")
        except Exception:
            pass
        return augmenters

    def describe_augmenter(
        self,
        augmenter_id: str,
        *,
        options: Optional[dict[str, Any]] = None,
    ) -> CapabilityDescriptor:
        options = options or {}
        if augmenter_id == "baseline":
            return BaselineAugmenter(system_prompt=options.get("system_prompt", "")).describe_component()

        if augmenter_id == "engram_lite":
            return EngramLiteAugmenter(
                base_dir=options.get("base_dir", self.engram_base_dir),
                project_id=options.get("project_id", self.engram_project_id),
                session_id=options.get("session_id"),
                system_prompt=options.get("system_prompt", ""),
            ).describe_component()

        if augmenter_id == "engram":
            return EngramAugmenter(
                base_dir=options.get("base_dir", self.engram_base_dir),
                project_id=options.get("project_id", self.engram_project_id),
                project_type=options.get("project_type", self.engram_project_type),
                session_id=options.get("session_id"),
            ).describe_component()

        if augmenter_id == "rag":
            return RagAugmenter(
                config=options.get("config"),
                collection=options.get("collection", "default"),
                system_prompt=options.get("system_prompt", ""),
            ).describe_component()

        return CapabilityDescriptor(
            kind=CapabilityKind.MEMORY,
            provider="llm_inspector_ui",
            component=augmenter_id,
            version="0.1.0",
            summary="Unknown augmenter descriptor.",
            features=(),
            input_types=("augment_request",),
            output_types=("prompt",),
            metadata={"augmenter_id": augmenter_id},
        )

    def list_augmenter_capabilities(
        self,
        augmenter_ids: Optional[list[str]] = None,
        *,
        options_by_id: Optional[dict[str, dict[str, Any]]] = None,
    ) -> list[CapabilityDescriptor]:
        ids = augmenter_ids or self.list_augmenters()
        options_by_id = options_by_id or {}
        return [
            self.describe_augmenter(augmenter_id, options=options_by_id.get(augmenter_id, {}))
            for augmenter_id in ids
        ]

    def get_augmenter_readiness(
        self,
        augmenter_id: str,
        *,
        options: Optional[dict[str, Any]] = None,
    ) -> AugmenterReadiness:
        options = options or {}

        if augmenter_id == "baseline":
            return AugmenterReadiness(
                augmenter_id="baseline",
                can_run=True,
                severity="ok",
                message="Baseline augmenter is ready.",
                details={},
            )

        if augmenter_id == "engram_lite":
            try:
                import engram  # noqa: F401
                from engram import ProjectMemory  # noqa: F401

                base_dir = Path(options.get("base_dir", self.engram_base_dir))
                project_id = str(options.get("project_id", self.engram_project_id))

                return AugmenterReadiness(
                    augmenter_id="engram_lite",
                    can_run=True,
                    severity="ok",
                    message="engram_lite augmenter is ready.",
                    details={
                        "base_dir": str(base_dir),
                        "project_id": project_id,
                    },
                )
            except Exception as exc:
                return AugmenterReadiness(
                    augmenter_id="engram_lite",
                    can_run=False,
                    severity="error",
                    message=f"engram_lite is not available: {type(exc).__name__}: {exc}",
                    details={},
                )

        if augmenter_id == "engram":
            try:
                import engram  # noqa: F401
                from engram.project_memory import ProjectMemory  # noqa: F401

                try:
                    from engram import ProjectType  # type: ignore  # noqa: F401
                except Exception:
                    from engram.project_memory import ProjectType  # type: ignore  # noqa: F401

                base_dir = Path(options.get("base_dir", self.engram_base_dir))
                project_id = str(options.get("project_id", self.engram_project_id))
                project_type = str(options.get("project_type", self.engram_project_type))

                return AugmenterReadiness(
                    augmenter_id="engram",
                    can_run=True,
                    severity="ok",
                    message="Engram augmenter is ready.",
                    details={
                        "base_dir": str(base_dir),
                        "project_id": project_id,
                        "project_type": project_type,
                    },
                )
            except Exception as exc:
                return AugmenterReadiness(
                    augmenter_id="engram",
                    can_run=False,
                    severity="error",
                    message=f"Engram is not available: {type(exc).__name__}: {exc}",
                    details={},
                )

        if augmenter_id == "rag":
            try:
                import rag_lib  # noqa: F401
                config = options.get("config")
                collection = str(options.get("collection", "default"))
                return AugmenterReadiness(
                    augmenter_id="rag",
                    can_run=True,
                    severity="ok",
                    message="RAG augmenter is ready.",
                    details={"config": config, "collection": collection},
                )
            except Exception as exc:
                return AugmenterReadiness(
                    augmenter_id="rag",
                    can_run=False,
                    severity="error",
                    message=f"rag_lib is not available: {type(exc).__name__}: {exc}",
                    details={},
                )

        return AugmenterReadiness(
            augmenter_id=augmenter_id,
            can_run=False,
            severity="error",
            message=f"Unknown augmenter: {augmenter_id}",
            details={},
        )

    def create(self, augmenter_id: str, *, session_id: str, options: Optional[dict[str, Any]] = None):
        options = options or {}

        if augmenter_id == "baseline":
            return BaselineAugmenter(system_prompt=options.get("system_prompt", ""))

        if augmenter_id == "engram_lite":
            return EngramLiteAugmenter(
                base_dir=options.get("base_dir", self.engram_base_dir),
                project_id=options.get("project_id", self.engram_project_id),
                session_id=session_id,
                system_prompt=options.get("system_prompt", ""),
            )

        if augmenter_id == "engram":
            return EngramAugmenter(
                base_dir=options.get("base_dir", self.engram_base_dir),
                project_id=options.get("project_id", self.engram_project_id),
                project_type=options.get("project_type", self.engram_project_type),
                session_id=session_id,
            )

        if augmenter_id == "rag":
            return RagAugmenter(
                config=options.get("config"),
                collection=options.get("collection", "default"),
                system_prompt=options.get("system_prompt", ""),
            )

        raise ValueError(f"Unknown augmenter_id: {augmenter_id}")
