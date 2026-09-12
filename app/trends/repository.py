"""
Repository layer for loading and querying AI trend templates.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from app.trends.models import Trend

logger = logging.getLogger("nova.trends.repository")

_DEFAULT_JSON_PATH = Path(__file__).parent / "data" / "default_trends.json"


class TrendsRepository(ABC):
    """Abstract repository for AI trend templates."""

    @abstractmethod
    def get_all(self) -> List[Trend]:
        """Return all available trend templates."""

    @abstractmethod
    def get_by_id(self, trend_id: str) -> Optional[Trend]:
        """Fetch a specific trend by ID."""

    @abstractmethod
    def get_categories(self) -> List[str]:
        """Return a list of unique categories."""

    @abstractmethod
    def search(self, query: str = "", category: str = "All") -> List[Trend]:
        """Search and filter trend templates."""


class LocalTrendsRepository(TrendsRepository):
    """Local JSON-based repository implementation."""

    def __init__(self, custom_data_dir: Optional[str | Path] = None) -> None:
        self.custom_data_dir = Path(custom_data_dir).expanduser().resolve() if custom_data_dir else None
        self._trends_cache: Optional[List[Trend]] = None

    def _load_trends(self) -> List[Trend]:
        """Load trends from built-in JSON file and optional user custom trends file."""
        trend_map: dict[str, Trend] = {}

        # 1. Load built-in default trends
        if _DEFAULT_JSON_PATH.exists():
            try:
                with open(_DEFAULT_JSON_PATH, "r", encoding="utf-8") as f:
                    raw_list = json.load(f)
                    if isinstance(raw_list, list):
                        for item in raw_list:
                            if isinstance(item, dict):
                                trend = Trend.from_dict(item)
                                trend_map[trend.id] = trend
            except Exception as exc:
                logger.warning("Failed to load built-in trends from %s: %s", _DEFAULT_JSON_PATH, exc)

        # 2. Load custom user trends if present
        if self.custom_data_dir:
            custom_json = self.custom_data_dir / "trends.json"
            if custom_json.exists():
                try:
                    with open(custom_json, "r", encoding="utf-8") as f:
                        raw_list = json.load(f)
                        if isinstance(raw_list, list):
                            for item in raw_list:
                                if isinstance(item, dict):
                                    trend = Trend.from_dict(item)
                                    trend_map[trend.id] = trend
                except Exception as exc:
                    logger.warning("Failed to load custom trends from %s: %s", custom_json, exc)

        return list(trend_map.values())

    def get_all(self) -> List[Trend]:
        """Return all trend templates."""
        if self._trends_cache is None:
            self._trends_cache = self._load_trends()
        return list(self._trends_cache)

    def reload(self) -> List[Trend]:
        """Force reload trends cache from disk."""
        self._trends_cache = self._load_trends()
        return list(self._trends_cache)

    def get_by_id(self, trend_id: str) -> Optional[Trend]:
        """Find trend by ID."""
        for t in self.get_all():
            if t.id == trend_id:
                return t
        return None

    def get_categories(self) -> List[str]:
        """Return unique category list."""
        categories = set()
        for t in self.get_all():
            if t.category:
                categories.add(t.category)
        return ["All"] + sorted(list(categories))

    def search(self, query: str = "", category: str = "All") -> List[Trend]:
        """Search by keyword in title, description, tags, prompt and filter by category."""
        results: List[Trend] = []
        q = query.strip().lower()

        for t in self.get_all():
            # Category match
            if category and category != "All" and t.category.lower() != category.lower():
                continue

            # Query match
            if q:
                match_title = q in t.title.lower()
                match_desc = q in t.description.lower()
                match_prompt = q in t.prompt.lower()
                match_tags = any(q in tag.lower() for tag in t.tags)
                if not (match_title or match_desc or match_prompt or match_tags):
                    continue

            results.append(t)

        return results
