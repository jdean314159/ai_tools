"""Language Tutor reference application.

This package serves two roles:
- a runnable language-learning application
- an integration/test vehicle for the ai_tools libraries

The import surface is kept lazy so the package itself is importable even when
optional runtime dependencies for the full tutoring stack are not installed yet.
"""

from importlib import import_module
from typing import Any

__all__ = [
    "describe_language_tutor",
    "TutorSession",
    "TutorResponse",
    "SessionState",
    "EngineManager",
    "CostTracker",
    "LanguageProfile",
    "get_language_profile",
    "STRATEGIES",
]

_LAZY_EXPORTS = {
    "describe_language_tutor": ("language_tutor.interop", "describe_language_tutor"),
    "TutorSession": ("language_tutor.tutor_session", "TutorSession"),
    "TutorResponse": ("language_tutor.tutor_session", "TutorResponse"),
    "SessionState": ("language_tutor.tutor_session", "SessionState"),
    "EngineManager": ("language_tutor.engine_manager", "EngineManager"),
    "CostTracker": ("language_tutor.engine_manager", "CostTracker"),
    "LanguageProfile": ("language_tutor.config", "LanguageProfile"),
    "get_language_profile": ("language_tutor.config", "get_language_profile"),
    "STRATEGIES": ("language_tutor.hardware_strategy", "STRATEGIES"),
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_EXPORTS:
        module_name, attr_name = _LAZY_EXPORTS[name]
        module = import_module(module_name)
        value = getattr(module, attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module 'language_tutor' has no attribute {name!r}")
