"""Optional neural memory primitives.

This subpackage is intentionally not imported by :mod:`engram`. Import it
explicitly when constructing the experimental RTRL/TITANS components.
"""

from .core import (
    HAS_TORCH,
    ModernSubgroupedRTRL,
    RTRLConfig,
    TITANSConfig,
    TITANSMemory,
    create_thesis_config,
)
from .coordinator import NeuralMemoryLayer
from .neural_memory import EmbeddingProjector, NeuralMemory, NeuralMemoryConfig
from .surprise_filter import (
    FilterStats,
    SurpriseBaseline,
    SurpriseFilter,
    SurpriseMetrics,
)

__all__ = [
    "EmbeddingProjector",
    "FilterStats",
    "HAS_TORCH",
    "ModernSubgroupedRTRL",
    "NeuralMemory",
    "NeuralMemoryConfig",
    "NeuralMemoryLayer",
    "RTRLConfig",
    "SurpriseBaseline",
    "SurpriseFilter",
    "SurpriseMetrics",
    "TITANSConfig",
    "TITANSMemory",
    "create_thesis_config",
]
