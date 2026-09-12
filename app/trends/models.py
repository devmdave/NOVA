"""
Data models for NOVA's AI Trends feature.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class Trend:
    """Represents a curated AI image generation trend / prompt template."""

    id: str
    title: str
    description: str
    prompt: str
    negative_prompt: str = ""
    category: str = "General"
    recommended_settings: Dict[str, Any] = field(default_factory=dict)
    source_url: str = ""
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert Trend to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Trend:
        """Construct a Trend safely from dictionary."""
        valid_keys = {
            "id", "title", "description", "prompt", "negative_prompt",
            "category", "recommended_settings", "source_url", "updated_at", "tags"
        }
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)
