from __future__ import annotations


class SandboxError(Exception):
    """Base exception for read-only sandbox failures."""


class RuntimeNotFoundError(SandboxError):
    """The configured container runtime binary is not available."""


class ImageNotAvailableError(SandboxError):
    """The configured container image is not available locally."""


class MountError(SandboxError):
    """A configured mount is missing or invalid."""


class InterpreterError(Exception):
    """Base exception for log interpretation failures."""


class RemoteEngineRefused(InterpreterError):
    """A remote engine was provided while local-only interpretation is required."""


class InterpretationParseError(InterpreterError):
    """The engine response could not be parsed as an interpretation."""


class CollectionReadError(Exception):
    """Collected logs could not be read from the staged source."""
