"""
TrendsService — core application service for managing AI trend discovery.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from PySide6.QtCore import QObject, Signal

from app.trends.models import Trend
from app.trends.repository import TrendsRepository

logger = logging.getLogger("nova.trends.service")


class TrendsService(QObject):
    """Service layer for searching, filtering, and retrieving trend templates."""

    trends_updated = Signal()

    def __init__(self, repository: TrendsRepository) -> None:
        super().__init__()
        self._repository = repository

    @property
    def repository(self) -> TrendsRepository:
        return self._repository

    def get_all_trends(self) -> List[Trend]:
        """Return all available trends."""
        return self._repository.get_all()

    def get_categories(self) -> List[str]:
        """Return unique category list."""
        return self._repository.get_categories()

    def get_trend_by_id(self, trend_id: str) -> Optional[Trend]:
        """Fetch trend by ID."""
        return self._repository.get_by_id(trend_id)

    def search_trends(self, query: str = "", category: str = "All") -> List[Trend]:
        """Search and filter trends by query and category."""
        return self._repository.search(query=query, category=category)
