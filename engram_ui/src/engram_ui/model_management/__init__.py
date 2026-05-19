"""Model management UI package.

Public API is exactly one function: render_model_management(). All other
symbols are package-internal and split across submodules by concern:

  _shared      — config IO, badges, formatters, resource-profile helpers
  inventory    — read-only views (hardware, running models, registered engines)
  add_models   — action flows (HF search, downloads, local import)
  profiles     — profile editor + page orchestrator

Original 1,702-line module decomposed 2026-05-11.

Author: Jeffrey Dean
"""
from __future__ import annotations

from .profiles import render_model_management

__all__ = ["render_model_management"]
