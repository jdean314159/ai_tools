from __future__ import annotations

from dataclasses import dataclass

from llm_inspector_ui.services.orchestrator import RunPlan, WorkbenchOrchestrator
from llm_inspector_ui.state.session_store import SessionStore


@dataclass
class FakeAugmentResult:
    prompt: str
    trace: dict
    prompt_tokens: int = 0
    memory_tokens: int = 0
    compressed: bool = False


class FakeAugmenter:
    def __init__(self, augmenter_id: str):
        self.augmenter_id = augmenter_id
        self.seen_turns = []

    def new_session(self, session_id: str) -> None:
        self.seen_turns = []

    def add_turn(self, role: str, text: str, session_id: str) -> None:
        self.seen_turns.append((role, text))

    def augment(self, request):
        prompt = f"prompt:{self.augmenter_id}:{request.user_text}"
        return FakeAugmentResult(
            prompt=prompt,
            trace={
                "sections": [
                    {"title": "User", "origin": "user", "text": request.user_text},
                    {"title": "Final prompt", "origin": "prompt", "text": prompt},
                ],
                "evidence": [],
                "token_accounting": {
                    "target_tokens": request.max_prompt_tokens,
                    "total_tokens": len(prompt.split()),
                    "per_origin_budget": {},
                    "per_origin_used": {"user": len(request.user_text.split())},
                    "truncated": False,
                    "compressed": False,
                    "notes": [],
                },
                "flags": {"augmenter_id": self.augmenter_id},
                "final_prompt": prompt,
            },
            prompt_tokens=len(prompt.split()),
        )


class FakeAugmenterService:
    def __init__(self):
        self.instances = {}

    def get_augmenter_readiness(self, augmenter_id: str, *, options=None):
        class Readiness:
            def __init__(self, augmenter_id):
                self.augmenter_id = augmenter_id
                self.can_run = augmenter_id != "broken"
                self.severity = "ok" if self.can_run else "error"
                self.message = "ready" if self.can_run else "augmenter unavailable"
                self.details = {}
        return Readiness(augmenter_id)

    def create(self, augmenter_id: str, *, session_id: str, options=None):
        inst = FakeAugmenter(augmenter_id)
        self.instances[augmenter_id] = inst
        return inst


class FakeEngine:
    def invoke(self, *, prompt: str, model_id=None, settings=None, session_id=None):
        return {
            "text": f"response:{prompt}",
            "metrics": {"model_id": model_id, "session_id": session_id},
        }


class FakeEngineService:
    def create_engine(self, engine_id: str, config=None):
        return FakeEngine()


class FakeInspectorService:
    def inspect(self, *, augmenter_id: str, augment_result, user_text: str, session_id: str):
        return augment_result.trace


def test_orchestrator_chat_mode_replays_only_prior_turns(tmp_path):
    store = SessionStore(tmp_path / "workbench.sqlite")
    session = store.create_session("Chat")

    store.add_turn(session.session_id, "user", "old user")
    store.add_turn(session.session_id, "assistant", "old assistant")

    augmenter_service = FakeAugmenterService()
    orchestrator = WorkbenchOrchestrator(
        session_store=store,
        engine_service=FakeEngineService(),
        augmenter_service=augmenter_service,
        inspector_service=FakeInspectorService(),
    )

    artifacts = orchestrator.run(
        RunPlan(
            session_id=session.session_id,
            user_text="new user",
            engine_id="echo",
            model_id="echo",
            augmenter_ids=["baseline"],
            augmenter_options={"baseline": {"system_prompt": "Test"}},
        )
    )

    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact.error is None
    assert artifact.status == "ok"
    assert artifact.mode == "chat"
    assert artifact.response_text.startswith("response:prompt:baseline:new user")
    assert artifact.settings["selected_augmenter_ids"] == ["baseline"]
    assert artifact.settings["augmenter_options_all"]["baseline"]["system_prompt"] == "Test"

    seen_turns = augmenter_service.instances["baseline"].seen_turns
    assert seen_turns == [("user", "old user"), ("assistant", "old assistant")]

    turns = store.list_turns(session.session_id)
    assert [t.role for t in turns] == ["user", "assistant", "user", "assistant"]


def test_orchestrator_compare_mode_does_not_pollute_transcript(tmp_path):
    store = SessionStore(tmp_path / "workbench.sqlite")
    session = store.create_session("Compare")

    augmenter_service = FakeAugmenterService()
    orchestrator = WorkbenchOrchestrator(
        session_store=store,
        engine_service=FakeEngineService(),
        augmenter_service=augmenter_service,
        inspector_service=FakeInspectorService(),
    )

    artifacts = orchestrator.run(
        RunPlan(
            session_id=session.session_id,
            user_text="test compare",
            engine_id="echo",
            model_id="echo",
            augmenter_ids=["baseline", "engram"],
        )
    )

    assert len(artifacts) == 2
    assert {a.augmenter_id for a in artifacts} == {"baseline", "engram"}
    assert all(a.mode == "compare" for a in artifacts)
    assert all(a.assistant_turn_id is None for a in artifacts)
    assert all(a.status == "ok" for a in artifacts)
    assert all(a.settings["selected_augmenter_ids"] == ["baseline", "engram"] for a in artifacts)

    turns = store.list_turns(session.session_id)
    assert [t.role for t in turns] == ["user"]


def test_orchestrator_skips_unready_compare_branch(tmp_path):
    store = SessionStore(tmp_path / "workbench.sqlite")
    session = store.create_session("Compare Skip")

    augmenter_service = FakeAugmenterService()
    orchestrator = WorkbenchOrchestrator(
        session_store=store,
        engine_service=FakeEngineService(),
        augmenter_service=augmenter_service,
        inspector_service=FakeInspectorService(),
    )

    artifacts = orchestrator.run(
        RunPlan(
            session_id=session.session_id,
            user_text="test compare",
            engine_id="echo",
            model_id="echo",
            augmenter_ids=["baseline", "broken"],
        )
    )

    assert len(artifacts) == 2

    by_id = {artifact.augmenter_id: artifact for artifact in artifacts}
    assert by_id["baseline"].status == "ok"
    assert by_id["broken"].status == "skipped"
    assert "augmenter unavailable" in (by_id["broken"].error or "")

    turns = store.list_turns(session.session_id)
    assert [t.role for t in turns] == ["user"]


def test_orchestrator_records_errors(tmp_path):
    class BrokenAugmenterService:
        def get_augmenter_readiness(self, augmenter_id: str, *, options=None):
            class Readiness:
                def __init__(self, augmenter_id: str):
                    self.augmenter_id = augmenter_id
                    self.can_run = True
                    self.severity = "ok"
                    self.message = "ready"
                    self.details = {}
            return Readiness(augmenter_id)

        def create(self, augmenter_id: str, *, session_id: str, options=None):
            raise RuntimeError("augmenter failed")

    store = SessionStore(tmp_path / "workbench.sqlite")
    session = store.create_session("Errors")

    orchestrator = WorkbenchOrchestrator(
        session_store=store,
        engine_service=FakeEngineService(),
        augmenter_service=BrokenAugmenterService(),
        inspector_service=FakeInspectorService(),
    )

    artifacts = orchestrator.run(
        RunPlan(
            session_id=session.session_id,
            user_text="hello",
            engine_id="echo",
            model_id="echo",
            augmenter_ids=["baseline"],
        )
    )

    assert len(artifacts) == 1
    assert artifacts[0].status == "error"
    assert artifacts[0].error is not None
    assert "augmenter failed" in artifacts[0].error