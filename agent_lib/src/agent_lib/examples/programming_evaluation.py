from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable, Mapping, Literal

from ..programming import (
    ProgrammingRuntimeConfig,
    ProgrammingTask,
    ProgrammingTaskStateStore,
    WorkspacePolicy,
    ProgrammingRoleBindings,
)
from .programming_task import (
    build_default_programming_config,
    build_minimum_reliable_programming_config,
    run_programming_demo_from_config,
)


@dataclass(frozen=True)
class ProgrammingBenchmarkCase:
    name: str
    description: str
    config: ProgrammingRuntimeConfig
    max_steps: int = 12
    initial_max_steps: int | None = None
    expect_status: str = "completed"
    expect_file_contains: str | None = "return a + b"
    expect_file_unchanged: bool = False
    expect_patch_status: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProgrammingBenchmarkResult:
    case_name: str
    description: str
    success: bool
    status: str
    stop_reason: str | None
    steps: int
    escalations: int
    retries: int
    patch_status: str | None
    verification_success: bool | None
    verification_count: int
    verification_failures: int
    patch_attempts: int
    elapsed_seconds: float | None
    touched_files: list[str]
    workspace_root: str
    state_path: str
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProgrammingBenchmarkReport:
    results: list[ProgrammingBenchmarkResult]

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for item in self.results if item.success)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def average_steps(self) -> float:
        return mean(item.steps for item in self.results) if self.results else 0.0

    @property
    def average_retries(self) -> float:
        return mean(item.retries for item in self.results) if self.results else 0.0

    @property
    def average_escalations(self) -> float:
        return mean(item.escalations for item in self.results) if self.results else 0.0

    @property
    def average_elapsed_seconds(self) -> float:
        values = [item.elapsed_seconds for item in self.results if item.elapsed_seconds is not None]
        return mean(values) if values else 0.0

    @property
    def total_verifications(self) -> int:
        return sum(item.verification_count for item in self.results)

    @property
    def total_verification_failures(self) -> int:
        return sum(item.verification_failures for item in self.results)

    @property
    def patch_status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.results:
            key = item.patch_status or "none"
            counts[key] = counts.get(key, 0) + 1
        return counts

    def comparison_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "case_name": item.case_name,
                "success": item.success,
                "steps": item.steps,
                "retries": item.retries,
                "escalations": item.escalations,
                "verification_outcome": f"{item.verification_count - item.verification_failures}/{item.verification_count}",
                "patch_status": item.patch_status or "none",
                "elapsed_seconds": round(item.elapsed_seconds or 0.0, 3),
            }
            for item in self.results
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "summary": {
                "average_steps": round(self.average_steps, 3),
                "average_retries": round(self.average_retries, 3),
                "average_escalations": round(self.average_escalations, 3),
                "average_elapsed_seconds": round(self.average_elapsed_seconds, 3),
                "total_verifications": self.total_verifications,
                "total_verification_failures": self.total_verification_failures,
                "patch_status_counts": dict(self.patch_status_counts),
            },
            "comparison": self.comparison_rows(),
            "results": [
                {
                    "case_name": item.case_name,
                    "description": item.description,
                    "success": item.success,
                    "status": item.status,
                    "stop_reason": item.stop_reason,
                    "steps": item.steps,
                    "escalations": item.escalations,
                    "retries": item.retries,
                    "patch_status": item.patch_status,
                    "verification_success": item.verification_success,
                    "verification_count": item.verification_count,
                    "verification_failures": item.verification_failures,
                    "patch_attempts": item.patch_attempts,
                    "elapsed_seconds": item.elapsed_seconds,
                    "touched_files": list(item.touched_files),
                    "workspace_root": item.workspace_root,
                    "state_path": item.state_path,
                    "notes": list(item.notes),
                }
                for item in self.results
            ],
        }


