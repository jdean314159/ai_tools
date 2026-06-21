from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Any, Iterable, Mapping

from ..contracts import AgentAction, AgentContext, AgentRun, EngineRoles, ToolResult
from ..llm_engines_adapter import RoleEngineSet, extract_json_object, action_from_payload
from ..memory import create_memory_adapter
from ..planners import SequencePlanner
from ..programming import (
    ContextBudgetConfig,
    FailurePolicy,
    PlanStep,
    ProgrammingContextManager,
    ProgrammingFailureController,
    ProgrammingRoleBindings,
    ProgrammingRuntimeConfig,
    ProgrammingTask,
    ProgrammingTaskStateStore,
    ProgrammingStateTracker,
    ProgrammingToolRuntime,
    WorkspaceAllocation,
    WorkspaceIsolationManager,
    WorkspacePolicy,
    execute_workspace_command,
    build_programming_task,
    load_programming_runtime_config,
    save_programming_runtime_config,
)
from ..runtime import AgentRuntime
from ..tools import LocalTool, LocalToolRuntime


DEFAULT_PROGRAMMING_PLAN = [
    PlanStep(step_id="inspect_file", description="Inspect the target file and confirm the bug."),
    PlanStep(step_id="apply_patch", description="Apply a candidate patch to the target file."),
    PlanStep(step_id="verify_patch", description="Verify the patch locally and escalate if the check fails."),
    PlanStep(step_id="repair_patch", description="Repair the patch after escalation, if needed."),
    PlanStep(step_id="complete_task", description="Summarize the finished task and stop."),
]


@dataclass
class FileWorkspace:
    root: Path

    def read_text(self, path: str) -> str:
        target = self.root / path
        return target.read_text(encoding="utf-8")

    def write_text(self, path: str, content: str) -> str:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"wrote {path}"

    def replace_text(self, path: str, old: str, new: str) -> str:
        current = self.read_text(path)
        if old not in current:
            raise ValueError(f"Text not found in {path}: {old!r}")
        updated = current.replace(old, new)
        self.write_text(path, updated)
        return f"updated {path}"

    def contains_text(self, path: str, needle: str) -> bool:
        return needle in self.read_text(path)


