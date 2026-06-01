from __future__ import annotations

from copy import deepcopy
from typing import Any


def inline_local_json_schema_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *schema* with local ``$defs``/``$ref`` entries inlined."""
    copied = deepcopy(schema)
    definitions = copied.get("$defs") or copied.get("definitions") or {}
    resolved = _resolve_node(copied, definitions, stack=())
    if isinstance(resolved, dict):
        resolved.pop("$defs", None)
        resolved.pop("definitions", None)
    return resolved


def _resolve_node(node: Any, definitions: dict[str, Any], stack: tuple[str, ...]) -> Any:
    if isinstance(node, list):
        return [_resolve_node(item, definitions, stack) for item in node]
    if not isinstance(node, dict):
        return node

    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        return _resolve_ref_node(node, ref.removeprefix("#/$defs/"), definitions, stack)
    if isinstance(ref, str) and ref.startswith("#/definitions/"):
        return _resolve_ref_node(node, ref.removeprefix("#/definitions/"), definitions, stack)

    return {
        key: _resolve_node(value, definitions, stack)
        for key, value in node.items()
        if key not in {"$defs", "definitions"}
    }


def _resolve_ref_node(
    node: dict[str, Any],
    key: str,
    definitions: dict[str, Any],
    stack: tuple[str, ...],
) -> dict[str, Any]:
    resolved = _resolve_ref(key, definitions, stack)
    siblings = {name: value for name, value in node.items() if name != "$ref"}
    if siblings:
        resolved.update(_resolve_node(siblings, definitions, stack))
    return resolved


def _resolve_ref(key: str, definitions: dict[str, Any], stack: tuple[str, ...]) -> dict[str, Any]:
    if key in stack:
        raise ValueError(f"recursive JSON schema reference is not supported: {key}")
    if key not in definitions:
        raise ValueError(f"JSON schema reference not found: {key}")
    resolved = _resolve_node(definitions[key], definitions, (*stack, key))
    if not isinstance(resolved, dict):
        raise ValueError(f"JSON schema reference did not resolve to an object: {key}")
    return resolved