@dataclass(frozen=True)
class ProgrammingBenchmarkScenario:
    name: str
    description: str
    memory_backend: str = "engram"
    runtime_profile: Literal["minimum_reliable", "isolated_workspace"] = "minimum_reliable"
    role_bindings: ProgrammingRoleBindings = field(default_factory=ProgrammingRoleBindings)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProgrammingScenarioBenchmarkResult:
    scenario: ProgrammingBenchmarkScenario
    report: ProgrammingBenchmarkReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.scenario.name,
            "description": self.scenario.description,
            "memory_backend": self.scenario.memory_backend,
            "runtime_profile": self.scenario.runtime_profile,
            "role_bindings": self.scenario.role_bindings.to_dict(),
            "notes": list(self.scenario.notes),
            "summary": self.report.to_dict()["summary"],
            "comparison": self.report.comparison_rows(),
        }


@dataclass(frozen=True)
class ProgrammingScenarioComparisonReport:
    scenarios: list[ProgrammingScenarioBenchmarkResult]

    @property
    def total_scenarios(self) -> int:
        return len(self.scenarios)

    @property
    def scenario_names(self) -> list[str]:
        return [item.scenario.name for item in self.scenarios]

    def case_matrix(self) -> list[dict[str, Any]]:
        case_names: list[str] = []
        for scenario in self.scenarios:
            for result in scenario.report.results:
                if result.case_name not in case_names:
                    case_names.append(result.case_name)
        rows: list[dict[str, Any]] = []
        for case_name in case_names:
            by_scenario: dict[str, Any] = {}
            for scenario in self.scenarios:
                match = next(
                    (item for item in scenario.report.results if item.case_name == case_name), None
                )
                if match is None:
                    continue
                by_scenario[scenario.scenario.name] = {
                    "success": match.success,
                    "steps": match.steps,
                    "retries": match.retries,
                    "escalations": match.escalations,
                    "patch_status": match.patch_status or "none",
                    "verification_outcome": f"{match.verification_count - match.verification_failures}/{match.verification_count}",
                    "elapsed_seconds": round(match.elapsed_seconds or 0.0, 3),
                }
            rows.append({"case_name": case_name, "scenarios": by_scenario})
        return rows

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_scenarios": self.total_scenarios,
            "scenario_names": self.scenario_names,
            "scenarios": [item.to_dict() for item in self.scenarios],
            "case_matrix": self.case_matrix(),
        }


def _copy_runtime_config(
    config: ProgrammingRuntimeConfig,
    *,
    task: ProgrammingTask | None = None,
    memory_backend: str | None = None,
    session_id: str | None = None,
    state_subdir: str | None = None,
    memory_subdir: str | None = None,
    role_bindings: ProgrammingRoleBindings | None = None,
) -> ProgrammingRuntimeConfig:
    return ProgrammingRuntimeConfig(
        task=task or config.task,
        memory_backend=memory_backend or config.memory_backend,
        project_id=config.project_id,
        session_id=session_id or config.session_id,
        role_bindings=role_bindings or config.role_bindings,
        context_budget=config.context_budget,
        failure_policy=config.failure_policy,
        memory_subdir=memory_subdir or config.memory_subdir,
        state_subdir=state_subdir or config.state_subdir,
        default_target_path=config.default_target_path,
        seed_content=config.seed_content,
    )


def _replace_case_task(
    config: ProgrammingRuntimeConfig, **task_overrides: Any
) -> ProgrammingRuntimeConfig:
    task = config.task
    new_task = ProgrammingTask(
        task_id=task_overrides.get("task_id", task.task_id),
        goal=task_overrides.get("goal", task.goal),
        session_id=task_overrides.get("session_id", task.session_id),
        workspace=task_overrides.get("workspace", task.workspace),
        plan=task_overrides.get("plan", list(task.plan)),
        verification_commands=task_overrides.get(
            "verification_commands", list(task.verification_commands)
        ),
        metadata=task_overrides.get("metadata", dict(task.metadata)),
    )
    return _copy_runtime_config(config, task=new_task)


