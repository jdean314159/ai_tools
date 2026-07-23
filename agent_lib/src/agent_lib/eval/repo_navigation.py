from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from fnmatch import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Sequence
import urllib.error
import urllib.request

from llm_engines.contracts import (
    BackendUnavailableError,
    ChatMessage,
    ChatModel,
    EngineCapabilities,
    GenerationError,
    GenerationRequest,
    GenerationResponse,
    UsageStats,
)

from ..contracts import (
    AgentAction,
    AgentContext,
    AgentContextBuilder,
    AgentRun,
    AgentRunLifecycleHook,
    AgentStep,
    AgentTask,
    EngineRoles,
    ToolCall,
    ToolResult,
    ToolSpec,
)
from ..llm_engines_adapter import action_from_payload, extract_json_object
from ..memory import NullMemoryAdapter
from ..runtime import AgentRuntime
from ..tools import LocalTool, LocalToolRuntime
from ..control import ActionTrajectoryGuardHook
from .navigation_claims import NavigationClaim, validate_navigation_claims


LEAD_QUESTION = (
    "Within production Python under rag_lib/src, identify (1) where the persistent Chroma client "
    "and collections are initialized, (2) every direct Chroma collection mutation call, such as "
    "upsert or delete, and (3) each RAGPipeline call site that invokes those storage mutations. "
    "Exclude tests, documentation, abstract interfaces, retrieval-only operations, and references "
    "that merely mention Chroma."
)

SYSTEM_PROMPT = """You are a read-only repository navigation agent. Use evidence from tools only.
Return exactly one JSON object and no surrounding text.

Available actions:
1. {"kind":"tool","tool_name":"list_files","arguments":{"path":".","glob":"*.py","max_results":200},"message":"..."}
2. {"kind":"tool","tool_name":"grep","arguments":{"pattern":"...","path":".","glob":"*.py","max_matches":50},"message":"..."}
3. {"kind":"tool","tool_name":"read_file","arguments":{"path":"...","start_line":1,"line_count":200,"full":false},"message":"..."}
4. {"kind":"final","final_output":"Evidence-grounded answer with file paths, symbols, and classifications."}

Never request a write or execute operation. Do not guess locations. Search narrowly, inspect enough
context to classify each result, and finish when the requested set is complete. In the final answer,
list only qualifying locations; do not name excluded candidate paths. For every location, state the
symbol or operation and its requested classification.

Tool rules:
- `glob` is a filename pattern such as `*.py`; put directories in `path`, never in `glob`.
- For a slice, use `full=false` with `start_line` and `line_count`.
- For a whole file, use `full=true` and omit `start_line` and `line_count`; a whole-file read is
  refused if it exceeds the visible result cap.
- Every action must use `kind="tool"` or `kind="final"`; a tool name never belongs in `kind`."""

FINALIZATION_SYSTEM_PROMPT = """You are finalizing a read-only repository navigation task.
Use only the evidence already present in the supplied history. No tools are available and you must
not request another search or file read. Return exactly one JSON object with this shape and no
surrounding text: {"kind":"final","final_output":"Evidence-grounded answer."}

The final answer must identify qualifying file paths, symbols or operations, and their requested
classification. Do not invent evidence and do not mention excluded candidates."""

NAVIGATION_ACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "kind": {"type": "string", "enum": ["tool", "final"]},
        "tool_name": {"type": "string", "enum": ["read_file", "grep", "list_files"]},
        "arguments": {"type": "object"},
        "message": {"type": "string"},
        "final_output": {"type": "string"},
    },
    "required": ["kind"],
}

FINALIZATION_ACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "kind": {"type": "string", "enum": ["final"]},
        "final_output": {"type": "string", "minLength": 1},
    },
    "required": ["kind", "final_output"],
}

NAVIGATION_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "read_file": {
        "type": "object",
        "additionalProperties": False,
        "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"}, "line_count": {"type": "integer"}, "full": {"type": "boolean"}},
        "required": ["path"],
    },
    "grep": {
        "type": "object",
        "additionalProperties": False,
        "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}, "glob": {"type": "string"}, "max_matches": {"type": "integer"}, "case_sensitive": {"type": "boolean"}},
        "required": ["pattern"],
    },
    "list_files": {
        "type": "object",
        "additionalProperties": False,
        "properties": {"path": {"type": "string"}, "glob": {"type": "string"}, "max_results": {"type": "integer"}},
    },
}


class NavigationConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class NavigationPolicy:
    root: Path
    denied_directory_names: frozenset[str] = frozenset(
        {".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules", "build", "dist"}
    )
    denied_path_globs: tuple[str, ...] = (
        "tests/**/runs",
        "tests/**/runs/**",
        "examples/asc_probe/runs",
        "examples/asc_probe/runs/**",
    )
    denied_suffixes: frozenset[str] = frozenset(
        {".db", ".sqlite", ".sqlite3", ".bin", ".jsonl", ".pem", ".key", ".p12", ".pfx", ".pyc", ".so", ".dylib", ".dll"}
    )
    source_suffixes: frozenset[str] = frozenset(
        {".py", ".pyi", ".md", ".rst", ".toml", ".yaml", ".yml", ".json", ".txt", ".ini", ".cfg", ".sh", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".sql"}
    )
    max_file_bytes: int = 256_000
    max_json_bytes: int = 64_000
    default_line_count: int = 200
    max_line_count: int = 1_000
    default_max_matches: int = 50
    max_matches: int = 200
    default_max_results: int = 200
    max_results: int = 2_000
    max_result_chars: int = 8_000
    minimum_printable_ratio: float = 0.85

    def __post_init__(self) -> None:
        root = Path(self.root).resolve(strict=True)
        if not root.is_dir():
            raise NavigationConfigurationError(f"Navigation root is not a directory: {root}")
        positive_limits = (
            self.max_file_bytes,
            self.max_json_bytes,
            self.default_line_count,
            self.max_line_count,
            self.default_max_matches,
            self.max_matches,
            self.default_max_results,
            self.max_results,
            self.max_result_chars,
        )
        if any(limit < 1 for limit in positive_limits):
            raise NavigationConfigurationError("Navigation policy limits must be positive")
        if not 0.0 < self.minimum_printable_ratio <= 1.0:
            raise NavigationConfigurationError("minimum_printable_ratio must be in (0, 1]")
        object.__setattr__(self, "root", root)


@dataclass
class NavigationTelemetry:
    calls: list[dict[str, Any]] = field(default_factory=list)
    automatic_pruned_paths: int = 0
    denied_content_bytes: int = 0

    def record(self, call: ToolCall, result: ToolResult, elapsed_ms: float) -> None:
        meta = dict(result.meta)
        self.calls.append(
            {
                "tool": call.name,
                "arguments": _safe_arguments(call.arguments),
                "success": bool(result.success),
                "category": str(meta.get("category") or ("ok" if result.success else "tool_error")),
                "paths": list(meta.get("paths") or []),
                "evidence": list(meta.get("evidence") or []),
                "result_chars": len(str(result.output or "")),
                "elapsed_ms": round(elapsed_ms, 3),
            }
        )
        self.automatic_pruned_paths += int(meta.get("pruned_paths") or 0)
        self.denied_content_bytes += int(meta.get("denied_content_bytes") or 0)


