"""Exact, AST-backed contracts for the NAV-VERIFIABLE-00 evaluation track."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .navigation_claims import EvidenceRef


TaskKind = Literal["definition", "direct_callers", "call_path", "mutation_target"]
ClaimKind = Literal["definition", "call_edge", "call_path", "mutation_target"]

VERIFIABLE_TASK_SCHEMA_VERSION = 1
VERIFIABLE_PAIR_SCHEMA_VERSION = 1
RELATION_CANONICALIZATION_VERSION = 1
VERIFIABLE_ADMISSION_SCHEMA_VERSION = 1

RELATION_CLAIMS_SCHEMA: dict[str, Any] = {
    "type": "array",
    "items": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "kind": {
                "type": "string",
                "enum": ["definition", "call_edge", "call_path", "mutation_target"],
                "description": "Exact relation type requested by the task.",
            },
            "path": {
                "type": "string",
                "minLength": 1,
                "description": "Repository-relative source file path, never a call-chain description.",
            },
            "symbol": {
                "type": "string",
                "minLength": 1,
                "description": "Canonical module-qualified enclosing or caller symbol.",
            },
            "target": {
                "type": "string",
                "description": "Canonical callee/endpoint, or the exact call expression for mutation_target.",
            },
            "path_symbols": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "description": "Ordered canonical symbols for call_path only; empty for other kinds.",
            },
            "evidence": {
                "type": "array",
                "minItems": 1,
                "description": "Cite only the exact minimal syntax lines proving this relation; a call path needs one reference for every component edge.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "path": {"type": "string", "minLength": 1},
                        "start_line": {"type": "integer", "minimum": 1},
                        "end_line": {"type": "integer", "minimum": 1},
                    },
                    "required": ["path", "start_line", "end_line"],
                },
            },
        },
        "required": [
            "kind",
            "path",
            "symbol",
            "target",
            "path_symbols",
            "evidence",
        ],
    },
}


class VerifiableNavigationError(ValueError):
    """Raised when a task fixture or static relation is not exactly decidable."""


@dataclass(frozen=True, slots=True)
class VerifiableTask:
    task_id: str
    kind: TaskKind
    question: str
    path: str
    symbol: str
    endpoint: str = ""
    line: int | None = None
    goal_requirements: tuple[tuple[str, str], ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "VerifiableTask":
        goals = value.get("goal_requirements")
        if not isinstance(goals, list):
            raise VerifiableNavigationError("goal_requirements must be an array")
        parsed_goals: list[tuple[str, str]] = []
        for goal in goals:
            if not isinstance(goal, Mapping):
                raise VerifiableNavigationError("goal requirement must be an object")
            goal_id = str(goal.get("goal_id") or "").strip()
            requirement = str(goal.get("requirement") or "").strip()
            if not goal_id or not requirement:
                raise VerifiableNavigationError("goal requirement needs goal_id and requirement")
            parsed_goals.append((goal_id, requirement))
        raw_line = value.get("line")
        return cls(
            task_id=str(value.get("task_id") or "").strip(),
            kind=str(value.get("kind") or "").strip(),  # type: ignore[arg-type]
            question=str(value.get("question") or "").strip(),
            path=str(value.get("path") or "").strip(),
            symbol=str(value.get("symbol") or "").strip(),
            endpoint=str(value.get("endpoint") or "").strip(),
            line=(
                int(raw_line)
                if isinstance(raw_line, int) and not isinstance(raw_line, bool)
                else None
            ),
            goal_requirements=tuple(parsed_goals),
        )

    def validate(self) -> None:
        if not self.task_id or not self.question or not self.path or not self.symbol:
            raise VerifiableNavigationError("task_id, question, path, and symbol are required")
        if not self.goal_requirements:
            raise VerifiableNavigationError("task requires at least one user-visible goal")
        if self.kind not in {
            "definition",
            "direct_callers",
            "call_path",
            "mutation_target",
        }:
            raise VerifiableNavigationError(f"unsupported task kind: {self.kind}")
        if self.kind == "call_path" and not self.endpoint:
            raise VerifiableNavigationError("call_path requires endpoint")
        if self.kind == "mutation_target" and (self.line is None or self.line < 1):
            raise VerifiableNavigationError("mutation_target requires a positive line")
        if len({goal_id for goal_id, _ in self.goal_requirements}) != len(self.goal_requirements):
            raise VerifiableNavigationError("goal ids must be unique")


@dataclass(frozen=True, slots=True)
class RelationClaim:
    kind: ClaimKind
    path: str
    symbol: str
    target: str = ""
    path_symbols: tuple[str, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RelationClaim":
        raw_path = value.get("path_symbols")
        raw_evidence = value.get("evidence")
        return cls(
            kind=str(value.get("kind") or "").strip(),  # type: ignore[arg-type]
            path=str(value.get("path") or "").strip(),
            symbol=str(value.get("symbol") or "").strip(),
            target=str(value.get("target") or "").strip(),
            path_symbols=tuple(
                str(item).strip() for item in raw_path if isinstance(item, str) and item.strip()
            )
            if isinstance(raw_path, list)
            else (),
            evidence=tuple(
                EvidenceRef.from_mapping(item) for item in raw_evidence if isinstance(item, Mapping)
            )
            if isinstance(raw_evidence, list)
            else (),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "path": self.path,
            "symbol": self.symbol,
            "target": self.target,
            "path_symbols": list(self.path_symbols),
            "evidence": [
                {
                    "path": ref.path,
                    "start_line": ref.start_line,
                    "end_line": ref.end_line,
                }
                for ref in self.evidence
            ],
        }


def relation_claims_shape_error(value: object) -> str | None:
    if not isinstance(value, list):
        return "relation_claims must be an array"
    for index, raw in enumerate(value, start=1):
        if not isinstance(raw, Mapping):
            return f"relation claim {index} must be an object"
        try:
            claim = RelationClaim.from_mapping(raw)
        except (TypeError, ValueError):
            return f"relation claim {index} is malformed"
        if claim.kind not in {
            "definition",
            "call_edge",
            "call_path",
            "mutation_target",
        }:
            return f"relation claim {index} has invalid kind"
        if not claim.path or not claim.symbol or not claim.evidence:
            return f"relation claim {index} requires path, symbol, and evidence"
        if any(
            ref.path != claim.path or ref.start_line < 1 or ref.end_line < ref.start_line
            for ref in claim.evidence
        ):
            return f"relation claim {index} has invalid evidence"
        if claim.kind in {"call_edge", "mutation_target"} and not claim.target:
            return f"relation claim {index} requires target"
        if claim.kind == "call_path":
            if (
                not claim.target
                or len(claim.path_symbols) < 2
                or claim.path_symbols[0] != claim.symbol
                or claim.path_symbols[-1] != claim.target
            ):
                return f"relation claim {index} has invalid path_symbols"
        elif claim.path_symbols:
            return f"relation claim {index} cannot include path_symbols"
    return None


@dataclass(frozen=True, slots=True)
class StaticRelation:
    kind: ClaimKind
    path: str
    symbol: str
    target: str = ""
    path_symbols: tuple[str, ...] = ()
    start_line: int = 0
    end_line: int = 0
    required_lines: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class VerifiableScore:
    relation_correct: bool
    evidence_complete: bool
    evidence_precise: bool
    exact_correct: bool
    expected: tuple[StaticRelation, ...]
    matched: tuple[StaticRelation, ...]
    unsupported_claims: tuple[dict[str, Any], ...]
    incomplete_evidence_claims: tuple[dict[str, Any], ...]
    normalized_claims: tuple[dict[str, Any], ...]
    imprecise_claims: tuple[dict[str, Any], ...]
    errors: tuple[str, ...]

    @property
    def correct(self) -> bool:
        """Backward-compatible alias for the strict exact-pass result."""

        return self.exact_correct


@dataclass(frozen=True, slots=True)
class TaskDifficulty:
    hop_count: int
    answer_file_count: int
    candidate_file_count: int
    decoy_count: int
    tier: Literal["local", "intermediate", "exploratory"]

    def as_dict(self) -> dict[str, Any]:
        return {
            "hop_count": self.hop_count,
            "answer_file_count": self.answer_file_count,
            "candidate_file_count": self.candidate_file_count,
            "decoy_count": self.decoy_count,
            "tier": self.tier,
        }


@dataclass(frozen=True, slots=True)
class _Definition:
    path: str
    symbol: str
    start_line: int
    end_line: int
    node: ast.AST


@dataclass(frozen=True, slots=True)
class _Call:
    path: str
    caller: str
    target_text: str
    resolved_target: str
    line: int


class PythonRelationOracle:
    """Conservative static oracle for pinned Python fixtures.

    Only lexically resolvable calls are accepted. Imports, aliases, inheritance,
    decorators, and dynamic dispatch are intentionally outside the v1 oracle.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve(strict=True)
        self.definitions: dict[str, _Definition] = {}
        self.calls: list[_Call] = []
        self._index()

    def _index(self) -> None:
        for path in sorted(self.root.rglob("*.py")):
            relative = path.relative_to(self.root).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)) and any(
                    alias.asname for alias in node.names
                ):
                    raise VerifiableNavigationError(
                        f"import alias is outside the v1 oracle: {relative}:{node.lineno}"
                    )
                if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(
                    node.value, (ast.Name, ast.Attribute)
                ):
                    raise VerifiableNavigationError(
                        f"assignment alias is outside the v1 oracle: {relative}:{node.lineno}"
                    )
            module = ".".join(Path(relative).with_suffix("").parts)
            self._visit_definitions(tree, relative, module, ())

    def _visit_definitions(
        self,
        node: ast.AST,
        path: str,
        module: str,
        parents: tuple[str, ...],
    ) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                local = (*parents, child.name)
                symbol = ".".join((module, *local))
                if symbol in self.definitions:
                    raise VerifiableNavigationError(f"duplicate symbol: {symbol}")
                definition = _Definition(
                    path=path,
                    symbol=symbol,
                    start_line=int(child.lineno),
                    end_line=int(child.end_lineno or child.lineno),
                    node=child,
                )
                self.definitions[symbol] = definition
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self._collect_calls(definition, module, parents)
                self._visit_definitions(child, path, module, local)
            else:
                self._visit_definitions(child, path, module, parents)

    def _collect_calls(
        self,
        definition: _Definition,
        module: str,
        class_parents: tuple[str, ...],
    ) -> None:
        calls: list[ast.Call] = []

        class CallVisitor(ast.NodeVisitor):
            def visit_Call(self, node: ast.Call) -> None:
                calls.append(node)
                self.generic_visit(node)

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                if node is definition.node:
                    self.generic_visit(node)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                if node is definition.node:
                    self.generic_visit(node)

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                return None

        CallVisitor().visit(definition.node)
        for node in calls:
            target = _dotted_name(node.func)
            if target is None:
                raise VerifiableNavigationError(
                    f"dynamic call in {definition.symbol}:{node.lineno}"
                )
            resolved = self._resolve_call_text(target, module=module, class_parents=class_parents)
            self.calls.append(
                _Call(
                    path=definition.path,
                    caller=definition.symbol,
                    target_text=target,
                    resolved_target=resolved,
                    line=int(node.lineno),
                )
            )

    @staticmethod
    def _resolve_call_text(
        target: str,
        *,
        module: str,
        class_parents: tuple[str, ...],
    ) -> str:
        parts = target.split(".")
        if parts[0] in {"self", "cls"} and class_parents and len(parts) == 2:
            return ".".join((module, *class_parents, *parts[1:]))
        if len(parts) == 1:
            return f"{module}.{target}"
        if parts[0][:1].isupper():
            return target
        return ""

    def definition(self, *, path: str, symbol: str) -> StaticRelation:
        definition = self._unique_symbol(path=path, symbol=symbol)
        return StaticRelation(
            kind="definition",
            path=definition.path,
            symbol=definition.symbol,
            start_line=definition.start_line,
            end_line=definition.end_line,
            required_lines=(definition.start_line,),
        )

    def direct_callers(self, *, path: str, symbol: str) -> tuple[StaticRelation, ...]:
        callee = self._unique_symbol(path=path, symbol=symbol).symbol
        relations = [
            StaticRelation(
                kind="call_edge",
                path=call.path,
                symbol=call.caller,
                target=callee,
                start_line=call.line,
                end_line=call.line,
                required_lines=(call.line,),
            )
            for call in self.calls
            if self._call_matches(call.resolved_target, callee)
        ]
        return tuple(sorted(relations, key=_relation_key))

    def unique_call_path(
        self,
        *,
        path: str,
        symbol: str,
        endpoint: str,
    ) -> StaticRelation:
        start = self._unique_symbol(path=path, symbol=symbol).symbol
        end = self._unique_symbol(path=path, symbol=endpoint).symbol
        adjacency: dict[str, set[str]] = defaultdict(set)
        for call in self.calls:
            matches = [
                candidate
                for candidate in self.definitions
                if self._call_matches(call.resolved_target, candidate)
            ]
            if len(matches) == 1:
                adjacency[call.caller].add(matches[0])
        paths: list[tuple[str, ...]] = []

        def walk(current: str, route: tuple[str, ...]) -> None:
            if current == end:
                paths.append(route)
                return
            for target in sorted(adjacency.get(current, ())):
                if target not in route:
                    walk(target, (*route, target))

        walk(start, (start,))
        if len(paths) != 1:
            raise VerifiableNavigationError(f"call path must be unique; found {len(paths)} paths")
        lines = [
            call.line
            for left, right in zip(paths[0], paths[0][1:])
            for call in self.calls
            if call.caller == left and self._call_matches(call.resolved_target, right)
        ]
        return StaticRelation(
            kind="call_path",
            path=path,
            symbol=start,
            target=end,
            path_symbols=paths[0],
            start_line=min(lines),
            end_line=max(lines),
            required_lines=tuple(sorted(set(lines))),
        )

    def mutation_target(
        self,
        *,
        path: str,
        symbol: str,
        line: int,
    ) -> StaticRelation:
        enclosing = self._unique_symbol(path=path, symbol=symbol)
        matches = [
            call
            for call in self.calls
            if call.path == enclosing.path and call.caller == enclosing.symbol and call.line == line
        ]
        if len(matches) != 1:
            raise VerifiableNavigationError(
                f"mutation site must contain exactly one call; found {len(matches)}"
            )
        return StaticRelation(
            kind="mutation_target",
            path=enclosing.path,
            symbol=enclosing.symbol,
            target=matches[0].target_text,
            start_line=line,
            end_line=line,
            required_lines=(line,),
        )

    def expected(self, task: VerifiableTask) -> tuple[StaticRelation, ...]:
        task.validate()
        if task.kind == "definition":
            return (self.definition(path=task.path, symbol=task.symbol),)
        if task.kind == "direct_callers":
            return self.direct_callers(path=task.path, symbol=task.symbol)
        if task.kind == "call_path":
            return (
                self.unique_call_path(
                    path=task.path,
                    symbol=task.symbol,
                    endpoint=task.endpoint,
                ),
            )
        assert task.line is not None
        return (
            self.mutation_target(
                path=task.path,
                symbol=task.symbol,
                line=task.line,
            ),
        )

    def _unique_symbol(self, *, path: str, symbol: str) -> _Definition:
        matches = [
            definition
            for candidate, definition in self.definitions.items()
            if definition.path == path and (candidate == symbol or candidate.endswith(f".{symbol}"))
        ]
        if len(matches) != 1:
            raise VerifiableNavigationError(
                f"symbol must resolve exactly once: {path}:{symbol} ({len(matches)})"
            )
        return matches[0]

    @staticmethod
    def _call_matches(target: str, symbol: str) -> bool:
        return target == symbol or symbol.endswith(f".{target}")


