"""
llm_engines.contracts

Canonical interfaces for the AI Toolkit.
All implementations must conform to these contracts.
No contract is frozen until its governing ADR is accepted.

Import as:  from llm_engines.contracts import ChatModel, GenerationRequest, ...
"""
from .engine import (
    # Exceptions
    LLMEngineError,
    BackendUnavailableError,
    ModelNotFoundError,
    ContextLengthExceededError,
    RateLimitError,
    GenerationError,
    EngineConfigError,
    # Compression
    CompressionStrategy,
    # Logprobs
    TokenLogprob,
    LogprobResult,
    # Capability / optimization
    EngineCapabilities,
    InferenceOptimizationRequest,
    ActiveInferenceOptimization,
    # Message / request / response
    FinishReason,
    UsageStats,
    ToolCall,
    ChatMessage,
    GenerationRequest,
    GenerationResponse,
    # Embedding
    EmbeddingRequest,
    EmbeddingResponse,
    # Protocols
    ChatModel,
    ToolCallingModel,
    EmbeddingModel,
    StreamingModel,
    AsyncStreamingModel,
    BatchChatModel,
    LogprobModel,
)
from .tools import (
    ToolParameterSchema,
    ToolSpec,
    ToolInvocation,
    ToolStatus,
    ToolResult,
)
from .discovery import (
    GPU,
    HardwareProfile,
    TaskType,
    ModelInfo,
    ModelRegistry,
    detect_hardware,
)

from .resources import (
    EngineFitRequest,
    EngineFitEstimate,
    EngineLaunchRecommendation,
    RolePlacementPlan,
)

from .rag import (
    Chunk,
    RAGResult,
    RAGPipeline,
)
from .registry import (
    EngineDescriptor,
    EngineParameter,
    EngineConfigSchema,
    ModelDescriptor,
    ProvisionRequest,
    ProvisionResult,
    EngineInvocationRequest,
    EngineInvocationResult,
    EngineHandle,
    EngineRegistry,
)

__all__ = [
    # Exceptions
    "LLMEngineError",
    "BackendUnavailableError",
    "ModelNotFoundError",
    "ContextLengthExceededError",
    "RateLimitError",
    "GenerationError",
    "EngineConfigError",
    # Capability / optimization
    "EngineCapabilities",
    "InferenceOptimizationRequest",
    "ActiveInferenceOptimization",
    # Messaging
    "FinishReason",
    "UsageStats",
    "ToolCall",
    "ChatMessage",
    "GenerationRequest",
    "GenerationResponse",
    # Embedding
    "EmbeddingRequest",
    "EmbeddingResponse",
    # Protocols
    "ChatModel",
    "ToolCallingModel",
    "EmbeddingModel",
    "StreamingModel",
    "AsyncStreamingModel",
    "BatchChatModel",
    "LogprobModel",
    # Logprobs / compression
    "CompressionStrategy",
    "TokenLogprob",
    "LogprobResult",
    # Tools
    "ToolParameterSchema",
    "ToolSpec",
    "ToolInvocation",
    "ToolStatus",
    "ToolResult",
    # Discovery
    "GPU",
    "HardwareProfile",
    "TaskType",
    "ModelInfo",
    "ModelRegistry",
    "detect_hardware",
    # Resource advisory
    "EngineFitRequest",
    "EngineFitEstimate",
    "EngineLaunchRecommendation",
    "RolePlacementPlan",
    # RAG
    "Chunk",
    "RAGResult",
    "RAGPipeline",
    # Registry
    "EngineDescriptor",
    "EngineParameter",
    "EngineConfigSchema",
    "ModelDescriptor",
    "ProvisionRequest",
    "ProvisionResult",
    "EngineInvocationRequest",
    "EngineInvocationResult",
    "EngineHandle",
    "EngineRegistry",
]