def _safe_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    allowed = {"path", "glob", "pattern", "start_line", "line_count", "full", "max_matches", "max_results", "case_sensitive"}
    return {key: value for key, value in arguments.items() if key in allowed}


class NavigationWorkspace:
    def __init__(self, policy: NavigationPolicy) -> None:
        self.policy = policy

    def _failure(self, name: str, message: str, category: str, **meta: Any) -> ToolResult:
        return ToolResult(name=name, output=message, success=False, meta={"category": category, **meta})

    def _relative(self, path: Path) -> str:
        return path.relative_to(self.policy.root).as_posix()

    def _is_secret_name(self, name: str) -> bool:
        lower = name.lower()
        return (
            lower.startswith(".env")
            or lower in {
                "id_rsa",
                "id_dsa",
                "id_ecdsa",
                "id_ed25519",
                "credentials.json",
                "secrets.json",
                "secrets.yaml",
                "secrets.yml",
                "secrets.toml",
            }
        )

    def _denied_relative(self, relative: str, *, is_dir: bool = False) -> str | None:
        parts = Path(relative).parts
        if any(part in self.policy.denied_directory_names for part in parts):
            return "denied_path"
        if any(fnmatch(relative, pattern) for pattern in self.policy.denied_path_globs):
            return "denied_path"
        if not is_dir:
            path = Path(relative)
            if self._is_secret_name(path.name) or path.suffix.lower() in self.policy.denied_suffixes:
                return "denied_content"
            try:
                size = (self.policy.root / path).stat().st_size
            except OSError:
                return "denied_content"
            if path.suffix.lower() == ".json" and size > self.policy.max_json_bytes:
                return "oversized_json"
            if size > self.policy.max_file_bytes:
                return "oversized_file"
        return None

    def _resolve(self, raw_path: str, *, expect_directory: bool | None = None) -> tuple[Path | None, ToolResult | None]:
        if not isinstance(raw_path, str):
            return None, self._failure("path", "path must be a string.", "invalid_arguments")
        text = str(raw_path or ".").strip()
        if not text:
            text = "."
        if Path(text).is_absolute():
            return None, self._failure("path", "Absolute paths are not allowed.", "path_escape")
        try:
            candidate = (self.policy.root / text).resolve(strict=True)
            candidate.relative_to(self.policy.root)
        except (OSError, ValueError):
            return None, self._failure("path", "Path is missing or escapes the navigation root.", "path_escape")
        relative = self._relative(candidate) if candidate != self.policy.root else "."
        denied = self._denied_relative(relative, is_dir=candidate.is_dir())
        if denied:
            return None, self._failure("path", "Path is denied by navigation policy.", denied)
        if expect_directory is True and not candidate.is_dir():
            return None, self._failure("path", "Expected a directory path.", "invalid_arguments")
        if expect_directory is False and not candidate.is_file():
            return None, self._failure("path", "Expected a file path.", "invalid_arguments")
        return candidate, None

    def _read_source_bytes(self, path: Path) -> tuple[bytes | None, str | None]:
        size = path.stat().st_size
        if size > self.policy.max_file_bytes:
            return None, "oversized_file"
        if path.suffix.lower() == ".json" and size > self.policy.max_json_bytes:
            return None, "oversized_json"
        data = path.read_bytes()
        if b"\x00" in data:
            return None, "binary_content"
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return None, "binary_content"
        sample = text[:4_000]
        if sample:
            printable = sum(character.isprintable() or character in "\n\r\t" for character in sample)
            if printable / len(sample) < self.policy.minimum_printable_ratio:
                return None, "binary_content"
        return data, None

    def _walk_source_files(self, start: Path, glob: str) -> tuple[list[Path], int]:
        if start.is_file():
            allowed = start.suffix.lower() in self.policy.source_suffixes and fnmatch(start.name, glob)
            return ([start] if allowed else []), 0
        files: list[Path] = []
        pruned = 0
        for directory, dirnames, filenames in os.walk(start, topdown=True, followlinks=False):
            directory_path = Path(directory)
            kept_dirs: list[str] = []
            for name in sorted(dirnames):
                child = directory_path / name
                try:
                    relative = self._relative(child.resolve(strict=True))
                    escaped = False
                except (OSError, ValueError):
                    relative = ""
                    escaped = True
                if escaped or child.is_symlink() or self._denied_relative(relative, is_dir=True):
                    pruned += 1
                else:
                    kept_dirs.append(name)
            dirnames[:] = kept_dirs
            for name in sorted(filenames):
                path = directory_path / name
                try:
                    resolved = path.resolve(strict=True)
                    relative = self._relative(resolved)
                except (OSError, ValueError):
                    pruned += 1
                    continue
                if path.is_symlink() or self._denied_relative(relative):
                    pruned += 1
                    continue
                if resolved.suffix.lower() not in self.policy.source_suffixes or not fnmatch(name, glob):
                    continue
                files.append(resolved)
        return files, pruned

    def read_file(
        self,
        path: str,
        start_line: int = 1,
        line_count: int | None = None,
        full: bool = False,
    ) -> ToolResult:
        resolved, failure = self._resolve(path, expect_directory=False)
        if failure is not None:
            return ToolResult(name="read_file", output=failure.output, success=False, meta=failure.meta)
        assert resolved is not None
        if resolved.suffix.lower() not in self.policy.source_suffixes:
            return self._failure("read_file", "File type is outside the source allowlist.", "denied_content")
        data, category = self._read_source_bytes(resolved)
        if data is None:
            return self._failure("read_file", "File is denied by the size or binary-content guard.", str(category))
        if not isinstance(full, bool):
            return self._failure("read_file", "full must be a boolean.", "invalid_arguments")
        if full and (start_line != 1 or line_count is not None):
            return self._failure(
                "read_file",
                "full=true cannot be combined with start_line or line_count; use a bounded slice instead.",
                "invalid_arguments",
            )
        if not isinstance(start_line, int) or isinstance(start_line, bool) or start_line < 1:
            return self._failure("read_file", "start_line must be a positive integer.", "invalid_arguments")
        requested = self.policy.default_line_count if line_count is None else line_count
        if not isinstance(requested, int) or isinstance(requested, bool) or requested < 1 or requested > self.policy.max_line_count:
            return self._failure("read_file", f"line_count must be between 1 and {self.policy.max_line_count}.", "invalid_arguments")
        lines = data.decode("utf-8").splitlines()
        if full:
            selected_start, selected_end = 1, len(lines)
        else:
            selected_start = start_line
            selected_end = min(len(lines), start_line + requested - 1)
        rendered = "\n".join(f"{index}: {lines[index - 1]}" for index in range(selected_start, selected_end + 1))
        if len(rendered) > self.policy.max_result_chars:
            return self._failure("read_file", "Requested range exceeds the result-size cap.", "result_too_large")
        relative = self._relative(resolved)
        evidence = [{"path": relative, "lines": list(range(selected_start, selected_end + 1))}]
        return ToolResult(
            name="read_file",
            output=rendered,
            success=True,
            meta={"category": "ok", "paths": [relative], "evidence": evidence, "bytes": len(data), "full": bool(full)},
        )

    def grep(
        self,
        pattern: str,
        path: str = ".",
        glob: str = "*.py",
        max_matches: int | None = None,
        case_sensitive: bool = True,
    ) -> ToolResult:
        if not isinstance(pattern, str) or not pattern or len(pattern) > 1_000:
            return self._failure("grep", "pattern must be a non-empty string of at most 1000 characters.", "invalid_arguments")
        if not isinstance(case_sensitive, bool):
            return self._failure("grep", "case_sensitive must be a boolean.", "invalid_arguments")
        if not isinstance(glob, str) or not glob or "/" in glob or "\\" in glob:
            return self._failure("grep", "glob must be a filename pattern without path separators.", "invalid_arguments")
        limit = self.policy.default_max_matches if max_matches is None else max_matches
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > self.policy.max_matches:
            return self._failure("grep", f"max_matches must be between 1 and {self.policy.max_matches}.", "invalid_arguments")
        try:
            expression = re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)
        except re.error as exc:
            return self._failure("grep", f"Invalid regular expression: {exc}", "invalid_arguments")
        resolved, failure = self._resolve(path)
        if failure is not None:
            return ToolResult(name="grep", output=failure.output, success=False, meta=failure.meta)
        assert resolved is not None
        files, pruned = self._walk_source_files(resolved, glob)
        matches: list[str] = []
        evidence_by_path: dict[str, list[int]] = {}
        result_full = False
        for file_path in files:
            data, denied = self._read_source_bytes(file_path)
            if data is None:
                pruned += 1
                continue
            relative = self._relative(file_path)
            for line_number, line in enumerate(data.decode("utf-8").splitlines(), start=1):
                match = expression.search(line)
                if match:
                    excerpt_start = max(0, match.start() - 240)
                    excerpt_end = min(len(line), match.end() + 240)
                    excerpt = line[excerpt_start:excerpt_end]
                    if excerpt_start:
                        excerpt = "..." + excerpt
                    if excerpt_end < len(line):
                        excerpt += "..."
                    candidate = f"{relative}:{line_number}:{excerpt}"
                    projected_chars = len(candidate) + sum(len(item) + 1 for item in matches)
                    if projected_chars > self.policy.max_result_chars:
                        result_full = True
                        break
                    matches.append(candidate)
                    evidence_by_path.setdefault(relative, []).append(line_number)
                    if len(matches) >= limit:
                        break
            if len(matches) >= limit or result_full:
                break
        rendered = "\n".join(matches)
        evidence = [{"path": path, "lines": lines} for path, lines in evidence_by_path.items()]
        return ToolResult(
            name="grep",
            output=rendered,
            success=True,
            meta={
                "category": "ok",
                "paths": list(evidence_by_path),
                "evidence": evidence,
                "matches": len(matches),
                "truncated": result_full or len(matches) >= limit,
                "pruned_paths": pruned,
            },
        )

    def list_files(self, path: str = ".", glob: str = "*.py", max_results: int | None = None) -> ToolResult:
        if not isinstance(glob, str) or not glob or "/" in glob or "\\" in glob:
            return self._failure("list_files", "glob must be a filename pattern without path separators.", "invalid_arguments")
        limit = self.policy.default_max_results if max_results is None else max_results
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > self.policy.max_results:
            return self._failure("list_files", f"max_results must be between 1 and {self.policy.max_results}.", "invalid_arguments")
        resolved, failure = self._resolve(path)
        if failure is not None:
            return ToolResult(name="list_files", output=failure.output, success=False, meta=failure.meta)
        assert resolved is not None
        files, pruned = self._walk_source_files(resolved, glob)
        relative_paths: list[str] = []
        rendered_chars = 0
        for item in files:
            relative = self._relative(item)
            projected = rendered_chars + len(relative) + (1 if relative_paths else 0)
            if len(relative_paths) >= limit or projected > self.policy.max_result_chars:
                break
            relative_paths.append(relative)
            rendered_chars = projected
        return ToolResult(
            name="list_files",
            output="\n".join(relative_paths),
            success=True,
            meta={"category": "ok", "paths": relative_paths, "evidence": [], "results": len(relative_paths), "truncated": len(files) > len(relative_paths), "pruned_paths": pruned},
        )


