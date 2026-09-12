"""
ModelRuntime — abstract base class for runtime adapters.

A runtime adapter knows how to load a specific model format into memory
and hand off a loaded pipeline to an InferenceEngine implementation.

Dependency direction:
    RuntimeAdapter → has no UI imports
    RuntimeAdapter → may import heavyweight libs (torch, diffusers) lazily
    InferenceEngine ← wraps a loaded RuntimeAdapter
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Optional


# Progress callback type for load operations (message, fraction 0.0–1.0)
LoadProgressCallback = Callable[[str, float], None]


class ModelRuntime(ABC):
    """Contract for an adapter that can load/unload a model into memory."""

    @abstractmethod
    def runtime_name(self) -> str:
        """Unique identifier matching ModelSpec.runtime, e.g. 'diffusers_flux'."""

    @abstractmethod
    def load(
        self,
        model_path: Path,
        progress_callback: Optional[LoadProgressCallback] = None,
    ) -> None:
        """Load model weights from disk into memory (GPU or CPU).

        Args:
            model_path: Path to the model directory produced by the store.
            progress_callback: Called with (message, fraction) during load.

        Raises:
            ModelLoadError: if loading fails for any reason.
            RuntimeNotAvailableError: if required packages are absent.
        """

    @abstractmethod
    def unload(self) -> None:
        """Release model from memory.  Safe to call when not loaded."""

    @abstractmethod
    def is_loaded(self) -> bool:
        """True when the model is in memory and ready to run."""
