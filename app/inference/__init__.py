"""
Inference package public re-exports.

Downstream code (UI, core) should import from here rather than from
individual sub-modules to keep coupling to module internals low.
"""
from .engine import InferenceEngine, ProgressCallback
from .errors import (
    BackendUnavailableError,
    GenerationCancelledError,
    GenerationFailedError,
    InferenceError,
    ValidationError,
)
from .models import (
    GenerationProgress,
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
)
from .service import InferenceService

__all__ = [
    # Engine contract
    "InferenceEngine",
    "ProgressCallback",
    # Service
    "InferenceService",
    # Data models
    "GenerationRequest",
    "GenerationResult",
    "GenerationProgress",
    "GenerationStatus",
    # Errors
    "InferenceError",
    "ValidationError",
    "BackendUnavailableError",
    "GenerationCancelledError",
    "GenerationFailedError",
]