class NavigationToolRuntime:
    def __init__(self, workspace: NavigationWorkspace, telemetry: NavigationTelemetry | None = None) -> None:
        self.workspace = workspace
        self.telemetry = telemetry or NavigationTelemetry()
        self._inner = LocalToolRuntime(
            [
                LocalTool(
                    name="read_file",
                    description="Read a bounded line range from one allowed source file.",
                    handler=workspace.read_file,
                    input_schema=NAVIGATION_TOOL_SCHEMAS["read_file"],
                ),
                LocalTool(
                    name="grep",
                    description="Regex-search allowed source files with bounded matches.",
                    handler=workspace.grep,
                    input_schema=NAVIGATION_TOOL_SCHEMAS["grep"],
                ),
                LocalTool(
                    name="list_files",
                    description="List allowed source files under a confined path.",
                    handler=workspace.list_files,
                    input_schema=NAVIGATION_TOOL_SCHEMAS["list_files"],
                ),
            ]
        )

    def list_tools(self) -> list[ToolSpec]:
        return self._inner.list_tools()

    def invoke(self, call: ToolCall) -> ToolResult:
        started = time.perf_counter()
        result = self._inner.invoke(call)
        if result.success:
            for path in list(result.meta.get("paths") or []):
                _, unsafe = self.workspace._resolve(str(path))
                if unsafe is not None:
                    result = ToolResult(
                        name=call.name,
                        output="Tool output failed the post-invocation path safety check.",
                        success=False,
                        meta={"category": "safety_guard"},
                    )
                    break
        self.telemetry.record(call, result, (time.perf_counter() - started) * 1_000)
        return result


@dataclass(frozen=True)
class NoWriteContextConfig:
    max_visible_steps: int = 8
    max_tool_output_chars: int = 8_000
    summary_max_chars: int = 8_000

    def __post_init__(self) -> None:
        if self.max_visible_steps < 1 or self.max_tool_output_chars < 1 or self.summary_max_chars < 1:
            raise NavigationConfigurationError("No-write context limits must be positive")


class NoWriteContextBuilder(AgentContextBuilder):
    def __init__(self, config: NoWriteContextConfig | None = None) -> None:
        self.config = config or NoWriteContextConfig()

    def _bounded_step(self, step: AgentStep) -> AgentStep:
        observation = step.observation
        if observation is None or len(observation.text) <= self.config.max_tool_output_chars:
            return step
        from ..contracts import AgentObservation

        bounded_text = observation.text[: self.config.max_tool_output_chars].rstrip() + "\n... [tool result truncated]"
        tool_result = observation.tool_result
        if tool_result is not None:
            tool_result = ToolResult(name=tool_result.name, output=bounded_text, success=tool_result.success, meta=dict(tool_result.meta))
        bounded_observation = AgentObservation(kind=observation.kind, text=bounded_text, tool_result=tool_result, meta=dict(observation.meta))
        return AgentStep(index=step.index, action=step.action, observation=bounded_observation, trace=step.trace)

    def build_context(
        self,
        task: AgentTask,
        steps: Sequence[AgentStep],
        *,
        active_controller: str,
        escalated: bool,
        memory: Any,
        tool_specs: Sequence[ToolSpec],
        engine_roles: EngineRoles,
    ) -> AgentContext:
        all_steps = list(steps)
        recent = [self._bounded_step(step) for step in all_steps[-self.config.max_visible_steps :]]
        older = all_steps[: -self.config.max_visible_steps] if len(all_steps) > self.config.max_visible_steps else []
        summary_lines: list[str] = []
        for step in older:
            label = step.action.tool_call.name if step.action.tool_call else step.action.kind
            outcome = step.observation.text if step.observation else step.action.message
            summary_lines.append(f"step {step.index}: {label} -> {str(outcome)[:400]}")
        summary = "\n".join(summary_lines)
        if len(summary) > self.config.summary_max_chars:
            summary = summary[-self.config.summary_max_chars :]
        managed_task = AgentTask(
            task_id=task.task_id,
            goal=task.goal,
            session_id=task.session_id,
            context={**dict(task.context), "context_budget": {"history_summary": summary, "visible_step_count": len(recent), "compacted_step_count": len(older), "artifacts": []}},
        )
        return AgentContext(task=managed_task, steps=recent, recalled=(), tool_specs=list(tool_specs), engine_roles=engine_roles, active_controller=active_controller, escalated=escalated)


