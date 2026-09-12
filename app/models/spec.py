"""
Model specification and status types.

Pure data — no runtime, no IO, no inference imports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class ModelStatus(Enum):
    """Lifecycle status of a registered model."""
    NOT_INSTALLED = auto()   # Spec known, files not on disk
    INSTALLED     = auto()   # Files present on disk, not loaded into memory
    LOADED        = auto()   # Loaded into GPU/CPU memory and ready
    ERROR         = auto()   # Last load/validate attempt failed


@dataclass
class ModelSpec:
    """Describes a single image-generation model known to NOVA.

    Specs live in the registry; they describe *what* a model is.
    The runtime layer knows *how* to run it.
    """

    # Stable identifier used as the directory name under models_dir
    model_id: str

    display_name: str
    description: str

    # Where to get the weights — HuggingFace repo ID or local path
    source: str

    # Which runtime adapter handles this model (matches RuntimeAdapter.runtime_name())
    runtime: str

    # License string for UI display and compliance tracking
    license: str

    # Approximate minimum VRAM in GB at default precision
    min_vram_gb: float

    # Hardware recommendations and metadata
    recommended_vram_gb: float = 0.0
    model_size_gb: float = 0.0
    precision: str = ""
    capabilities: list[str] = field(default_factory=list)
    supported_vendors: list[str] = field(default_factory=list)

    # Recommended default dimensions for this model
    default_width: int = 1024
    default_height: int = 1024

    # Recommended step range (min, default, max)
    steps_min: int = 1
    steps_default: int = 4
    steps_max: int = 50

    # Recommended guidance range
    guidance_default: float = 0.0

    # Arbitrary tags for future filtering ("text-to-image", "inpainting", etc.)
    tags: list[str] = field(default_factory=list)

    # Current lifecycle status — mutable, set by registry/runtime
    status: ModelStatus = ModelStatus.NOT_INSTALLED

    # Human-readable error message when status == ERROR
    error_message: Optional[str] = None

    def validate(self) -> list[str]:
        """Return a list of validation errors (empty = valid spec)."""
        errors: list[str] = []
        if not self.model_id.strip():
            errors.append("model_id must not be empty.")
        if not self.display_name.strip():
            errors.append("display_name must not be empty.")
        if not self.source.strip():
            errors.append("source must not be empty.")
        if not self.runtime.strip():
            errors.append("runtime must not be empty.")
        if self.min_vram_gb < 0:
            errors.append("min_vram_gb must be non-negative.")
        if self.recommended_vram_gb < 0:
            errors.append("recommended_vram_gb must be non-negative.")
        if self.recommended_vram_gb > 0 and self.recommended_vram_gb < self.min_vram_gb:
            errors.append("recommended_vram_gb cannot be less than min_vram_gb.")
        if self.model_size_gb < 0:
            errors.append("model_size_gb must be non-negative.")
        if self.default_width <= 0 or self.default_width % 8 != 0:
            errors.append(f"default_width must be a positive multiple of 8 (got {self.default_width}).")
        if self.default_height <= 0 or self.default_height % 8 != 0:
            errors.append(f"default_height must be a positive multiple of 8 (got {self.default_height}).")
        if not (0 < self.steps_min <= self.steps_default <= self.steps_max):
            errors.append("steps_min <= steps_default <= steps_max must hold.")
        return errors
