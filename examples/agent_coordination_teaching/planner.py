from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class Assignment:
    """Concrete assignment a planner hands to a worker."""
    worker: str
    title: str
    instructions: str
    files: tuple[str, ...] = ()


class _AssignmentModel(BaseModel):
    """Pydantic schema used to parse planner output via StructuredOutputHandler."""
    worker: str = ""
    title: str = "Worker assignment"
    instructions: str = ""
    files: list[str] = Field(default_factory=list)


class _PlanModel(BaseModel):
    """Top-level structured output: a list of assignments."""
    assignments: list[_AssignmentModel] = Field(default_factory=list)


class Planner:
    """
    Generates per-worker assignments for the coordination demo.

    The "mock"/"stub" backend produces deterministic assignments for offline
    runs; any other backend goes through ``llm_engines.get_engine`` and parses
    structured output via ``llm_engines.StructuredOutputHandler`` — no
    hand-rolled JSON regex parsing.
    """

    def __init__(self, *, backend: str = "mock", model: str = "mock-planner") -> None:
        self.backend = backend
        self.model = model

    def plan(self, *, task: str, workers: list[str]) -> list[Assignment]:
        if self.backend in {"mock", "stub"}:
            return [self._stub_assignment(worker, task) for worker in workers]

        from llm_engines import ChatMessage, GenerationRequest, StructuredOutputHandler, get_engine

        engine = get_engine(self.backend, self.model)
        instruction = (
            "Create one small assignment per worker for a coordination teaching demo.\n"
            f"Workers (use these exact names): {workers}\n"
            f"Task: {task}\n"
            "For each worker, write a short title, instructions that stay inside the "
            "provided workspace, and a list of files the worker would touch."
        )
        schema_prompt = StructuredOutputHandler.create_schema_prompt(_PlanModel)
        response = engine.generate(
            GenerationRequest(
                messages=[ChatMessage(role="user", content=f"{instruction}\n\n{schema_prompt}")],
                temperature=0.2,
            )
        )
        result = StructuredOutputHandler.parse_with_details(response.text, _PlanModel)
        if not result.success or result.data is None:
            return [self._fallback(workers, task)]

        assignments: list[Assignment] = []
        for item in result.data.assignments:
            if item.worker in workers:
                assignments.append(
                    Assignment(
                        worker=item.worker,
                        title=item.title or "Worker assignment",
                        instructions=item.instructions or task,
                        files=tuple(item.files),
                    )
                )
        return assignments or [self._fallback(workers, task)]

    @staticmethod
    def _stub_assignment(worker: str, task: str) -> Assignment:
        return Assignment(
            worker=worker,
            title=f"Handle teaching-demo task as {worker}",
            instructions=(
                "Acknowledge the assignment, stay inside the provided workspace, "
                "and summarize what you would change. Keep the work small and inspectable.\n\n"
                f"Task: {task}"
            ),
            files=(f"{worker}.md",),
        )

    @staticmethod
    def _fallback(workers: list[str], task: str) -> Assignment:
        return Assignment(
            worker=workers[0],
            title="Fallback assignment",
            instructions=task,
            files=("README.md",),
        )
