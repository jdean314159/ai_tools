"""Vendored or reference subtrees that hygiene gates do not police.

These directories contain externally authored code imported for reference, not
ai_tools source. They are exempt from ai_tools documentation and hygiene
standards.

IN SCOPE, NOT EXEMPT: any new capability built on the ai_tools libraries, even
if it is an agent app modeled on a vendored template here. The exemption is by
literal path prefix, not by category.
"""
from __future__ import annotations


# (prefix, reason). Prefixes match repo-root-relative POSIX paths.
VENDORED_PREFIXES: tuple[tuple[str, str], ...] = (
    (
        "asc/",
        "Externally authored reference app (Tom's ASC); template for a future "
        "ai_tools-based equivalent. Not ai_tools source. Re-include only if "
        "asc/ is adopted as a maintained ai_tools package.",
    ),
)


def is_vendored(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return any(normalized.startswith(prefix) for prefix, _reason in VENDORED_PREFIXES)