class LLMProgrammingPlanner:
    def __init__(self, engines: RoleEngineSet, *, path: str = "main.py") -> None:
        self.engines = engines
        self.path = path

    def _latest_tool_text(self, context: AgentContext, tool_name: str) -> str:
        for step in reversed(context.steps):
            call = step.action.tool_call
            if call is not None and call.name == tool_name and step.observation is not None:
                return step.observation.text
        return ""

    def _has_tool(self, context: AgentContext, tool_name: str, *, phase: str | None = None) -> bool:
        for step in context.steps:
            call = step.action.tool_call
            if call is None or call.name != tool_name:
                continue
            if phase is not None and str(step.action.meta.get("phase") or "") != phase:
                continue
            return True
        return False

    def _latest_failed_check(self, context: AgentContext) -> bool:
        for step in reversed(context.steps):
            call = step.action.tool_call
            if call is not None and call.name == "run_check" and step.observation and step.observation.tool_result is not None:
                return not bool(step.observation.tool_result.success)
        return False

    def _planner_prompt(self, context: AgentContext) -> str:
        memory = "\n".join(item.text for item in context.recalled) if context.recalled else "(none)"
        file_contents = self._latest_tool_text(context, "read_file") or "(file not read yet)"
        return (
            f"Task: {context.task.goal}\n"
            f"Session: {context.task.session_id}\n"
            f"Path: {context.task.context.get('path', self.path)}\n"
            f"Known memory:\n{memory}\n\n"
            f"Latest file contents:\n{file_contents}\n\n"
            "Return JSON only with one of: "
            "{'kind':'tool','tool_name':'read_file','arguments':{'path':'main.py'},'message':'...'} or "
            "{'kind':'tool','tool_name':'run_check','arguments':{'path':'main.py','must_contain':'return a + b'},'message':'...'} or "
            "{'kind':'final','final_output':'...'}"
        )

    def _patch_prompt(self, context: AgentContext, *, file_contents: str, role: str) -> str:
        return (
            f"You are the {role} model editing a Python file.\n"
            f"Task: {context.task.goal}\n"
            f"Path: {context.task.context.get('path', self.path)}\n"
            f"Current file contents:\n{file_contents}\n\n"
            "Return JSON only with keys 'old', 'new', and optional 'message'."
        )

    def _invoke_json(self, role: str, system_prompt: str, user_prompt: str) -> tuple[dict[str, Any], dict[str, Any]]:
        response = self.engines.invoke(
            role,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=300,
            temperature=0.0,
            metadata={"task": "programming_demo", "role": role},
        )
        payload = extract_json_object(response.message.content or "")
        meta = action_from_payload({"kind": "message", "message": ""}, response=response, engine_role=role).meta
        return payload, meta

    def plan(self, context: AgentContext) -> AgentAction:
        active = context.active_controller
        file_text = self._latest_tool_text(context, "read_file")

        if active == "critic":
            if not self._has_tool(context, "replace_text", phase="critic_repair"):
                payload, meta = self._invoke_json(
                    "critic",
                    "Return only JSON patch instructions for the repaired code.",
                    self._patch_prompt(context, file_contents=file_text or "(file not read yet)", role="critic"),
                )
                return AgentAction.tool(
                    "replace_text",
                    {"path": self.path, "old": str(payload["old"]), "new": str(payload["new"] )},
                    message=str(payload.get("message") or "Apply the mentor repair."),
                    meta={**meta, "phase": "critic_repair", "engine_role": "critic", "plan_step_id": "repair_patch"},
                )
            if not self._has_tool(context, "run_check", phase="critic_verify"):
                return AgentAction.tool(
                    "run_check",
                    {"path": self.path, "must_contain": "return a + b"},
                    message="Verify the repaired patch.",
                    meta={"phase": "critic_verify", "engine_role": "critic", "plan_step_id": "repair_patch"},
                )
            return AgentAction.final(
                "Updated main.py so add(a, b) now returns a + b after escalating to the mentor.",
                meta={"phase": "finish", "engine_role": "critic", "handoff": "planner", "plan_step_id": "complete_task"},
            )

        if not self._has_tool(context, "read_file"):
            payload, meta = self._invoke_json(
                "planner",
                "Return only JSON actions for the programming task.",
                self._planner_prompt(context),
            )
            if str(payload.get("kind") or "").strip().lower() == "final":
                return AgentAction.final(
                    str(payload.get("final_output") or payload.get("message") or "Completed programming task."),
                    meta={**meta, "phase": "finish", "engine_role": "planner", "plan_step_id": "complete_task"},
                )
            return AgentAction.tool(
                str(payload.get("tool_name") or payload.get("name") or "read_file"),
                dict(payload.get("arguments") or {"path": self.path}),
                message=str(payload.get("message") or "Read the file."),
                meta={**meta, "phase": "inspect", "engine_role": "planner", "plan_step_id": "inspect_file"},
            )

        if not self._has_tool(context, "replace_text", phase="edit"):
            payload, meta = self._invoke_json(
                "executor",
                "Return only JSON patch instructions.",
                self._patch_prompt(context, file_contents=file_text or "(file not read yet)", role="executor"),
            )
            return AgentAction.tool(
                "replace_text",
                {"path": self.path, "old": str(payload["old"]), "new": str(payload["new"])},
                message=str(payload.get("message") or "Apply the worker patch."),
                meta={**meta, "phase": "edit", "engine_role": "executor", "plan_step_id": "apply_patch"},
            )

        if not self._has_tool(context, "run_check", phase="verify"):
            payload, meta = self._invoke_json(
                "planner",
                "Return only JSON actions for the programming task.",
                self._planner_prompt(context),
            )
            return AgentAction.tool(
                str(payload.get("tool_name") or "run_check"),
                dict(payload.get("arguments") or {"path": self.path, "must_contain": "return a + b"}),
                message=str(payload.get("message") or "Run the local verification."),
                meta={**meta, "phase": "verify", "engine_role": "planner", "plan_step_id": "verify_patch"},
            )

        return AgentAction.final(
            "Updated main.py so add(a, b) now returns a + b.",
            meta={"phase": "finish", "engine_role": "planner", "plan_step_id": "complete_task"},
        )




