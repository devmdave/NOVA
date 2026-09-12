"""
Strongly-typed data models for the NOVA inference layer.

These are pure data classes with no UI or backend dependencies.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class GenerationStatus(Enum):
    """Lifecycle states of a generation job."""
    IDLE = auto()
    GENERATING = auto()
    COMPLETED = auto()
    CANCELLED = auto()
    ERROR = auto()


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

@dataclass
class GenerationRequest:
    """All parameters needed to perform one image-generation run."""

    prompt: str
    negative_prompt: str = ""

    # Dimensions — must be positive multiples of 8
    width: int = 1024
    height: int = 1024

    # Sampling
    steps: int = 20
    guidance: float = 7.5
    seed: int = -1          # -1 means "choose randomly at generation time"

    def resolve_seed(self) -> int:
        """Return the seed to use; generates a random one when seed == -1."""
        if self.seed == -1:
            return random.randint(0, 2 ** 32 - 1)
        return self.seed

    def validate(self) -> list[str]:
        """Return a list of human-readable validation errors (empty = valid)."""
        errors: list[str] = []
        if not self.prompt.strip():
            errors.append("Prompt must not be empty.")
        if self.width <= 0 or self.width % 8 != 0:
            errors.append(f"Width must be a positive multiple of 8 (got {self.width}).")
        if self.height <= 0 or self.height % 8 != 0:
            errors.append(f"Height must be a positive multiple of 8 (got {self.height}).")
        if not (1 <= self.steps <= 200):
            errors.append(f"Steps must be between 1 and 200 (got {self.steps}).")
        if not (0.0 <= self.guidance <= 30.0):
            errors.append(f"Guidance must be between 0.0 and 30.0 (got {self.guidance}).")
        return errors


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------

@dataclass
class GenerationProgress:
    """Snapshot of progress during an active generation job."""

    status: GenerationStatus
    step: int = 0
    total_steps: int = 0
    message: str = ""

    @property
    def fraction(self) -> float:
        """Progress as a value in [0.0, 1.0]. Returns 0 when steps unknown."""
        if self.total_steps <= 0:
            return 0.0
        return min(self.step / self.total_steps, 1.0)


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class GenerationResult:
    """Output of a completed (or failed/cancelled) generation job."""

    request: GenerationRequest

    # Image payload — backends use whichever is appropriate
    image_data: Optional[bytes] = None   # raw PNG/JPEG bytes (in-memory)
    image_path: Optional[str] = None     # path to file on disk

    # Metadata
    seed_used: int = -1
    duration_seconds: float = 0.0
    metadata: dict = field(default_factory=dict)

    # Status
    status: GenerationStatus = GenerationStatus.COMPLETED
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.status == GenerationStatus.COMPLETED

    @property
    def cancelled(self) -> bool:
        return self.status == GenerationStatus.CANCELLED
