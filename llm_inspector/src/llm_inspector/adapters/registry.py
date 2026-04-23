from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from llm_inspector.protocols import ContextAugmenter


@dataclass(frozen=True)
class AdapterSpec:
    name: str
    factory_path: str  # e.g. "llm_inspector.adapters.baseline:make_baseline"


class AdapterRegistry:
    def __init__(self) -> None:
        self._specs: Dict[str, AdapterSpec] = {}

    def register(self, spec: AdapterSpec) -> None:
        self._specs[spec.name] = spec

    def available(self) -> list[str]:
        return sorted(self._specs.keys())

    def create(self, name: str, **kwargs) -> ContextAugmenter:
        if name not in self._specs:
            raise KeyError(f"Unknown adapter: {name}. Available: {', '.join(self.available())}")

        spec = self._specs[name]
        mod_name, _, attr = spec.factory_path.partition(":")
        mod = importlib.import_module(mod_name)
        factory: Callable[..., ContextAugmenter] = getattr(mod, attr)
        return factory(**kwargs)