class RelationCanonicalizer:
    """Versioned, deterministic normalization shared by claims and oracle output."""

    version = RELATION_CANONICALIZATION_VERSION

    def __init__(self, oracle: PythonRelationOracle) -> None:
        self._full_to_canonical: dict[str, str] = {}
        canonical_to_full: dict[str, str] = {}
        for full, definition in oracle.definitions.items():
            module = ".".join(Path(definition.path).with_suffix("").parts)
            prefix = f"{module}."
            canonical = full[len(prefix) :] if full.startswith(prefix) else full
            other = canonical_to_full.get(canonical)
            if other is not None and other != full:
                raise VerifiableNavigationError(
                    f"canonical symbol collision: {canonical} ({other}, {full})"
                )
            canonical_to_full[canonical] = full
            self._full_to_canonical[full] = canonical
        self._canonical_symbols = frozenset(canonical_to_full)

    def symbol(self, value: str) -> str:
        text = value.strip()
        if text in self._full_to_canonical:
            return self._full_to_canonical[text]
        if text in self._canonical_symbols:
            return text
        return text

    def callable(self, value: str) -> str:
        text = value.strip()
        try:
            expression = ast.parse(text, mode="eval").body
        except SyntaxError as exc:
            raise VerifiableNavigationError(f"invalid callable expression: {value!r}") from exc
        if isinstance(expression, ast.Call):
            expression = expression.func
        dotted = _dotted_name(expression)
        if dotted is None:
            raise VerifiableNavigationError(
                f"dynamic callable expression is not canonicalizable: {value!r}"
            )
        return self.symbol(dotted)

    def claim(self, claim: RelationClaim) -> RelationClaim:
        target = claim.target
        if claim.kind in {"call_edge", "call_path"}:
            target = self.symbol(target)
        elif claim.kind == "mutation_target":
            target = self.callable(target)
        return RelationClaim(
            kind=claim.kind,
            path=Path(claim.path).as_posix(),
            symbol=self.symbol(claim.symbol),
            target=target,
            path_symbols=tuple(self.symbol(item) for item in claim.path_symbols),
            evidence=tuple(
                EvidenceRef(Path(ref.path).as_posix(), ref.start_line, ref.end_line)
                for ref in claim.evidence
            ),
        )

    def relation(self, relation: StaticRelation) -> StaticRelation:
        target = relation.target
        if relation.kind in {"call_edge", "call_path"}:
            target = self.symbol(target)
        elif relation.kind == "mutation_target":
            target = self.callable(target)
        return StaticRelation(
            kind=relation.kind,
            path=Path(relation.path).as_posix(),
            symbol=self.symbol(relation.symbol),
            target=target,
            path_symbols=tuple(self.symbol(item) for item in relation.path_symbols),
            start_line=relation.start_line,
            end_line=relation.end_line,
            required_lines=relation.required_lines,
        )


