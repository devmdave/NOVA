"""
InferenceEngine — abstract base class for all local image-generation backends.

A concrete backend (Diffusers, ComfyUI, etc.) must subclass InferenceEngine
and implement the three abstract methods.  The UI never imports a concrete
engine; it always talks to InferenceService which holds the engine reference.
"""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import Callable, Optional

from .models import GenerationProgress, GenerationRequest, GenerationResult


# Convenient type alias used by callers that supply a progress callback.
ProgressCallback = Callable[[GenerationProgress], None]


class InferenceEngine(ABC):
    """Model-agnostic contract for a local image-generation backend.

    Thread-safety contract:
        ``generate()`` is called from a worker thread, never the Qt main thread.
        ``is_available()`` and ``backend_name()`` may be called from any thread.
    """

    @abstractmethod
    def generate(
        self,
        request: GenerationRequest,
        progress_callback: Optional[ProgressCallback] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> GenerationResult:
        """Run image generation synchronously.

        Args:
            request: Validated generation parameters.
            progress_callback: Called after each diffusion step (may be None).
            cancel_event: When set, the engine should abort as soon as possible
                          and return a result with status=CANCELLED.

        Returns:
            GenerationResult describing success, cancellation, or failure.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Return True when the engine is loaded and ready to accept requests."""

    @abstractmethod
    def backend_name(self) -> str:
        """Human-readable identifier, e.g. ``'MockEngine'``, ``'DiffusersFlux'``."""
