from __future__ import annotations

from llm_inspector.augmenters import BaselineAugmenter


def make_baseline(**kwargs) -> BaselineAugmenter:
    return BaselineAugmenter(**kwargs)