def build_representative_programming_cases(
    *, memory_backend: str = "engram"
) -> list[ProgrammingBenchmarkCase]:
    cases: list[ProgrammingBenchmarkCase] = []

    minimal = build_minimum_reliable_programming_config(
        session_id="eval_minimal", memory_backend=memory_backend
    )
    cases.append(
        ProgrammingBenchmarkCase(
            name="minimal_reliable_auto_fix",
            description="Minimum reliable path should repair a small single-file bug and verify it.",
            config=minimal,
        )
    )

    proposal = build_minimum_reliable_programming_config(
        session_id="eval_proposal", memory_backend=memory_backend
    )
    proposal_ws = WorkspacePolicy(
        root=proposal.task.workspace.root,
        writable_paths=list(proposal.task.workspace.writable_paths),
        runnable_commands=list(proposal.task.workspace.runnable_commands),
        approval_mode="proposal_only",
        max_parallel_patch_workers=proposal.task.workspace.max_parallel_patch_workers,
        isolation_mode=proposal.task.workspace.isolation_mode,
        branch_prefix=proposal.task.workspace.branch_prefix,
        enforce_patch_ownership=proposal.task.workspace.enforce_patch_ownership,
    )
    proposal = _replace_case_task(proposal, workspace=proposal_ws)
    cases.append(
        ProgrammingBenchmarkCase(
            name="proposal_only_review_gate",
            description="Proposal-only mode should avoid mutating the file while still producing a patch proposal.",
            config=proposal,
            expect_file_contains=None,
            expect_file_unchanged=True,
            expect_patch_status="proposed",
        )
    )

    nested = build_minimum_reliable_programming_config(
        session_id="eval_nested",
        path="src/math_ops.py",
        seed_content="def add(a, b):\n    return a - b\n",
        memory_backend=memory_backend,
    )
    nested = _replace_case_task(
        nested,
        task_id="fix_nested_add_function",
        goal="Fix src/math_ops.py so add(a, b) returns the sum and compiles.",
        metadata={**dict(nested.task.metadata), "path": "src/math_ops.py"},
    )
    cases.append(
        ProgrammingBenchmarkCase(
            name="nested_path_with_compile_check",
            description="Nested-path task should repair the file and pass both content and compile verification.",
            config=nested,
        )
    )

    resume = build_minimum_reliable_programming_config(
        session_id="eval_resume", memory_backend=memory_backend
    )
    cases.append(
        ProgrammingBenchmarkCase(
            name="resume_after_partial_run",
            description="Task should resume from persisted state after a short interrupted run.",
            config=resume,
            initial_max_steps=2,
        )
    )

    isolated = build_default_programming_config(
        session_id="eval_isolated", memory_backend=memory_backend
    )
    isolated_task = ProgrammingTask(
        task_id=isolated.task.task_id,
        goal=isolated.task.goal,
        session_id=isolated.task.session_id,
        workspace=WorkspacePolicy(
            root=isolated.task.workspace.root,
            writable_paths=list(isolated.task.workspace.writable_paths),
            runnable_commands=list(isolated.task.workspace.runnable_commands),
            approval_mode=isolated.task.workspace.approval_mode,
            max_parallel_patch_workers=isolated.task.workspace.max_parallel_patch_workers,
            isolation_mode="worktree",
            branch_prefix=isolated.task.workspace.branch_prefix,
            enforce_patch_ownership=isolated.task.workspace.enforce_patch_ownership,
        ),
        plan=list(isolated.task.plan),
        verification_commands=list(isolated.task.verification_commands),
        metadata=dict(isolated.task.metadata),
    )
    isolated = _copy_runtime_config(isolated, task=isolated_task)
    cases.append(
        ProgrammingBenchmarkCase(
            name="isolated_workspace_fix",
            description="Task should repair the file while running in an isolated workspace.",
            config=isolated,
        )
    )
    return cases