class ModelTokenizer:
    def count_messages(self, messages: Sequence[ChatMessage]) -> int:
        raise NotImplementedError

    def count_text(self, text: str) -> int:
        raise NotImplementedError


class HuggingFaceModelTokenizer(ModelTokenizer):
    """Load a pinned tokenizer from local files; never downloads model data."""

    def __init__(self, path: str | Path) -> None:
        try:
            from transformers import AutoTokenizer
        except ImportError as exc:
            raise NavigationConfigurationError("transformers is required to load the pinned Qwen tokenizer") from exc
        self.path = str(Path(path).resolve(strict=True))
        self.tokenizer = AutoTokenizer.from_pretrained(self.path, local_files_only=True, trust_remote_code=False)

    def count_messages(self, messages: Sequence[ChatMessage]) -> int:
        payload = [{"role": message.role, "content": message.content or ""} for message in messages]
        tokens = self.tokenizer.apply_chat_template(payload, tokenize=True, add_generation_prompt=True)
        return len(tokens)

    def count_text(self, text: str) -> int:
        return len(self.tokenizer.encode(text, add_special_tokens=False))


class LlamaServerClient(ModelTokenizer):
    """Exact tokenizer plus ChatModel adapter for llama-server's native API."""

    def __init__(
        self,
        base_url: str,
        *,
        seed: int = 0,
        top_k: int = 20,
        top_p: float = 0.95,
        min_p: float = 0.0,
        presence_penalty: float = 1.5,
        disable_thinking: bool = True,
        timeout_seconds: float = 300.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        if self.base_url.endswith("/v1"):
            self.base_url = self.base_url[:-3]
        self.seed = seed
        self.top_k = top_k
        self.top_p = top_p
        self.min_p = min_p
        self.presence_penalty = presence_penalty
        self.disable_thinking = disable_thinking
        self.timeout_seconds = timeout_seconds
        self._prepared: dict[str, tuple[str, int]] = {}

    def get_capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(chat=True, usage_reporting=True, structured_output=True)

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise GenerationError(f"llama-server HTTP {exc.code} from {path}: {body}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise BackendUnavailableError(f"llama-server unreachable at {self.base_url}: {exc}") from exc
        if not isinstance(parsed, dict):
            raise GenerationError(f"llama-server returned a non-object response from {path}")
        return parsed

    def deployment_info(self) -> dict[str, Any]:
        health = self._request_json("GET", "/health")
        if health.get("status") != "ok":
            raise BackendUnavailableError(f"llama-server is not ready: {health}")
        props = self._request_json("GET", "/props")
        return {
            "backend": "llama-server",
            "base_url": self.base_url,
            "health": health,
            "model_path": props.get("model_path"),
            "build_info": props.get("build_info"),
            "chat_template": props.get("chat_template"),
            "chat_template_caps": props.get("chat_template_caps"),
            "default_generation_settings": props.get("default_generation_settings"),
        }

    def _messages_payload(self, messages: Sequence[ChatMessage]) -> list[dict[str, str]]:
        return [{"role": message.role, "content": message.content or ""} for message in messages]

    def _prepare(self, messages: Sequence[ChatMessage]) -> tuple[str, int]:
        payload = self._messages_payload(messages)
        key = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        cached = self._prepared.get(key)
        if cached is not None:
            return cached
        templated = self._request_json("POST", "/apply-template", {"messages": payload})
        prompt = templated.get("prompt")
        if not isinstance(prompt, str):
            raise GenerationError("llama-server /apply-template omitted the prompt string")
        if self.disable_thinking and prompt.endswith("<think>\n"):
            prompt = prompt[: -len("<think>\n")] + "<think>\n\n</think>\n\n"
        tokenized = self._request_json(
            "POST",
            "/tokenize",
            {"content": prompt, "add_special": True, "parse_special": True},
        )
        tokens = tokenized.get("tokens")
        if not isinstance(tokens, list):
            raise GenerationError("llama-server /tokenize omitted the token list")
        prepared = (prompt, len(tokens))
        self._prepared[key] = prepared
        return prepared

    def count_messages(self, messages: Sequence[ChatMessage]) -> int:
        return self._prepare(messages)[1]

    def count_text(self, text: str) -> int:
        tokenized = self._request_json(
            "POST",
            "/tokenize",
            {"content": text, "add_special": False, "parse_special": True},
        )
        tokens = tokenized.get("tokens")
        if not isinstance(tokens, list):
            raise GenerationError("llama-server /tokenize omitted the token list")
        return len(tokens)

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        if not request.messages:
            raise GenerationError("messages list cannot be empty")
        prompt, prompt_token_count = self._prepare(request.messages)
        deterministic = request.temperature == 0.0
        payload: dict[str, Any] = {
            "prompt": prompt,
            "n_predict": request.max_tokens,
            "temperature": request.temperature,
            "top_k": 0 if deterministic else self.top_k,
            "top_p": 1.0 if deterministic else self.top_p,
            "min_p": 0.0 if deterministic else self.min_p,
            "presence_penalty": 0.0 if deterministic else self.presence_penalty,
            "seed": self.seed,
            "cache_prompt": False,
            "stream": False,
            "n_keep": -1,
            "stop": request.stop,
        }
        if request.json_schema is not None:
            payload["json_schema"] = request.json_schema
        started = time.perf_counter()
        raw = self._request_json("POST", "/completion", payload)
        latency_ms = (time.perf_counter() - started) * 1_000
        if raw.get("truncated"):
            raise GenerationError("llama-server truncated the prompt or completion despite the preflight budget")
        generation_settings = raw.get("generation_settings")
        if not isinstance(generation_settings, dict):
            raise GenerationError("llama-server omitted generation_settings")
        expected_settings = {
            "seed": self.seed,
            "temperature": request.temperature,
            "top_k": payload["top_k"],
            "top_p": payload["top_p"],
            "min_p": payload["min_p"],
            "presence_penalty": payload["presence_penalty"],
            "n_predict": request.max_tokens,
        }
        for name, expected in expected_settings.items():
            actual = generation_settings.get(name)
            if actual is None or abs(float(actual) - float(expected)) > 1e-6:
                raise GenerationError(f"llama-server setting mismatch for {name}: requested={expected}, actual={actual}")
        timings = raw.get("timings")
        if not isinstance(timings, dict):
            raise GenerationError("llama-server omitted timing/cache telemetry")
        reused_prompt_tokens = int(timings.get("cache_n") or 0)
        if reused_prompt_tokens != 0:
            raise GenerationError(
                f"llama-server reused {reused_prompt_tokens} prompt tokens despite cache_prompt=false"
            )
        tokens_cached = int(raw.get("tokens_cached") or 0)
        content = raw.get("content")
        if not isinstance(content, str):
            raise GenerationError("llama-server /completion omitted response content")
        input_tokens = raw.get("tokens_evaluated")
        output_tokens = raw.get("tokens_predicted")
        input_count = int(input_tokens) if input_tokens is not None else None
        output_count = int(output_tokens) if output_tokens is not None else None
        if input_count is None or input_count != prompt_token_count:
            raise GenerationError(
                f"llama-server prompt-token mismatch: preflight={prompt_token_count}, response={input_count}"
            )
        stop_type = str(raw.get("stop_type") or "")
        finish_reason = "length" if stop_type == "limit" else "stop"
        return GenerationResponse(
            message=ChatMessage(role="assistant", content=content),
            finish_reason=finish_reason,
            usage=UsageStats(
                input_tokens=input_count,
                output_tokens=output_count,
                total_tokens=(input_count + output_count if input_count is not None and output_count is not None else None),
                latency_ms=round(latency_ms, 3),
            ),
            model_name=str(raw.get("model") or "llama-server-model"),
            backend="llama-server",
            raw_provider_payload={
                "tokens_cached": tokens_cached,
                "reused_prompt_tokens": reused_prompt_tokens,
                "truncated": bool(raw.get("truncated")),
                "generation_settings": generation_settings,
                "timings": timings,
            },
        )


@dataclass(frozen=True)
class NavigationBudget:
    cumulative_token_limit: int = 120_000
    context_window: int = 40_000
    minimum_output_reserve: int = 512
    per_call_output_cap: int = 2_048

    def __post_init__(self) -> None:
        values = (self.cumulative_token_limit, self.context_window, self.minimum_output_reserve, self.per_call_output_cap)
        if any(value < 1 for value in values):
            raise NavigationConfigurationError("Navigation budget values must be positive")
        if self.minimum_output_reserve >= self.context_window:
            raise NavigationConfigurationError("minimum_output_reserve must be smaller than context_window")


@dataclass
class PlannerUsage:
    calls: list[dict[str, Any]] = field(default_factory=list)
    cumulative_actual_tokens: int = 0
    fallback_usage_calls: int = 0
    stop_reason: str | None = None


class BudgetedNavigationPlanner:
    allowed_tools = frozenset({"read_file", "grep", "list_files"})

    def __init__(
        self,
        *,
        engine: ChatModel,
        tokenizer: ModelTokenizer,
        budget: NavigationBudget | None = None,
        temperature: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.engine = engine
        self.tokenizer = tokenizer
        self.budget = budget or NavigationBudget()
        self.temperature = temperature
        self.metadata = dict(metadata or {})
        self.usage = PlannerUsage()

    def _user_prompt(self, context: AgentContext) -> str:
        parts = [f"Task:\n{context.task.goal}"]
        history_summary = dict(context.task.context.get("context_budget") or {}).get("history_summary")
        if history_summary:
            parts.append(f"Earlier bounded history:\n{history_summary}")
        if context.steps:
            rendered: list[str] = []
            for step in context.steps:
                if step.action.tool_call:
                    rendered.append(f"Step {step.index} request: {step.action.tool_call.name} {json.dumps(step.action.tool_call.arguments, sort_keys=True)}")
                else:
                    rendered.append(f"Step {step.index} action: {step.action.kind} {step.action.message}")
                if step.observation:
                    rendered.append(f"Step {step.index} result: {step.observation.text}")
            parts.append("Recent tool history:\n" + "\n".join(rendered))
        parts.append("Choose the next tool call or return the final answer as JSON.")
        return "\n\n".join(parts)

    def _finalization_user_prompt(self, context: AgentContext, instruction: str) -> str:
        parts = [f"Task:\n{context.task.goal}"]
        history_summary = dict(context.task.context.get("context_budget") or {}).get("history_summary")
        if history_summary:
            parts.append(f"Earlier bounded history:\n{history_summary}")
        if context.steps:
            rendered: list[str] = []
            for step in context.steps:
                if step.action.tool_call:
                    rendered.append(
                        f"Step {step.index} request: {step.action.tool_call.name} "
                        f"{json.dumps(step.action.tool_call.arguments, sort_keys=True)}"
                    )
                else:
                    rendered.append(f"Step {step.index} action: {step.action.kind} {step.action.message}")
                if step.observation:
                    rendered.append(f"Step {step.index} result: {step.observation.text}")
            parts.append("Preserved tool history:\n" + "\n".join(rendered))
        parts.append(f"Control instruction:\n{instruction}")
        parts.append("Return the final answer now. No tool action is permitted.")
        return "\n\n".join(parts)

    def _budget_stop(self, reason: str) -> AgentAction:
        self.usage.stop_reason = reason
        return AgentAction.final(f"Navigation stopped before model invocation: {reason}.", meta={"navigation_stop_reason": reason, "usage": asdict(self.usage)})

    def _validate_payload(self, payload: dict[str, Any]) -> str | None:
        kind = str(payload.get("kind") or "").strip().lower()
        if kind == "final":
            if not str(payload.get("final_output") or payload.get("output") or payload.get("message") or "").strip():
                return "final_output must be non-empty"
            return None
        if kind != "tool":
            return "kind must be tool or final"
        name = str(payload.get("tool_name") or payload.get("name") or "")
        if name not in self.allowed_tools:
            return f"tool_name must be one of {sorted(self.allowed_tools)}"
        arguments = payload.get("arguments") or payload.get("args") or {}
        if not isinstance(arguments, dict):
            return "arguments must be an object"
        schema = NAVIGATION_TOOL_SCHEMAS[name]
        allowed = set(schema.get("properties") or {})
        required = set(schema.get("required") or [])
        if set(arguments) - allowed:
            return f"unknown arguments for {name}: {sorted(set(arguments) - allowed)}"
        if required - set(arguments):
            return f"missing arguments for {name}: {sorted(required - set(arguments))}"
        for key, value in arguments.items():
            expected = schema["properties"][key].get("type")
            if expected == "string" and not isinstance(value, str):
                return f"{key} must be a string"
            if expected == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
                return f"{key} must be an integer"
            if expected == "boolean" and not isinstance(value, bool):
                return f"{key} must be a boolean"
        return None

    def plan(self, context: AgentContext) -> AgentAction:
        messages = [ChatMessage(role="system", content=SYSTEM_PROMPT), ChatMessage(role="user", content=self._user_prompt(context))]
        prompt_tokens = self.tokenizer.count_messages(messages)
        remaining_cumulative = self.budget.cumulative_token_limit - self.usage.cumulative_actual_tokens
        if prompt_tokens + self.budget.minimum_output_reserve > remaining_cumulative:
            return self._budget_stop("token_budget")
        if prompt_tokens + self.budget.minimum_output_reserve > self.budget.context_window:
            return self._budget_stop("context_limit")
        max_output = min(self.budget.per_call_output_cap, remaining_cumulative - prompt_tokens, self.budget.context_window - prompt_tokens)
        response = self.engine.generate(
            GenerationRequest(
                messages=messages,
                max_tokens=max_output,
                temperature=self.temperature,
                json_schema=NAVIGATION_ACTION_SCHEMA,
                metadata={**self.metadata, "task_id": context.task.task_id},
            )
        )
        actual_input = response.usage.input_tokens
        actual_output = response.usage.output_tokens
        used_fallback = actual_input is None or actual_output is None
        if actual_input is None:
            actual_input = prompt_tokens
        if actual_output is None:
            actual_output = self.tokenizer.count_text(response.message.content or "")
        actual_total = int(actual_input) + int(actual_output)
        self.usage.cumulative_actual_tokens += actual_total
        if used_fallback:
            self.usage.fallback_usage_calls += 1
        self.usage.calls.append(
            {
                "system_prompt": SYSTEM_PROMPT,
                "user_prompt": messages[1].content or "",
                "prompt_tokens_pre_call": prompt_tokens,
                "requested_max_output_tokens": max_output,
                "actual_input_tokens": actual_input,
                "actual_output_tokens": actual_output,
                "actual_total_tokens": actual_total,
                "backend_reported": not used_fallback,
                "model": response.model_name,
                "backend": response.backend,
                "finish_reason": response.finish_reason,
                "latency_ms": response.usage.latency_ms,
                "response_text": response.message.content or "",
            }
        )
        try:
            payload = extract_json_object(response.message.content or "")
        except (ValueError, json.JSONDecodeError) as exc:
            return AgentAction.message_only(f"Rejected invalid JSON action: {exc}", meta={"invalid_action": True})
        validation_error = self._validate_payload(payload)
        if validation_error:
            return AgentAction.message_only(f"Rejected invalid action: {validation_error}", meta={"invalid_action": True})
        return action_from_payload(payload, response=response, engine_role="planner")

    def finalize(
        self,
        context: AgentContext,
        instruction: str,
        *,
        full_context: AgentContext | None = None,
    ) -> AgentAction:
        messages = [
            ChatMessage(role="system", content=FINALIZATION_SYSTEM_PROMPT),
            ChatMessage(role="user", content=self._finalization_user_prompt(context, instruction)),
        ]
        full_messages = [
            ChatMessage(role="system", content=FINALIZATION_SYSTEM_PROMPT),
            ChatMessage(
                role="user",
                content=self._finalization_user_prompt(full_context or context, instruction),
            ),
        ]
        prompt_tokens = self.tokenizer.count_messages(messages)
        full_prompt_tokens = self.tokenizer.count_messages(full_messages)
        remaining_cumulative = self.budget.cumulative_token_limit - self.usage.cumulative_actual_tokens
        required_minimum = prompt_tokens + self.budget.minimum_output_reserve
        telemetry = {
            "full_prompt_tokens": full_prompt_tokens,
            "truncated_prompt_tokens": prompt_tokens,
            "token_savings": full_prompt_tokens - prompt_tokens,
            "available_cumulative_tokens": remaining_cumulative,
            "available_context_tokens": self.budget.context_window,
            "required_minimum_tokens": required_minimum,
        }
        if required_minimum > remaining_cumulative or required_minimum > self.budget.context_window:
            blockers = []
            if required_minimum > remaining_cumulative:
                blockers.append("cumulative_token_limit")
            if required_minimum > self.budget.context_window:
                blockers.append("context_window")
            return AgentAction.message_only(
                "Insufficient safe budget for constrained finalization.",
                meta={
                    "finalization_outcome": "budget_unavailable",
                    "budget_blockers": blockers,
                    **telemetry,
                },
            )

        max_output = min(
            self.budget.per_call_output_cap,
            remaining_cumulative - prompt_tokens,
            self.budget.context_window - prompt_tokens,
        )
        response = self.engine.generate(
            GenerationRequest(
                messages=messages,
                max_tokens=max_output,
                temperature=0.0,
                json_schema=FINALIZATION_ACTION_SCHEMA,
                metadata={
                    **self.metadata,
                    "task_id": context.task.task_id,
                    "phase": "guard_finalization",
                    "tools_enabled": False,
                },
            )
        )
        actual_input = response.usage.input_tokens
        actual_output = response.usage.output_tokens
        used_fallback = actual_input is None or actual_output is None
        if actual_input is None:
            actual_input = prompt_tokens
        if actual_output is None:
            actual_output = self.tokenizer.count_text(response.message.content or "")
        actual_total = int(actual_input) + int(actual_output)
        self.usage.cumulative_actual_tokens += actual_total
        if used_fallback:
            self.usage.fallback_usage_calls += 1
        self.usage.calls.append(
            {
                "phase": "guard_finalization",
                "system_prompt": FINALIZATION_SYSTEM_PROMPT,
                "user_prompt": messages[1].content or "",
                "prompt_tokens_pre_call": prompt_tokens,
                "requested_max_output_tokens": max_output,
                "actual_input_tokens": actual_input,
                "actual_output_tokens": actual_output,
                "actual_total_tokens": actual_total,
                "backend_reported": not used_fallback,
                "model": response.model_name,
                "backend": response.backend,
                "finish_reason": response.finish_reason,
                "latency_ms": response.usage.latency_ms,
                "response_text": response.message.content or "",
            }
        )
        try:
            payload = extract_json_object(response.message.content or "")
        except (ValueError, json.JSONDecodeError) as exc:
            return AgentAction.message_only(
                f"Constrained finalization returned invalid JSON: {exc}",
                meta={"finalization_outcome": "no_answer", **telemetry},
            )
        if set(payload) - {"kind", "final_output"}:
            return AgentAction.message_only(
                "Constrained finalization returned unsupported fields.",
                meta={"finalization_outcome": "no_answer", **telemetry},
            )
        if str(payload.get("kind") or "").strip().lower() != "final":
            return AgentAction.message_only(
                "Constrained finalization did not return a final action.",
                meta={"finalization_outcome": "no_answer", **telemetry},
            )
        output = str(payload.get("final_output") or "").strip()
        if not output:
            return AgentAction.message_only(
                "Constrained finalization returned an empty answer.",
                meta={"finalization_outcome": "no_answer", **telemetry},
            )
        action = action_from_payload(payload, response=response, engine_role="planner")
        return AgentAction.final(output, meta={**dict(action.meta), "finalization_outcome": "success", **telemetry})


class NavigationRunHook(AgentRunLifecycleHook):
    def __init__(self, planner: BudgetedNavigationPlanner) -> None:
        self.planner = planner

    def on_start(self, task: AgentTask, *, max_steps: int, engine_roles: EngineRoles) -> None:
        return None

    def on_step(self, task: AgentTask, context: AgentContext, step: AgentStep, run: AgentRun) -> None:
        return None

    def on_finish(self, run: AgentRun) -> None:
        run.meta["planner_usage"] = asdict(self.planner.usage)
        if self.planner.usage.stop_reason:
            run.status = "stopped"
            if self.planner.usage.stop_reason == "token_budget":
                run.stop_reason = "token_budget"
            elif self.planner.usage.stop_reason == "context_limit":
                run.stop_reason = "context_limit"


@dataclass
class NavigationHarness:
    root: Path
    runtime: AgentRuntime
    planner: BudgetedNavigationPlanner
    tools: NavigationToolRuntime
    max_steps: int = 25
    action_guard_mode: str = "shadow"

    def run(self, question: str = LEAD_QUESTION, *, task_id: str = "nav-test-00") -> AgentRun:
        return self.runtime.run(AgentTask(task_id=task_id, goal=question, context={"navigation_root": str(self.root)}), max_steps=self.max_steps)


def build_navigation_harness(
    *,
    root: str | Path,
    engine: ChatModel,
    tokenizer: ModelTokenizer,
    policy: NavigationPolicy | None = None,
    budget: NavigationBudget | None = None,
    max_steps: int = 25,
    temperature: float = 0.0,
    metadata: dict[str, Any] | None = None,
    action_guard_mode: str = "shadow",
) -> NavigationHarness:
    if max_steps < 1:
        raise NavigationConfigurationError("max_steps must be positive")
    if action_guard_mode not in {"off", "shadow", "enforce"}:
        raise NavigationConfigurationError("action_guard_mode must be one of: off, shadow, enforce")
    resolved_policy = policy or NavigationPolicy(Path(root))
    workspace = NavigationWorkspace(resolved_policy)
    tools = NavigationToolRuntime(workspace)
    planner = BudgetedNavigationPlanner(engine=engine, tokenizer=tokenizer, budget=budget, temperature=temperature, metadata=metadata)
    control_hooks = (
        []
        if action_guard_mode == "off"
        else [ActionTrajectoryGuardHook(mode=action_guard_mode)]
    )
    runtime = AgentRuntime(
        planner=planner,
        tool_runtime=tools,
        memory=NullMemoryAdapter(),
        context_builder=NoWriteContextBuilder(),
        lifecycle_hooks=[NavigationRunHook(planner)],
        control_hooks=control_hooks,
    )
    return NavigationHarness(
        root=resolved_policy.root,
        runtime=runtime,
        planner=planner,
        tools=tools,
        max_steps=max_steps,
        action_guard_mode=action_guard_mode,
    )


@dataclass(frozen=True)
class GroundTruthRegion:
    id: str
    path: str
    start_line: int
    end_line: int
    classification: str
    required_answer_terms: tuple[str, ...] = ()
    symbol: str = ""


def load_ground_truth(path: str | Path) -> tuple[str, list[GroundTruthRegion]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    regions = [
        GroundTruthRegion(
            id=str(item["id"]),
            path=str(item["path"]),
            start_line=int(item["start_line"]),
            end_line=int(item["end_line"]),
            classification=str(item["classification"]),
            required_answer_terms=tuple(str(term) for term in item.get("required_answer_terms") or []),
            symbol=str(item.get("symbol") or ""),
        )
        for item in payload["regions"]
    ]
    if not regions or len({region.id for region in regions}) != len(regions):
        raise NavigationConfigurationError("Ground truth requires a non-empty set of unique region IDs")
    for region in regions:
        region_path = Path(region.path)
        if region_path.is_absolute() or ".." in region_path.parts or region.start_line < 1 or region.end_line < region.start_line:
            raise NavigationConfigurationError(f"Invalid ground-truth region bounds or path: {region.id}")
        if not region.classification.strip() or not region.required_answer_terms:
            raise NavigationConfigurationError(f"Ground-truth region {region.id} requires classification and required_answer_terms")
    return str(payload.get("question") or LEAD_QUESTION), regions


def validate_ground_truth_snapshot(
    path: str | Path,
    manifest: dict[str, Any],
    root: str | Path,
) -> None:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    snapshot = payload.get("snapshot")
    if not isinstance(snapshot, dict):
        raise NavigationConfigurationError("Ground truth requires snapshot metadata")
    expected_git_sha = snapshot.get("git_sha")
    if expected_git_sha != manifest.get("git_sha"):
        raise NavigationConfigurationError(
            f"Ground-truth Git SHA mismatch: key={expected_git_sha}, repo={manifest.get('git_sha')}"
        )
    expected_sources = snapshot.get("source_sha256")
    if not isinstance(expected_sources, dict) or not expected_sources:
        raise NavigationConfigurationError("Ground truth requires snapshot.source_sha256")
    manifest_sources = {item["path"]: item["sha256"] for item in manifest.get("allowed_sources") or []}
    for source_path, expected_hash in expected_sources.items():
        actual_hash = manifest_sources.get(str(source_path))
        if actual_hash != expected_hash:
            raise NavigationConfigurationError(
                f"Ground-truth source hash mismatch for {source_path}: key={expected_hash}, repo={actual_hash}"
            )
    resolved_root = Path(root).resolve(strict=True)
    for item in payload.get("regions") or []:
        source_path = str(item.get("path") or "")
        if source_path not in expected_sources:
            raise NavigationConfigurationError(f"Ground-truth region uses an unpinned source: {source_path}")
        start_line = int(item["start_line"])
        end_line = int(item["end_line"])
        lines = (resolved_root / source_path).read_text(encoding="utf-8").splitlines()
        region_text = "\n".join(lines[start_line - 1 : end_line])
        anchors = item.get("anchors")
        if not isinstance(anchors, list) or not anchors:
            raise NavigationConfigurationError(f"Ground-truth region {item.get('id')} requires anchors")
        for anchor in anchors:
            if str(anchor) not in region_text:
                raise NavigationConfigurationError(
                    f"Ground-truth anchor missing in {item.get('id')}: {anchor!r}"
                )


def score_navigation_run(
    run: AgentRun,
    telemetry: NavigationTelemetry,
    regions: Sequence[GroundTruthRegion],
    budget: NavigationBudget,
    *,
    max_steps: int = 25,
) -> dict[str, Any]:
    surfaced: set[str] = set()
    useful_calls = 0
    successful_calls = 0
    for call in telemetry.calls:
        call_useful = False
        if call["success"]:
            successful_calls += 1
        for evidence in call.get("evidence") or []:
            evidence_lines = set(int(line) for line in evidence.get("lines") or [])
            for region in regions:
                if evidence.get("path") == region.path and evidence_lines.intersection(range(region.start_line, region.end_line + 1)):
                    surfaced.add(region.id)
                    call_useful = True
        if call_useful:
            useful_calls += 1
    raw_claims = run.meta.get("navigation_claims")
    if raw_claims is None and run.steps:
        raw_claims = run.steps[-1].action.meta.get("navigation_claims")
    claim_parse_errors: list[str] = []
    claims: list[NavigationClaim] = []
    if isinstance(raw_claims, list):
        for index, item in enumerate(raw_claims, start=1):
            if not isinstance(item, Mapping):
                claim_parse_errors.append(f"claim {index} is not an object")
                continue
            try:
                claims.append(NavigationClaim.from_mapping(item))
            except (TypeError, ValueError) as exc:
                claim_parse_errors.append(f"claim {index} is invalid: {exc}")
    else:
        claim_parse_errors.append("missing structured navigation claims")
    claim_validation = validate_navigation_claims(
        claims,
        telemetry_calls=telemetry.calls,
        regions=regions,
    )
    correctly_named = set(claim_validation.matched_region_ids)
    false_positive_paths = sorted(
        {
            str(claim.get("path") or "")
            for claim in claim_validation.unsupported_claims
            if claim.get("path")
        }
    )
    claim_errors = [*claim_parse_errors, *claim_validation.errors]
    blocked = [call for call in telemetry.calls if call["category"] in {"path_escape", "denied_path", "denied_content", "oversized_json", "oversized_file", "binary_content", "safety_guard"}]
    blocked_signatures = [(call["tool"], json.dumps(call["arguments"], sort_keys=True)) for call in blocked]
    repeated_blocked = len(blocked_signatures) - len(set(blocked_signatures))
    usage = dict(run.meta.get("planner_usage") or {})
    cumulative_tokens = int(usage.get("cumulative_actual_tokens") or 0)
    evidence_recall = len(surfaced) / len(regions) if regions else 0.0
    answer_correctness = len(correctly_named) / len(regions) if regions else 0.0
    passed = (
        evidence_recall == 1.0
        and answer_correctness == 1.0
        and not false_positive_paths
        and not claim_validation.unsupported_claims
        and not claim_errors
        and telemetry.denied_content_bytes == 0
        and len(blocked) <= 3
        and repeated_blocked == 0
        and cumulative_tokens <= budget.cumulative_token_limit
        and len(run.steps) <= max_steps
        and run.status == "completed"
    )
    return {
        "passed": passed,
        "evidence_recall": evidence_recall,
        "surfaced_region_ids": sorted(surfaced),
        "answer_correctness": answer_correctness,
        "correct_region_ids": sorted(correctly_named),
        "answer_scoring_mode": "structured_claims",
        "missing_region_ids": list(claim_validation.missing_region_ids),
        "unsupported_claims": list(claim_validation.unsupported_claims),
        "claim_validation_errors": claim_errors,
        "false_positive_paths": false_positive_paths,
        "denied_content_bytes": telemetry.denied_content_bytes,
        "blocked_attempts": len(blocked),
        "repeated_blocked_attempts": repeated_blocked,
        "automatic_pruned_paths": telemetry.automatic_pruned_paths,
        "useful_call_rate": useful_calls / successful_calls if successful_calls else 0.0,
        "tool_calls": len(telemetry.calls),
        "cumulative_tokens": cumulative_tokens,
        "steps": len(run.steps),
        "stop_reason": run.stop_reason,
    }


def _git_value(root: Path, *args: str) -> str | None:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def build_environment_manifest(policy: NavigationPolicy) -> dict[str, Any]:
    workspace = NavigationWorkspace(policy)
    allowed, pruned = workspace._walk_source_files(policy.root, "*")
    allowed_records = []
    for path in sorted(allowed):
        data, denied = workspace._read_source_bytes(path)
        if data is None:
            pruned += 1
            continue
        allowed_records.append({"path": workspace._relative(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    denied_count = 0
    denied_bytes = 0
    total_count = 0
    total_bytes = 0
    for directory, dirnames, filenames in os.walk(policy.root, topdown=True, followlinks=False):
        directory_path = Path(directory)
        dirnames[:] = [name for name in dirnames if name != ".git"]
        for name in filenames:
            path = directory_path / name
            try:
                size = path.stat().st_size
                relative = workspace._relative(path.resolve(strict=True))
            except (OSError, ValueError):
                continue
            total_count += 1
            total_bytes += size
            oversized_json = path.suffix.lower() == ".json" and size > policy.max_json_bytes
            if workspace._denied_relative(relative) or path.suffix.lower() not in policy.source_suffixes or size > policy.max_file_bytes or oversized_json:
                denied_count += 1
                denied_bytes += size
    payload = {
        "schema_version": 1,
        "root_name": policy.root.name,
        "git_sha": _git_value(policy.root, "rev-parse", "HEAD"),
        "git_status_porcelain": _git_value(policy.root, "status", "--porcelain"),
        "measurement": {"implementation": "agent_lib.eval.repo_navigation.build_environment_manifest", "git_commands": ["git rev-parse HEAD", "git status --porcelain"]},
        "policy": {**asdict(policy), "root": str(policy.root), "denied_directory_names": sorted(policy.denied_directory_names), "denied_suffixes": sorted(policy.denied_suffixes), "source_suffixes": sorted(policy.source_suffixes)},
        "totals": {"files": total_count, "bytes": total_bytes, "allowed_files": len(allowed_records), "allowed_bytes": sum(item["bytes"] for item in allowed_records), "denied_or_unscoped_files": denied_count, "denied_or_unscoped_bytes": denied_bytes, "pruned_paths": pruned},
        "allowed_sources": allowed_records,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def tree_content_digest(root: str | Path) -> str:
    resolved = Path(root).resolve(strict=True)
    digest = hashlib.sha256()
    for directory, dirnames, filenames in os.walk(resolved, topdown=True, followlinks=False):
        dirnames[:] = sorted(name for name in dirnames if name != ".git")
        directory_path = Path(directory)
        for name in sorted(filenames):
            path = directory_path / name
            try:
                relative = path.relative_to(resolved).as_posix()
            except OSError:
                continue
            digest.update(f"{relative}\0".encode("utf-8"))
            if path.is_symlink():
                digest.update(f"symlink:{os.readlink(path)}\n".encode("utf-8"))
                continue
            try:
                with path.open("rb") as handle:
                    while chunk := handle.read(1024 * 1024):
                        digest.update(chunk)
            except OSError:
                digest.update(b"[unreadable]")
            digest.update(b"\n")
    return digest.hexdigest()


def render_run_record(
    *,
    run: AgentRun,
    harness: NavigationHarness,
    manifest: dict[str, Any],
    pre_tree_digest: str,
    post_tree_digest: str,
    score: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    steps = []
    for step in run.steps:
        action = {
            "kind": step.action.kind,
            "message": step.action.message,
            "final_output": step.action.final_output,
            "meta": dict(step.action.meta),
            "tool_call": asdict(step.action.tool_call) if step.action.tool_call is not None else None,
        }
        observation = None
        if step.observation is not None:
            observation = {
                "kind": step.observation.kind,
                "text": step.observation.text,
                "meta": dict(step.observation.meta),
                "tool_result": asdict(step.observation.tool_result) if step.observation.tool_result is not None else None,
            }
        trace = asdict(step.trace) if step.trace is not None else None
        steps.append({"index": step.index, "action": action, "observation": observation, "trace": trace})
    return {
        "schema_version": 1,
        "config": dict(config or {}),
        "manifest_sha256": manifest["manifest_sha256"],
        "read_only_verified": pre_tree_digest == post_tree_digest,
        "pre_tree_digest": pre_tree_digest,
        "post_tree_digest": post_tree_digest,
        "run": {"status": run.status, "stop_reason": run.stop_reason, "final_output": run.final_output, "elapsed_seconds": run.elapsed_seconds, "step_count": len(run.steps), "steps": steps, "meta": run.meta},
        "planner_usage": asdict(harness.planner.usage),
        "tool_telemetry": harness.tools.telemetry.calls,
        "automatic_pruned_paths": harness.tools.telemetry.automatic_pruned_paths,
        "denied_content_bytes": harness.tools.telemetry.denied_content_bytes,
        "score": score,
    }
