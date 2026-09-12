"""
Typed error hierarchy for the NOVA inference layer.

Keeps error semantics out of generic Exception handling.
"""


class InferenceError(Exception):
    """Base class for all inference-layer errors."""


class ValidationError(InferenceError):
    """Raised when a GenerationRequest fails validation."""

    def __init__(self, messages: list[str]) -> None:
        self.messages = messages
        super().__init__("; ".join(messages))


class BackendUnavailableError(InferenceError):
    """Raised when the inference backend is not ready."""


class GenerationCancelledError(InferenceError):
    """Raised internally when generation is cancelled mid-run."""


class GenerationFailedError(InferenceError):
    """Raised when the backend encounters an unrecoverable error."""