def build_default_benchmark_scenarios() -> list[ProgrammingBenchmarkScenario]:
    return [
        ProgrammingBenchmarkScenario(
            name="engram_minimum_reliable",
            description="Baseline minimum reliable programming path using Engram memory.",
            memory_backend="engram",
            runtime_profile="minimum_reliable",
        ),
        ProgrammingBenchmarkScenario(
            name="engram_isolated_workspace",
            description="Engram baseline with isolated workspace policy applied broadly.",
            memory_backend="engram",
            runtime_profile="isolated_workspace",
        ),
    ]


def _apply_scenario_to_case(
    case: ProgrammingBenchmarkCase, scenario: ProgrammingBenchmarkScenario
) -> ProgrammingBenchmarkCase:
    cfg = _copy_runtime_config(
        case.config,
        memory_backend=scenario.memory_backend,
        session_id=f"{case.config.session_id}_{scenario.name}",
        state_subdir=f"{case.config.state_subdir}_{scenario.name}",
        memory_subdir=f"{case.config.memory_subdir}_{scenario.name}",
        role_bindings=scenario.role_bindings
        if scenario.role_bindings != ProgrammingRoleBindings()
        else case.config.role_bindings,
    )
    if scenario.runtime_profile == "isolated_workspace":
        ws = cfg.task.workspace
        cfg = _replace_case_task(
            cfg,
            workspace=WorkspacePolicy(
                root=ws.root,
                writable_paths=list(ws.writable_paths),
                runnable_commands=list(ws.runnable_commands),
                approval_mode=ws.approval_mode,
                max_parallel_patch_workers=ws.max_parallel_patch_workers,
                isolation_mode="worktree",
                branch_prefix=ws.branch_prefix,
                enforce_patch_ownership=ws.enforce_patch_ownership,
            ),
        )
    return ProgrammingBenchmarkCase(
        name=case.name,
        description=case.description,
        config=cfg,
        max_steps=case.max_steps,
        initial_max_steps=case.initial_max_steps,
        expect_status=case.expect_status,
        expect_file_contains=case.expect_file_contains,
        expect_file_unchanged=case.expect_file_unchanged,
        expect_patch_status=case.expect_patch_status,
        notes=list(case.notes) + [f"scenario={scenario.name}"],
    )


def _summarize_case(
    case: ProgrammingBenchmarkCase, *, run: Any, root: Path
) -> ProgrammingBenchmarkResult:
    state_store = ProgrammingTaskStateStore(root / case.config.state_subdir)
    state = state_store.load(case.config.task.task_id)
    retries = sum((state.retry_counts.values() if state is not None else []), 0)
    patch_status = (
        state.last_patch.status if state is not None and state.last_patch is not None else None
    )
    verification_success = (
        state.last_verification.success
        if state is not None and state.last_verification is not None
        else None
    )
    touched_files = list(state.touched_files) if state is not None else []
    verification_steps = [
        step
        for step in run.steps
        if step.observation is not None
        and step.observation.tool_result is not None
        and step.observation.tool_result.name in {"run_check", "run_command"}
    ]
    verification_count = len(verification_steps)
    verification_failures = sum(
        1 for step in verification_steps if not step.observation.tool_result.success
    )
    patch_attempts = sum(
        1
        for step in run.steps
        if step.action.tool_call is not None and step.action.tool_call.name == "replace_text"
    )
    notes = list(case.notes)
    success = True

    if run.status != case.expect_status:
        success = False
        notes.append(f"expected status {case.expect_status!r}, got {run.status!r}")

    target = str(case.config.task.metadata.get("path", case.config.default_target_path))
    effective_root = Path(str(getattr(run, "programming_workspace_root", root)))
    target_path = effective_root / target
    if case.expect_file_contains is not None:
        if not target_path.exists() or case.expect_file_contains not in target_path.read_text(
            encoding="utf-8"
        ):
            success = False
            notes.append(f"expected file {target!r} to contain {case.expect_file_contains!r}")
    if case.expect_file_unchanged:
        if (
            not target_path.exists()
            or target_path.read_text(encoding="utf-8") != case.config.seed_content
        ):
            success = False
            notes.append(f"expected file {target!r} to remain unchanged in proposal-only flow")
    if case.expect_patch_status is not None and patch_status != case.expect_patch_status:
        success = False
        notes.append(f"expected patch status {case.expect_patch_status!r}, got {patch_status!r}")

    state_path = str(
        (root / case.config.state_subdir / f"{case.config.task.task_id}.json").resolve()
    )
    return ProgrammingBenchmarkResult(
        case_name=case.name,
        description=case.description,
        success=success,
        status=run.status,
        stop_reason=run.stop_reason,
        steps=len(run.steps),
        escalations=run.escalations,
        retries=retries,
        patch_status=patch_status,
        verification_success=verification_success,
        verification_count=verification_count,
        verification_failures=verification_failures,
        patch_attempts=patch_attempts,
        elapsed_seconds=getattr(run, "elapsed_seconds", None),
        touched_files=touched_files,
        workspace_root=str(effective_root.resolve()),
        state_path=state_path,
        notes=notes,
    )


