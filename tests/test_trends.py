"""
Unit and UI integration tests for NOVA's AI Trends feature.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
import pytest
from PySide6.QtCore import Qt

from app.config.settings import AppSettings
from app.core.app_service import ApplicationService
from app.inference.mock import MockInferenceEngine
from app.trends.models import Trend
from app.trends.repository import LocalTrendsRepository
from app.trends.service import TrendsService
from app.ui.views.generate_view import GenerateView
from app.ui.views.trends_view import TrendsView


@pytest.fixture
def temp_dir():
    tmp = tempfile.mkdtemp()
    yield Path(tmp)
    shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Trend Model Tests
# ---------------------------------------------------------------------------

def test_trend_model_dict_roundtrip():
    trend = Trend(
        id="test_t1",
        title="Cyberpunk Street",
        description="A rainy neon city street at night.",
        prompt="Cyberpunk street in rain, neon lights",
        negative_prompt="blurry, ugly",
        category="Photorealism",
        recommended_settings={"width": 1024, "height": 1024, "steps": 25, "guidance": 7.5, "mode": "text-to-image"},
        source_url="https://example.com/trend1",
        tags=["cyberpunk", "neon"],
    )

    data = trend.to_dict()
    assert data["id"] == "test_t1"
    assert data["title"] == "Cyberpunk Street"

    restored = Trend.from_dict(data)
    assert restored.id == trend.id
    assert restored.prompt == trend.prompt
    assert restored.recommended_settings["steps"] == 25
    assert restored.tags == ["cyberpunk", "neon"]


# ---------------------------------------------------------------------------
# TrendsRepository Tests
# ---------------------------------------------------------------------------

def test_repository_loads_default_trends():
    repo = LocalTrendsRepository()
    all_trends = repo.get_all()
    assert len(all_trends) >= 6
    categories = repo.get_categories()
    assert "All" in categories
    assert "Photorealism" in categories


def test_repository_search_and_filter():
    repo = LocalTrendsRepository()

    # Search query
    cyber_results = repo.search(query="cyberpunk")
    assert len(cyber_results) >= 1
    assert any("cyberpunk" in t.title.lower() or "cyberpunk" in t.prompt.lower() for t in cyber_results)

    # Category filter
    anime_results = repo.search(category="Anime & Illustration")
    assert len(anime_results) >= 1
    assert all(t.category == "Anime & Illustration" for t in anime_results)

    # Combined filter
    empty_results = repo.search(query="nonexistent_xyz_query_123")
    assert len(empty_results) == 0


def test_repository_custom_json(temp_dir):
    custom_data = [
        {
            "id": "custom_01",
            "title": "Custom Futuristic Car",
            "description": "A sleek hovercar.",
            "prompt": "Sleek hovercar floating over highway",
            "category": "Vehicles",
            "recommended_settings": {"steps": 20},
        }
    ]
    with open(temp_dir / "trends.json", "w", encoding="utf-8") as f:
        json.dump(custom_data, f)

    repo = LocalTrendsRepository(custom_data_dir=temp_dir)
    all_trends = repo.get_all()

    custom_item = repo.get_by_id("custom_01")
    assert custom_item is not None
    assert custom_item.title == "Custom Futuristic Car"


# ---------------------------------------------------------------------------
# TrendsService Tests
# ---------------------------------------------------------------------------

def test_trends_service():
    repo = LocalTrendsRepository()
    service = TrendsService(repo)

    all_trends = service.get_all_trends()
    assert len(all_trends) >= 6

    search_res = service.search_trends(query="diorama")
    assert len(search_res) >= 1
    assert search_res[0].id == "trend_isometric_diorama"


# ---------------------------------------------------------------------------
# TrendsView UI Tests
# ---------------------------------------------------------------------------

def test_trends_view_ui(qtbot, temp_dir):
    settings = AppSettings(models_dir=str(temp_dir / "models"), history_dir=str(temp_dir / "history"))
    engine = MockInferenceEngine()
    app_service = ApplicationService(settings, engine)

    view = TrendsView(app_service)
    qtbot.addWidget(view)

    assert view.list_trends.count() >= 6

    # Test filtering by text query
    view.txt_search.setText("diorama")
    assert view.list_trends.count() == 1

    # Test "Use in Generate" signal
    reused_trends = []
    view.use_trend_requested.connect(lambda t: reused_trends.append(t))

    view._on_use_clicked()
    assert len(reused_trends) == 1
    assert reused_trends[0].id == "trend_isometric_diorama"


def test_generate_view_apply_trend(qtbot, temp_dir):
    settings = AppSettings(models_dir=str(temp_dir / "models"), history_dir=str(temp_dir / "history"))
    engine = MockInferenceEngine()
    app_service = ApplicationService(settings, engine)

    gen_view = GenerateView(app_service)
    qtbot.addWidget(gen_view)

    trend = Trend(
        id="trend_test",
        title="Sci-Fi Corridor",
        description="A glowing spaceship hallway",
        prompt="Futuristic spaceship corridor with cyan LED strips",
        negative_prompt="dirty, broken",
        recommended_settings={"width": 1024, "height": 768, "steps": 15, "guidance": 8.0, "mode": "text-to-image"},
    )

    gen_view.apply_trend(trend)

    assert gen_view.txt_prompt.toPlainText() == "Futuristic spaceship corridor with cyan LED strips"
    assert gen_view.txt_negative.toPlainText() == "dirty, broken"

    applied_settings = gen_view.settings_panel.get_settings()
    assert applied_settings["width"] == 1024
    assert applied_settings["height"] == 768
    assert applied_settings["steps"] == 15
    assert applied_settings["guidance"] == 8.0
