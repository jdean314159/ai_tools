"""
rag_lib.config

YAML configuration loader. Mirrors the llm_engines config_loader pattern:
  1. Explicit path argument
  2. RAG_LIB_CONFIG env var
  3. ~/.rag_lib/rag_lib.yaml  (auto-created from packaged default)
  4. Packaged default (data/rag_lib.yaml)
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import yaml

from .errors import RagLibError

_PACKAGED_DEFAULT = Path(__file__).resolve().parent.parent.parent / "data" / "rag_lib.yaml"


def packaged_config_path() -> Path:
    return _PACKAGED_DEFAULT


def user_config_path() -> Path:
    """Default per-user config path. Override via RAG_LIB_CONFIG env var."""
    return Path("~/.rag_lib/rag_lib.yaml").expanduser()


def ensure_user_config_exists(path: Path | None = None) -> Path:
    """Copy packaged default to user config dir if not already present."""
    target = path or user_config_path()
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(packaged_config_path(), target)
    return target


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load and return the rag_lib config dict.

    Args:
        config_path: Explicit path. If None, falls through env var → user
                     config → packaged default.
    """
    if config_path is not None:
        path = Path(config_path).expanduser()
    else:
        env = os.getenv("RAG_LIB_CONFIG")
        if env:
            path = Path(env).expanduser()
        else:
            path = ensure_user_config_exists()

    if not path.exists():
        path = packaged_config_path()

    if not path.exists():
        raise RagLibError(f"rag_lib config not found: {path}")

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RagLibError(f"Invalid YAML in {path}: {exc}") from exc

    return data or {}


def get(config: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Safely navigate nested config keys.

    Example:
        get(cfg, "chunker", "max_embed_tokens", default=1800)
    """
    node = config
    for key in keys:
        if not isinstance(node, dict):
            return default
        node = node.get(key, default)
        if node is default:
            return default
    return node


def get_doc_type_config(
    config: dict[str, Any],
    doc_type: str,
) -> dict[str, Any]:
    """Return the chunker config for a specific doc_type, falling back to defaults."""
    chunker = config.get("chunker", {})
    doc_types = chunker.get("doc_types", {})
    defaults = chunker.get(
        "defaults",
        {
            "strategy": "fixed_size",
            "chunk_size": 512,
            "chunk_overlap": 50,
        },
    )
    return {**defaults, **doc_types.get(doc_type, {})}