def run_programming_benchmark(
    cases: Iterable[ProgrammingBenchmarkCase] | None = None,
    *,
    root: str | Path | None = None,
    engines_by_name: Mapping[str, Any] | None = None,
) -> ProgrammingBenchmarkReport:
    case_list = list(cases or build_representative_programming_cases())
    keepalive = None
    if root is None:
        keepalive = TemporaryDirectory()
        root_path = Path(keepalive.name)
    else:
        root_path = Path(root)
        root_path.mkdir(parents=True, exist_ok=True)

    try:
        results: list[ProgrammingBenchmarkResult] = []
        for case in case_list:
            case_root = root_path / case.name
            case_root.mkdir(parents=True, exist_ok=True)
            if case.initial_max_steps is not None:
                run_programming_demo_from_config(
                    case.config,
                    root=case_root,
                    engines_by_name=engines_by_name,
                    max_steps=case.initial_max_steps,
                )
            run, actual_root = run_programming_demo_from_config(
                case.config,
                root=case_root,
                engines_by_name=engines_by_name,
                max_steps=case.max_steps,
            )
            results.append(_summarize_case(case, run=run, root=Path(actual_root)))
        return ProgrammingBenchmarkReport(results=results)
    finally:
        if keepalive is not None:
            keepalive.cleanup()


def run_programming_scenario_benchmark(
    scenarios: Iterable[ProgrammingBenchmarkScenario] | None = None,
    *,
    root: str | Path | None = None,
    engines_by_name: Mapping[str, Any] | None = None,
) -> ProgrammingScenarioComparisonReport:
    scenario_list = list(scenarios or build_default_benchmark_scenarios())
    keepalive = None
    if root is None:
        keepalive = TemporaryDirectory()
        root_path = Path(keepalive.name)
    else:
        root_path = Path(root)
        root_path.mkdir(parents=True, exist_ok=True)
    try:
        scenario_reports: list[ProgrammingScenarioBenchmarkResult] = []
        for scenario in scenario_list:
            base_cases = build_representative_programming_cases(
                memory_backend=scenario.memory_backend
            )
            scenario_cases = [_apply_scenario_to_case(case, scenario) for case in base_cases]
            report = run_programming_benchmark(
                scenario_cases, root=root_path / scenario.name, engines_by_name=engines_by_name
            )
            scenario_reports.append(
                ProgrammingScenarioBenchmarkResult(scenario=scenario, report=report)
            )
        return ProgrammingScenarioComparisonReport(scenarios=scenario_reports)
    finally:
        if keepalive is not None:
            keepalive.cleanup()
