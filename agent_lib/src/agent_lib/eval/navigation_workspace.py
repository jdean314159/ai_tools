from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
import os
from pathlib import Path
import re
import time
from typing import Any

from ..contracts import ToolCall, ToolResult, ToolSpec
from ..tools import LocalTool, LocalToolRuntime
from .navigation_contracts import NavigationConfigurationError


NAVIGATION_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "read_file": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "path": {"type": "string"},
            "start_line": {"type": "integer"},
            "line_count": {"type": "integer"},
            "full": {"type": "boolean"},
        },
        "required": ["path"],
    },
    "grep": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "pattern": {"type": "string"},
            "path": {"type": "string"},
            "glob": {"type": "string"},
            "max_matches": {"type": "integer"},
            "case_sensitive": {"type": "boolean"},
        },
        "required": ["pattern"],
    },
    "list_files": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "path": {"type": "string"},
            "glob": {"type": "string"},
            "max_results": {"type": "integer"},
        },
    },
}


@dataclass(frozen=True)
class NavigationPolicy:
    root: Path
    denied_directory_names: frozenset[str] = frozenset(
        {
            ".git",
            ".venv",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            "node_modules",
            "build",
            "dist",
        }
    )
    denied_path_globs: tuple[str, ...] = (
        "tests/**/runs",
        "tests/**/runs/**",
        "examples/asc_probe/runs",
        "examples/asc_probe/runs/**",
    )
    denied_suffixes: frozenset[str] = frozenset(
        {
            ".db",
            ".sqlite",
            ".sqlite3",
            ".bin",
            ".jsonl",
            ".pem",
            ".key",
            ".p12",
            ".pfx",
            ".pyc",
            ".so",
            ".dylib",
            ".dll",
        }
    )
    source_suffixes: frozenset[str] = frozenset(
        {
            ".py",
            ".pyi",
            ".md",
            ".rst",
            ".toml",
            ".yaml",
            ".yml",
            ".json",
            ".txt",
            ".ini",
            ".cfg",
            ".sh",
            ".js",
            ".jsx",
            ".ts",
            ".tsx",
            ".html",
            ".css",
            ".sql",
        }
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
    allowed = {
        "path",
        "glob",
        "pattern",
        "start_line",
        "line_count",
        "full",
        "max_matches",
        "max_results",
        "case_sensitive",
    }
    return {key: value for key, value in arguments.items() if key in allowed}


class NavigationWorkspace:
    def __init__(self, policy: NavigationPolicy) -> None:
        self.policy = policy

    def _failure(self, name: str, message: str, category: str, **meta: Any) -> ToolResult:
        return ToolResult(
            name=name, output=message, success=False, meta={"category": category, **meta}
        )

    def _relative(self, path: Path) -> str:
        return path.relative_to(self.policy.root).as_posix()

    def _is_secret_name(self, name: str) -> bool:
        lower = name.lower()
        return lower.startswith(".env") or lower in {
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

    def _denied_relative(self, relative: str, *, is_dir: bool = False) -> str | None:
        parts = Path(relative).parts
        if any(part in self.policy.denied_directory_names for part in parts):
            return "denied_path"
        if any(fnmatch(relative, pattern) for pattern in self.policy.denied_path_globs):
            return "denied_path"
        if not is_dir:
            path = Path(relative)
            if (
                self._is_secret_name(path.name)
                or path.suffix.lower() in self.policy.denied_suffixes
            ):
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

    def _resolve(
        self, raw_path: str, *, expect_directory: bool | None = None
    ) -> tuple[Path | None, ToolResult | None]:
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
            return None, self._failure(
                "path", "Path is missing or escapes the navigation root.", "path_escape"
            )
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
            printable = sum(
                character.isprintable() or character in "\n\r\t" for character in sample
            )
            if printable / len(sample) < self.policy.minimum_printable_ratio:
                return None, "binary_content"
        return data, None

    def _walk_source_files(self, start: Path, glob: str) -> tuple[list[Path], int]:
        if start.is_file():
            allowed = start.suffix.lower() in self.policy.source_suffixes and fnmatch(
                start.name, glob
            )
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
                if resolved.suffix.lower() not in self.policy.source_suffixes or not fnmatch(
                    name, glob
                ):
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
            return ToolResult(
                name="read_file", output=failure.output, success=False, meta=failure.meta
            )
        assert resolved is not None
        if resolved.suffix.lower() not in self.policy.source_suffixes:
            return self._failure(
                "read_file", "File type is outside the source allowlist.", "denied_content"
            )
        data, category = self._read_source_bytes(resolved)
        if data is None:
            return self._failure(
                "read_file", "File is denied by the size or binary-content guard.", str(category)
            )
        if not isinstance(full, bool):
            return self._failure("read_file", "full must be a boolean.", "invalid_arguments")
        if full and (start_line != 1 or line_count is not None):
            return self._failure(
                "read_file",
                "full=true cannot be combined with start_line or line_count; use a bounded slice instead.",
                "invalid_arguments",
            )
        if not isinstance(start_line, int) or isinstance(start_line, bool) or start_line < 1:
            return self._failure(
                "read_file", "start_line must be a positive integer.", "invalid_arguments"
            )
        requested = self.policy.default_line_count if line_count is None else line_count
        if (
            not isinstance(requested, int)
            or isinstance(requested, bool)
            or requested < 1
            or requested > self.policy.max_line_count
        ):
            return self._failure(
                "read_file",
                f"line_count must be between 1 and {self.policy.max_line_count}.",
                "invalid_arguments",
            )
        lines = data.decode("utf-8").splitlines()
        if full:
            selected_start, selected_end = 1, len(lines)
        else:
            selected_start = start_line
            selected_end = min(len(lines), start_line + requested - 1)
        rendered = "\n".join(
            f"{index}: {lines[index - 1]}" for index in range(selected_start, selected_end + 1)
        )
        if len(rendered) > self.policy.max_result_chars:
            return self._failure(
                "read_file", "Requested range exceeds the result-size cap.", "result_too_large"
            )
        relative = self._relative(resolved)
        evidence = [{"path": relative, "lines": list(range(selected_start, selected_end + 1))}]
        return ToolResult(
            name="read_file",
            output=rendered,
            success=True,
            meta={
                "category": "ok",
                "paths": [relative],
                "evidence": evidence,
                "bytes": len(data),
                "full": bool(full),
            },
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
            return self._failure(
                "grep",
                "pattern must be a non-empty string of at most 1000 characters.",
                "invalid_arguments",
            )
        if not isinstance(case_sensitive, bool):
            return self._failure("grep", "case_sensitive must be a boolean.", "invalid_arguments")
        if not isinstance(glob, str) or not glob or "/" in glob or "\\" in glob:
            return self._failure(
                "grep",
                "glob must be a filename pattern without path separators.",
                "invalid_arguments",
            )
        limit = self.policy.default_max_matches if max_matches is None else max_matches
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or limit < 1
            or limit > self.policy.max_matches
        ):
            return self._failure(
                "grep",
                f"max_matches must be between 1 and {self.policy.max_matches}.",
                "invalid_arguments",
            )
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

    def list_files(
        self, path: str = ".", glob: str = "*.py", max_results: int | None = None
    ) -> ToolResult:
        if not isinstance(glob, str) or not glob or "/" in glob or "\\" in glob:
            return self._failure(
                "list_files",
                "glob must be a filename pattern without path separators.",
                "invalid_arguments",
            )
        limit = self.policy.default_max_results if max_results is None else max_results
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or limit < 1
            or limit > self.policy.max_results
        ):
            return self._failure(
                "list_files",
                f"max_results must be between 1 and {self.policy.max_results}.",
                "invalid_arguments",
            )
        resolved, failure = self._resolve(path)
        if failure is not None:
            return ToolResult(
                name="list_files", output=failure.output, success=False, meta=failure.meta
            )
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
            meta={
                "category": "ok",
                "paths": relative_paths,
                "evidence": [],
                "results": len(relative_paths),
                "truncated": len(files) > len(relative_paths),
                "pruned_paths": pruned,
            },
        )


class NavigationToolRuntime:
    def __init__(
        self, workspace: NavigationWorkspace, telemetry: NavigationTelemetry | None = None
    ) -> None:
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
