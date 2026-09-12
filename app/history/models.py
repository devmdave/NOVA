"""
Data models for NOVA's history and local generation storage.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict


@dataclass
class GenerationRecord:
    """Persistent metadata record for a single successful generation."""

    id: str
    image_path: str
    thumbnail_path: str
    prompt: str
    negative_prompt: str = ""
    width: int = 1024
    height: int = 1024
    steps: int = 20
    guidance: float = 7.5
    seed: int = -1
    model: str = "flux-schnell"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    mode: str = "text-to-image"
    denoising_strength: float = 0.5
    duration_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to a JSON-serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GenerationRecord:
        """Construct a GenerationRecord from a dictionary safely handling extra or missing keys."""
        valid_keys = {
            "id", "image_path", "thumbnail_path", "prompt", "negative_prompt",
            "width", "height", "steps", "guidance", "seed", "model",
            "timestamp", "mode", "denoising_strength", "duration_seconds", "metadata"
        }
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)