def load_verifiable_task_set(
    path: str | Path,
    *,
    source_root: str | Path,
) -> tuple[VerifiableTask, ...]:
    fixture_path = Path(path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != VERIFIABLE_TASK_SCHEMA_VERSION:
        raise VerifiableNavigationError("unsupported task schema version")
    if payload.get("track") != "NAV-VERIFIABLE-00":
        raise VerifiableNavigationError("unexpected task track")
    root = Path(source_root).resolve(strict=True)
    expected_sources = payload.get("sources")
    if not isinstance(expected_sources, Mapping) or not expected_sources:
        raise VerifiableNavigationError("task set requires pinned sources")
    pinned_paths = {str(raw_path) for raw_path in expected_sources}
    discovered_paths = {path.relative_to(root).as_posix() for path in root.rglob("*.py")}
    if pinned_paths != discovered_paths:
        raise VerifiableNavigationError(
            "pinned sources must exactly match the Python fixture snapshot"
        )
    for raw_path, expected_hash in expected_sources.items():
        source = (root / str(raw_path)).resolve(strict=True)
        source.relative_to(root)
        actual = hashlib.sha256(source.read_bytes()).hexdigest()
        if actual != str(expected_hash):
            raise VerifiableNavigationError(f"source hash mismatch for {raw_path}")
    raw_tasks = payload.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise VerifiableNavigationError("task set requires tasks")
    tasks = tuple(
        VerifiableTask.from_mapping(item) for item in raw_tasks if isinstance(item, Mapping)
    )
    if len(tasks) != len(raw_tasks):
        raise VerifiableNavigationError("every task must be an object")
    if len({task.task_id for task in tasks}) != len(tasks):
        raise VerifiableNavigationError("task ids must be unique")
    oracle = PythonRelationOracle(root)
    RelationCanonicalizer(oracle)
    for task in tasks:
        if not oracle.expected(task):
            raise VerifiableNavigationError(f"task {task.task_id} has no exact expected relations")
    return tasks


def score_verifiable_claims(
    task: VerifiableTask,
    claims: Sequence[RelationClaim],
    *,
    oracle: PythonRelationOracle,
    observed_lines: Mapping[str, set[int]],
) -> VerifiableScore:
    canonicalizer = RelationCanonicalizer(oracle)
    expected = tuple(canonicalizer.relation(item) for item in oracle.expected(task))
    expected_by_key = {_relation_key(item): item for item in expected}
    matched: list[StaticRelation] = []
    unsupported: list[dict[str, Any]] = []
    incomplete: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []
    imprecise: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[tuple[Any, ...]] = set()
    for index, raw_claim in enumerate(claims, start=1):
        try:
            claim = canonicalizer.claim(raw_claim)
        except VerifiableNavigationError as exc:
            errors.append(f"claim {index} cannot be canonicalized: {exc}")
            continue
        normalized.append(claim.as_dict())
        relation = StaticRelation(
            kind=claim.kind,
            path=claim.path,
            symbol=claim.symbol,
            target=claim.target,
            path_symbols=claim.path_symbols,
        )
        key = _relation_key(relation)
        expected_relation = expected_by_key.get(key)
        if expected_relation is None:
            unsupported.append(raw_claim.as_dict())
            continue
        if key in seen:
            errors.append(f"claim {index} duplicates a relation")
            continue
        seen.add(key)
        matched.append(expected_relation)

        lines: set[int] = set()
        refs_valid = bool(claim.evidence)
        for ref in claim.evidence:
            referenced = set(range(ref.start_line, ref.end_line + 1))
            if ref.path != claim.path or not referenced.issubset(
                observed_lines.get(ref.path, set())
            ):
                refs_valid = False
            lines.update(referenced)
        if not claim.evidence:
            errors.append(f"claim {index} has no evidence")
        elif not refs_valid:
            errors.append(f"claim {index} references unobserved evidence")
        missing_lines = sorted(set(expected_relation.required_lines) - lines)
        if missing_lines or not refs_valid:
            incomplete.append(
                {
                    "claim": raw_claim.as_dict(),
                    "missing_lines": missing_lines,
                }
            )
            continue
        extra_lines = sorted(lines - set(expected_relation.required_lines))
        if extra_lines:
            imprecise.append(
                {
                    "claim": raw_claim.as_dict(),
                    "extra_lines": extra_lines,
                }
            )
    relation_correct = set(seen) == set(expected_by_key) and not unsupported
    evidence_complete = relation_correct and not incomplete
    evidence_precise = evidence_complete and not imprecise
    exact_correct = relation_correct and evidence_complete and evidence_precise and not errors
    return VerifiableScore(
        relation_correct=relation_correct,
        evidence_complete=evidence_complete,
        evidence_precise=evidence_precise,
        exact_correct=exact_correct,
        expected=expected,
        matched=tuple(sorted(matched, key=_relation_key)),
        unsupported_claims=tuple(unsupported),
        incomplete_evidence_claims=tuple(incomplete),
        normalized_claims=tuple(normalized),
        imprecise_claims=tuple(imprecise),
        errors=tuple(errors),
    )


def classify_task_difficulty(
    task: VerifiableTask,
    *,
    oracle: PythonRelationOracle,
) -> TaskDifficulty:
    """Classify a task from source structure only, before any model run."""

    expected = oracle.expected(task)
    answer_symbols: set[str] = set()
    answer_files = {relation.path for relation in expected}
    expected_calls: set[tuple[str, int]] = set()
    hop_count = 0
    for relation in expected:
        answer_symbols.add(relation.symbol)
        if relation.target:
            answer_symbols.add(relation.target)
        answer_symbols.update(relation.path_symbols)
        if relation.kind in {"call_edge", "mutation_target"}:
            hop_count = max(hop_count, 1)
            expected_calls.add((relation.path, relation.start_line))
        elif relation.kind == "call_path":
            hop_count = max(hop_count, len(relation.path_symbols) - 1)
            for line in relation.required_lines:
                expected_calls.add((relation.path, line))
    for symbol in answer_symbols:
        definition = oracle.definitions.get(symbol)
        if definition is not None:
            answer_files.add(definition.path)

    terminals = {task.symbol.rsplit(".", 1)[-1]}
    if task.endpoint:
        terminals.add(task.endpoint.rsplit(".", 1)[-1])
    candidate_files = 0
    for path in sorted(oracle.root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if any(re.search(rf"\b{re.escape(term)}\b", text) for term in terminals):
            candidate_files += 1

    decoys = 0
    for symbol in oracle.definitions:
        if symbol.rsplit(".", 1)[-1] in terminals and symbol not in answer_symbols:
            decoys += 1
    for call in oracle.calls:
        if (
            call.target_text.rsplit(".", 1)[-1] in terminals
            and (call.path, call.line) not in expected_calls
        ):
            decoys += 1

    exploratory_signals = sum(
        (
            candidate_files >= 5,
            hop_count >= 3,
            decoys >= 4,
            len(answer_files) >= 3,
        )
    )
    if candidate_files == 1 and hop_count <= 1 and decoys == 0:
        tier: Literal["local", "intermediate", "exploratory"] = "local"
    elif exploratory_signals >= 2:
        tier = "exploratory"
    else:
        tier = "intermediate"
    return TaskDifficulty(
        hop_count=hop_count,
        answer_file_count=len(answer_files),
        candidate_file_count=candidate_files,
        decoy_count=decoys,
        tier=tier,
    )


def build_task_admission_manifest(
    tasks: Sequence[VerifiableTask],
    *,
    oracle: PythonRelationOracle,
) -> dict[str, Any]:
    """Build the immutable, source-only admission record for candidate tasks."""

    canonicalizer = RelationCanonicalizer(oracle)
    source_hashes = {
        path.relative_to(oracle.root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(oracle.root.rglob("*.py"))
    }
    task_records: list[dict[str, Any]] = []
    for task in tasks:
        expected = tuple(canonicalizer.relation(item) for item in oracle.expected(task))
        if not expected:
            raise VerifiableNavigationError(f"task {task.task_id} has no exact expected relations")
        task_records.append(
            {
                "task_id": task.task_id,
                "kind": task.kind,
                "oracle_resolvable": True,
                "canonical_symbols_unique": True,
                "difficulty": classify_task_difficulty(task, oracle=oracle).as_dict(),
                "expected_relations": [_static_relation_dict(item) for item in expected],
            }
        )
    manifest: dict[str, Any] = {
        "schema_version": VERIFIABLE_ADMISSION_SCHEMA_VERSION,
        "track": "NAV-VERIFIABLE-00",
        "difficulty_policy": {
            "local": {
                "candidate_file_count": 1,
                "max_hop_count": 1,
                "decoy_count": 0,
            },
            "exploratory": {
                "minimum_satisfied_signals": 2,
                "signals": {
                    "candidate_file_count_gte": 5,
                    "hop_count_gte": 3,
                    "decoy_count_gte": 4,
                    "answer_file_count_gte": 3,
                },
            },
            "intermediate": "all admitted tasks not classified local or exploratory",
        },
        "source_hashes": source_hashes,
        "tasks": task_records,
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest["admission_manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
    return manifest


def build_pair_manifest(
    *,
    pair_id: str,
    task: VerifiableTask,
    autonomous_config: Mapping[str, Any],
    structured_config: Mapping[str, Any],
    run_order: Sequence[str],
) -> dict[str, Any]:
    if tuple(run_order) not in {
        ("autonomous", "structured"),
        ("structured", "autonomous"),
    }:
        raise VerifiableNavigationError(
            "run_order must contain autonomous and structured exactly once"
        )
    ignored = {"structured_navigation", "output_dir", "run_label"}
    left = {key: value for key, value in autonomous_config.items() if key not in ignored}
    right = {key: value for key, value in structured_config.items() if key not in ignored}
    if left != right:
        raise VerifiableNavigationError(
            "paired runs must share model, task, seed, budget, and decoding configuration"
        )
    if autonomous_config.get("structured_navigation") not in {False, None}:
        raise VerifiableNavigationError("autonomous run cannot enable the ledger")
    if structured_config.get("structured_navigation") is not True:
        raise VerifiableNavigationError("structured run must enable the ledger")
    return {
        "schema_version": VERIFIABLE_PAIR_SCHEMA_VERSION,
        "track": "NAV-VERIFIABLE-00",
        "pair_id": pair_id,
        "task_id": task.task_id,
        "run_order": list(run_order),
        "shared_config": left,
        "runs": {
            "autonomous": dict(autonomous_config),
            "structured": dict(structured_config),
        },
    }


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None


def _relation_key(relation: StaticRelation) -> tuple[Any, ...]:
    return (
        relation.kind,
        relation.path,
        relation.symbol,
        relation.target,
        relation.path_symbols,
    )


def _static_relation_dict(relation: StaticRelation) -> dict[str, Any]:
    return {
        "kind": relation.kind,
        "path": relation.path,
        "symbol": relation.symbol,
        "target": relation.target,
        "path_symbols": list(relation.path_symbols),
        "required_lines": list(relation.required_lines),
    }
