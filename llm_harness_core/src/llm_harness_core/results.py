from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class OperationWarning:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OperationError:
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OperationResult(Generic[T]):
    ok: bool
    value: T | None = None
    warnings: tuple[OperationWarning, ...] = ()
    error: OperationError | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(
        cls,
        value: T,
        *,
        warnings: tuple[OperationWarning, ...] = (),
        diagnostics: dict[str, Any] | None = None,
    ) -> "OperationResult[T]":
        return cls(
            ok=True,
            value=value,
            warnings=warnings,
            error=None,
            diagnostics=dict(diagnostics or {}),
        )

    @classmethod
    def failure(
        cls,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> "OperationResult[T]":
        return cls(
            ok=False,
            value=None,
            warnings=(),
            error=OperationError(
                code=code,
                message=message,
                retryable=retryable,
                details=dict(details or {}),
            ),
            diagnostics=dict(diagnostics or {}),
        )
