"""
Trends package exports.
"""
from app.trends.models import Trend
from app.trends.repository import TrendsRepository, LocalTrendsRepository
from app.trends.service import TrendsService

__all__ = [
    "Trend",
    "TrendsRepository",
    "LocalTrendsRepository",
    "TrendsService",
]