def load_role_engines_from_llm_engines_config(
    config: ProgrammingRuntimeConfig,
    *,
    engine_config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load named mentor/worker/critic engines from an llm_engines YAML config."""
    names = {
        str(name).strip()
        for name in [config.role_bindings.planner, config.role_bindings.executor, config.role_bindings.critic]
        if str(name or '').strip()
    }
    if not names:
        return {}
    from llm_engines.factory import EngineFactory

    return {name: EngineFactory.from_engine_name(name, engine_config_path) for name in sorted(names)}


def write_programming_config_file(
    path: str | Path,
    *,
    session_id: str = 'programming_demo',
    task_path: str = 'main.py',
    memory_backend: str = 'engram',
    mentor: str | None = None,
    worker: str | None = None,
    critic: str | None = None,
) -> Path:
    bindings = ProgrammingRoleBindings(planner=mentor, executor=worker, critic=critic)
    config = build_default_programming_config(
        session_id=session_id,
        path=task_path,
        memory_backend=memory_backend,
        role_bindings=bindings,
    )
    return save_programming_runtime_config(config, path)


def run_programming_demo_from_file(
    config_path: str | Path,
    *,
    root: str | Path | None = None,
    engine_config_path: str | Path | None = None,
    engines_by_name: Mapping[str, Any] | None = None,
    memory=None,
    max_steps: int = 12,
) -> tuple[AgentRun, Path]:
    config = load_programming_runtime_config(config_path)
    registry = dict(engines_by_name or {})
    if not registry and engine_config_path is not None:
        registry = load_role_engines_from_llm_engines_config(config, engine_config_path=engine_config_path)
    return run_programming_demo_from_config(
        config,
        root=root,
        engines_by_name=registry,
        memory=memory,
        max_steps=max_steps,
    )


def make_programming_tool_runtime(
    workspace: FileWorkspace,
    workspace_policy: WorkspacePolicy | None = None,
    *,
    owner_id: str = "worker",
    isolation_manager: WorkspaceIsolationManager | None = None,
) -> ProgrammingToolRuntime:
    base_runtime = LocalToolRuntime(
        [
            LocalTool(
                name="read_file",
                description="Read the current contents of a source file.",
                handler=workspace.read_text,
                input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            ),
            LocalTool(
                name="replace_text",
                description="Apply a targeted textual edit to a source file.",
                handler=workspace.replace_text,
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "old": {"type": "string"},
                        "new": {"type": "string"},
                    },
                    "required": ["path", "old", "new"],
                },
            ),
            LocalTool(
                name="run_check",
                description="Verify that a file contains the expected text after an edit.",
                handler=lambda path, must_contain: ToolResult(
                    name="run_check",
                    output=str(workspace.contains_text(path, must_contain)),
                    success=workspace.contains_text(path, must_contain),
                    meta={"path": path, "must_contain": must_contain},
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "must_contain": {"type": "string"},
                    },
                    "required": ["path", "must_contain"],
                },
            ),
            LocalTool(
                name="run_command",
                description="Run an allowed verification or inspection command inside the workspace.",
                handler=lambda command: execute_workspace_command(workspace.root, command),
                input_schema={
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            ),
        ]
    )
    policy = workspace_policy or WorkspacePolicy(root=str(workspace.root), writable_paths=["main.py"], runnable_commands=[], approval_mode="auto")
    return ProgrammingToolRuntime(base_runtime, policy, root=workspace.root, owner_id=owner_id, isolation_manager=isolation_manager)


def _default_programming_actions(path: str = "main.py") -> Iterable[AgentAction]:
    return [
        AgentAction.message_only(
            "Inspect the buggy implementation before editing.",
            meta={"phase": "plan", "engine_role": "planner", "plan_step_id": "inspect_file"},
        ),
        AgentAction.tool(
            "read_file",
            {"path": path},
            message="Read the target file.",
            meta={"phase": "inspect", "engine_role": "executor", "plan_step_id": "inspect_file"},
        ),
        AgentAction.tool(
            "replace_text",
            {"path": path, "old": "return a - b", "new": "return a * b"},
            message="Try a local patch quickly before escalating.",
            meta={"phase": "edit", "engine_role": "executor", "plan_step_id": "apply_patch"},
        ),
        AgentAction.tool(
            "run_check",
            {"path": path, "must_contain": "return a + b"},
            message="Verify the quick local patch.",
            meta={"phase": "verify", "engine_role": "executor", "plan_step_id": "verify_patch"},
        ),
    ]


def _default_critic_actions(path: str = "main.py") -> Iterable[AgentAction]:
    return [
        AgentAction.message_only(
            "Escalating to mentor after the local verification failed.",
            meta={"phase": "escalate", "engine_role": "critic", "plan_step_id": "repair_patch"},
        ),
        AgentAction.tool(
            "replace_text",
            {"path": path, "old": "return a * b", "new": "return a + b"},
            message="Apply the corrected patch from the mentor.",
            meta={"phase": "repair", "engine_role": "critic", "plan_step_id": "repair_patch"},
        ),
        AgentAction.tool(
            "run_check",
            {"path": path, "must_contain": "return a + b"},
            message="Verify the mentor patch.",
            meta={"phase": "critic_verify", "engine_role": "critic", "plan_step_id": "repair_patch"},
        ),
        AgentAction.final(
            "Updated main.py so add(a, b) now returns a + b after escalating to the mentor.",
            meta={"phase": "finish", "engine_role": "critic", "handoff": "planner", "plan_step_id": "complete_task"},
        ),
    ]


def _plan_status_map(state) -> dict[str, str]:
    if state is None:
        return {}
    return {step.step_id: step.status for step in state.plan}


def _build_sequence_actions_for_state(state, *, path: str = "main.py") -> tuple[list[AgentAction], list[AgentAction], str]:
    if state is None:
        return list(_default_programming_actions(path)), list(_default_critic_actions(path)), "planner"

    status = _plan_status_map(state)
    planner_actions: list[AgentAction] = []
    critic_actions: list[AgentAction] = []
    controller = "planner"

    inspect_status = status.get("inspect_file", "pending")
    if inspect_status != "completed":
        planner_actions.append(
            AgentAction.tool(
                "read_file",
                {"path": path},
                message="Resume by reading the target file.",
                meta={"phase": "inspect", "engine_role": "executor", "plan_step_id": "inspect_file", "resumed": True},
            )
        )

    if status.get("apply_patch", "pending") != "completed":
        planner_actions.append(
            AgentAction.tool(
                "replace_text",
                {"path": path, "old": "return a - b", "new": "return a * b"},
                message="Resume the local patch attempt.",
                meta={"phase": "edit", "engine_role": "executor", "plan_step_id": "apply_patch", "resumed": True},
            )
        )

    verify_status = status.get("verify_patch", "pending")
    repair_status = status.get("repair_patch", "pending")
    if state.last_verification is not None and not state.last_verification.success and repair_status != "completed":
        controller = "critic"
    elif verify_status != "completed":
        planner_actions.append(
            AgentAction.tool(
                "run_check",
                {"path": path, "must_contain": "return a + b"},
                message="Resume the local verification.",
                meta={"phase": "verify", "engine_role": "executor", "plan_step_id": "verify_patch", "resumed": True},
            )
        )

    if controller == "critic":
        if repair_status != "completed":
            critic_actions.extend(
                [
                    AgentAction.message_only(
                        "Resuming in mentor mode after a failed verification.",
                        meta={"phase": "resume", "engine_role": "critic", "plan_step_id": "repair_patch", "resumed": True},
                    ),
                    AgentAction.tool(
                        "replace_text",
                        {"path": path, "old": "return a * b", "new": "return a + b"},
                        message="Apply the mentor repair after resume.",
                        meta={"phase": "repair", "engine_role": "critic", "plan_step_id": "repair_patch", "resumed": True},
                    ),
                    AgentAction.tool(
                        "run_check",
                        {"path": path, "must_contain": "return a + b"},
                        message="Verify the mentor repair after resume.",
                        meta={"phase": "critic_verify", "engine_role": "critic", "plan_step_id": "repair_patch", "resumed": True},
                    ),
                ]
            )
        if status.get("complete_task", "pending") != "completed":
            critic_actions.append(
                AgentAction.final(
                    state.final_output or "Updated main.py so add(a, b) now returns a + b after resuming the mentor flow.",
                    meta={"phase": "finish", "engine_role": "critic", "handoff": "planner", "plan_step_id": "complete_task", "resumed": True},
                )
            )
    elif status.get("complete_task", "pending") != "completed" and repair_status == "completed":
        critic_actions.append(
            AgentAction.final(
                state.final_output or "Updated main.py so add(a, b) now returns a + b after resuming.",
                meta={"phase": "finish", "engine_role": "critic", "handoff": "planner", "plan_step_id": "complete_task", "resumed": True},
            )
        )

    if not planner_actions and controller == "planner" and status.get("complete_task", "pending") != "completed":
        planner_actions.append(
            AgentAction.final(
                state.final_output or "Programming task ready to finalize.",
                meta={"phase": "finish", "engine_role": "planner", "plan_step_id": "complete_task", "resumed": True},
            )
        )

    return planner_actions, critic_actions or list(_default_critic_actions(path)), controller




def build_minimum_reliable_programming_config(
    *,
    session_id: str = "programming_demo",
    path: str = "main.py",
    seed_content: str = "def add(a, b):\n    return a - b\n",
    memory_backend: str = "engram",
    role_bindings: ProgrammingRoleBindings | None = None,
) -> ProgrammingRuntimeConfig:
    config = build_default_programming_config(
        session_id=session_id,
        path=path,
        seed_content=seed_content,
        memory_backend=memory_backend,
        role_bindings=role_bindings,
    )
    task = ProgrammingTask(
        task_id=config.task.task_id,
        goal=config.task.goal,
        session_id=config.task.session_id,
        workspace=WorkspacePolicy(
            root=config.task.workspace.root,
            writable_paths=list(config.task.workspace.writable_paths),
            runnable_commands=list(config.task.workspace.runnable_commands),
            approval_mode="auto",
            max_parallel_patch_workers=1,
            isolation_mode="in_place",
            branch_prefix=config.task.workspace.branch_prefix,
            enforce_patch_ownership=config.task.workspace.enforce_patch_ownership,
        ),
        plan=list(config.task.plan),
        verification_commands=list(config.task.verification_commands),
        metadata=dict(config.task.metadata),
    )
    return ProgrammingRuntimeConfig(
        task=task,
        memory_backend=config.memory_backend,
        project_id=config.project_id,
        session_id=config.session_id,
        role_bindings=config.role_bindings,
        context_budget=config.context_budget,
        failure_policy=config.failure_policy,
        memory_subdir=config.memory_subdir,
        state_subdir=config.state_subdir,
        default_target_path=config.default_target_path,
        seed_content=config.seed_content,
    )

def build_default_programming_config(
    *,
    session_id: str = "programming_demo",
    path: str = "main.py",
    seed_content: str = "def add(a, b):\n    return a - b\n",
    memory_backend: str = "engram",
    role_bindings: ProgrammingRoleBindings | None = None,
) -> ProgrammingRuntimeConfig:
    task = build_programming_task(
        task_id="fix_add_function",
        goal="Fix the add(a, b) implementation in main.py so it returns the sum.",
        path=path,
        session_id=session_id,
        plan=list(DEFAULT_PROGRAMMING_PLAN),
        verification_commands=[f"run_check:{path}:return a + b", f"run_command:{sys.executable} -m py_compile {path}"],
    )
    task = ProgrammingTask(
        task_id=task.task_id,
        goal=task.goal,
        session_id=task.session_id,
        workspace=WorkspacePolicy(
            root=".",
            writable_paths=list(task.workspace.writable_paths),
            runnable_commands=[f"{sys.executable} -m py_compile {path}"],
            approval_mode=task.workspace.approval_mode,
            max_parallel_patch_workers=task.workspace.max_parallel_patch_workers,
            isolation_mode=task.workspace.isolation_mode,
            branch_prefix=task.workspace.branch_prefix,
            enforce_patch_ownership=task.workspace.enforce_patch_ownership,
        ),
        plan=list(task.plan),
        verification_commands=list(task.verification_commands),
        metadata=dict(task.metadata),
    )
    return ProgrammingRuntimeConfig(
        task=task,
        memory_backend=memory_backend,
        project_id="agent_programming_demo",
        session_id=session_id,
        role_bindings=role_bindings or ProgrammingRoleBindings(),
        context_budget=ContextBudgetConfig(max_visible_steps=4, max_tool_output_chars=120, summary_max_chars=500),
        failure_policy=FailurePolicy(),
        memory_subdir=".agent_memory",
        state_subdir=".agent_state",
        default_target_path=path,
        seed_content=seed_content,
    )


def resolve_programming_role_engines(
    config: ProgrammingRuntimeConfig,
    *,
    engines_by_name: Mapping[str, Any] | None = None,
    planner_engine=None,
    executor_engine=None,
    critic_engine=None,
) -> tuple[Any | None, Any | None, Any | None]:
    if planner_engine is not None or executor_engine is not None or critic_engine is not None:
        return planner_engine, executor_engine, critic_engine
    registry = dict(engines_by_name or {})
    bindings = config.role_bindings
    planner = registry.get(str(bindings.planner or "").strip()) if bindings.planner else None
    executor = registry.get(str(bindings.executor or "").strip()) if bindings.executor else None
    critic = registry.get(str(bindings.critic or "").strip()) if bindings.critic else None
    return planner, executor, critic


def make_programming_runtime_from_config(
    workspace: FileWorkspace,
    config: ProgrammingRuntimeConfig,
    *,
    memory=None,
    engines_by_name: Mapping[str, Any] | None = None,
    planner_engine=None,
    executor_engine=None,
    critic_engine=None,
) -> AgentRuntime:
    planner_engine, executor_engine, critic_engine = resolve_programming_role_engines(
        config,
        engines_by_name=engines_by_name,
        planner_engine=planner_engine,
        executor_engine=executor_engine,
        critic_engine=critic_engine,
    )
    state_root = workspace.root / config.state_subdir
    state_root.mkdir(parents=True, exist_ok=True)
    worker_owner = str(config.role_bindings.executor or "worker").strip() or "worker"
    isolation_manager = WorkspaceIsolationManager(state_root)
    allocation = isolation_manager.prepare_workspace(workspace.root, worker_owner, config.task.workspace)
    effective_workspace = FileWorkspace(Path(allocation.root))
    adapter = create_memory_adapter(
        config.memory_backend,
        memory=memory,
        base_dir=str(effective_workspace.root / config.memory_subdir),
        project_id=config.project_id,
        session_id=config.session_id,
    )
    base_task = config.task
    programming_task = ProgrammingTask(
        task_id=base_task.task_id,
        goal=base_task.goal,
        session_id=config.session_id or base_task.session_id,
        workspace=WorkspacePolicy(
            root=str(effective_workspace.root),
            writable_paths=list(base_task.workspace.writable_paths or [config.default_target_path]),
            runnable_commands=list(base_task.workspace.runnable_commands),
            approval_mode=base_task.workspace.approval_mode,
            max_parallel_patch_workers=base_task.workspace.max_parallel_patch_workers,
            isolation_mode=base_task.workspace.isolation_mode,
            branch_prefix=base_task.workspace.branch_prefix,
            enforce_patch_ownership=base_task.workspace.enforce_patch_ownership,
        ),
        plan=list(base_task.plan),
        verification_commands=list(base_task.verification_commands),
        metadata={**dict(base_task.metadata), "path": base_task.metadata.get("path", config.default_target_path), "workspace_allocation": {"owner_id": allocation.owner_id, "root": allocation.root, "source": allocation.source, "branch_name": allocation.branch_name, "isolation_mode": allocation.isolation_mode}},
    )
    state_store = ProgrammingTaskStateStore(state_root)
    existing_state = state_store.load(programming_task.task_id)
    failure_policy = config.failure_policy
    state_tracker = ProgrammingStateTracker(state_store, programming_task, failure_policy=failure_policy)
    failure_controller = ProgrammingFailureController(state_tracker, failure_policy=failure_policy)

    if planner_engine is not None:
        engines = RoleEngineSet(
            planner=planner_engine,
            executor=executor_engine or planner_engine,
            critic=critic_engine or planner_engine,
        )
        planner = LLMProgrammingPlanner(engines, path=config.default_target_path)
        critic = planner
        roles = EngineRoles(
            planner=config.role_bindings.planner or "mentor",
            executor=config.role_bindings.executor or "worker",
            critic=config.role_bindings.critic or config.role_bindings.planner or "mentor",
        )
    else:
        planner_actions, critic_actions, resume_controller = _build_sequence_actions_for_state(existing_state, path=config.default_target_path)
        planner = SequencePlanner(planner_actions)
        critic = SequencePlanner(critic_actions)
        roles = EngineRoles(planner="worker", executor="worker", critic="mentor")
        programming_task = ProgrammingTask(
            task_id=programming_task.task_id,
            goal=programming_task.goal,
            session_id=programming_task.session_id,
            workspace=programming_task.workspace,
            plan=programming_task.plan,
            verification_commands=programming_task.verification_commands,
            metadata={**dict(programming_task.metadata), "resume_controller": resume_controller},
        )
    context_manager = ProgrammingContextManager(state_root, config=config.context_budget)
    runtime = AgentRuntime(
        planner=planner,
        critic=critic,
        tool_runtime=make_programming_tool_runtime(effective_workspace, programming_task.workspace, owner_id=worker_owner, isolation_manager=isolation_manager),
        memory=adapter,
        engine_roles=roles,
        lifecycle_hooks=[state_tracker, failure_controller],
        max_repeated_tool_calls=failure_policy.stop_on_repeated_tool_calls + 1,
        context_builder=context_manager,
    )
    setattr(runtime, "programming_config", config)
    setattr(runtime, "programming_task", programming_task)
    setattr(runtime, "programming_state_store", state_store)
    setattr(runtime, "programming_state_tracker", state_tracker)
    setattr(runtime, "programming_context_manager", context_manager)
    setattr(runtime, "programming_workspace_allocation", allocation)
    setattr(runtime, "programming_isolation_manager", isolation_manager)
    setattr(runtime, "programming_workspace", effective_workspace)
    return runtime


def make_programming_demo_runtime(
    workspace: FileWorkspace,
    *,
    memory_backend: str = "engram",
    memory=None,
    memory_base_dir: str | Path | None = None,
    state_base_dir: str | Path | None = None,
    project_id: str = "agent_programming_demo",
    session_id: str = "agent_programming_demo",
    planner_engine=None,
    executor_engine=None,
    critic_engine=None,
    config: ProgrammingRuntimeConfig | None = None,
) -> AgentRuntime:
    config_obj = config or build_default_programming_config(session_id=session_id, memory_backend=memory_backend)
    config_obj = ProgrammingRuntimeConfig(
        task=config_obj.task,
        memory_backend=memory_backend or config_obj.memory_backend,
        project_id=project_id or config_obj.project_id,
        session_id=session_id or config_obj.session_id,
        role_bindings=config_obj.role_bindings,
        context_budget=config_obj.context_budget,
        failure_policy=config_obj.failure_policy,
        memory_subdir=(Path(memory_base_dir).name if memory_base_dir is not None else config_obj.memory_subdir),
        state_subdir=(Path(state_base_dir).name if state_base_dir is not None else config_obj.state_subdir),
        default_target_path=config_obj.default_target_path,
        seed_content=config_obj.seed_content,
    )
    return make_programming_runtime_from_config(
        workspace,
        config_obj,
        memory=memory,
        planner_engine=planner_engine,
        executor_engine=executor_engine,
        critic_engine=critic_engine,
    )


def run_programming_demo_from_config(
    config: ProgrammingRuntimeConfig,
    *,
    root: str | Path | None = None,
    engines_by_name: Mapping[str, Any] | None = None,
    memory=None,
    max_steps: int = 12,
) -> tuple[AgentRun, Path]:
    if root is None:
        tempdir = TemporaryDirectory()
        root_path = Path(tempdir.name)
        keepalive = tempdir
    else:
        root_path = Path(root)
        root_path.mkdir(parents=True, exist_ok=True)
        keepalive = None

    workspace = FileWorkspace(root_path)
    target_path = config.task.metadata.get("path", config.default_target_path)
    if not (root_path / str(target_path)).exists():
        workspace.write_text(str(target_path), config.seed_content)
    runtime = make_programming_runtime_from_config(
        workspace,
        config,
        memory=memory,
        engines_by_name=engines_by_name,
    )
    programming_task = getattr(runtime, "programming_task")
    state_tracker = getattr(runtime, "programming_state_tracker")
    task = programming_task.to_agent_task()
    resume_controller = str(programming_task.metadata.get("resume_controller") or task.context.get("resume_controller") or "").strip()
    if resume_controller:
        task.context["resume_controller"] = resume_controller
    task.context.update(state_tracker.attach_to_context(task.context))
    run = runtime.run(task, max_steps=max_steps)
    setattr(run, "_tempdir", keepalive)
    allocation = getattr(runtime, "programming_workspace_allocation", None)
    if allocation is not None:
        setattr(run, "programming_workspace_root", allocation.root)
    return run, root_path


def run_programming_demo(
    *,
    root: str | Path | None = None,
    memory_backend: str = "engram",
    seed_content: str = "def add(a, b):\n    return a - b\n",
    planner_engine=None,
    executor_engine=None,
    critic_engine=None,
    max_steps: int = 12,
) -> tuple[AgentRun, Path]:
    config = build_default_programming_config(
        session_id="programming_demo",
        memory_backend=memory_backend,
        seed_content=seed_content,
    )
    runtime_kwargs = {
        "planner_engine": planner_engine,
        "executor_engine": executor_engine,
        "critic_engine": critic_engine,
    }
    if any(value is not None for value in runtime_kwargs.values()):
        engines_by_name = None
    else:
        engines_by_name = None
    return run_programming_demo_from_config(
        config,
        root=root,
        memory=None,
        engines_by_name=engines_by_name,
        max_steps=max_steps,
    ) if not any(value is not None for value in runtime_kwargs.values()) else _run_programming_demo_with_direct_engines(
        config,
        root=root,
        max_steps=max_steps,
        **runtime_kwargs,
    )


def _run_programming_demo_with_direct_engines(
    config: ProgrammingRuntimeConfig,
    *,
    root: str | Path | None = None,
    planner_engine=None,
    executor_engine=None,
    critic_engine=None,
    max_steps: int = 12,
) -> tuple[AgentRun, Path]:
    if root is None:
        tempdir = TemporaryDirectory()
        root_path = Path(tempdir.name)
        keepalive = tempdir
    else:
        root_path = Path(root)
        root_path.mkdir(parents=True, exist_ok=True)
        keepalive = None
    workspace = FileWorkspace(root_path)
    target_path = config.task.metadata.get("path", config.default_target_path)
    if not (root_path / str(target_path)).exists():
        workspace.write_text(str(target_path), config.seed_content)
    runtime = make_programming_runtime_from_config(
        workspace,
        config,
        planner_engine=planner_engine,
        executor_engine=executor_engine,
        critic_engine=critic_engine,
    )
    programming_task = getattr(runtime, "programming_task")
    state_tracker = getattr(runtime, "programming_state_tracker")
    task = programming_task.to_agent_task()
    resume_controller = str(programming_task.metadata.get("resume_controller") or task.context.get("resume_controller") or "").strip()
    if resume_controller:
        task.context["resume_controller"] = resume_controller
    task.context.update(state_tracker.attach_to_context(task.context))
    run = runtime.run(task, max_steps=max_steps)
    setattr(run, "_tempdir", keepalive)
    allocation = getattr(runtime, "programming_workspace_allocation", None)
    if allocation is not None:
        setattr(run, "programming_workspace_root", allocation.root)
    return run, root_path


def resume_programming_demo(
    *,
    root: str | Path,
    memory_backend: str = "engram",
    planner_engine=None,
    executor_engine=None,
    critic_engine=None,
    max_steps: int = 12,
) -> tuple[AgentRun, Path]:
    config = build_default_programming_config(
        session_id="programming_demo",
        memory_backend=memory_backend,
    )
    return _run_programming_demo_with_direct_engines(
        config,
        root=root,
        planner_engine=planner_engine,
        executor_engine=executor_engine,
        critic_engine=critic_engine,
        max_steps=max_steps,
    ) if any(value is not None for value in (planner_engine, executor_engine, critic_engine)) else run_programming_demo_from_config(
        config,
        root=root,
        max_steps=max_steps,
    )
