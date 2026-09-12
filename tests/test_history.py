"""
Unit and integration tests for NOVA's History & local generation storage.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
import pytest
from PySide6.QtCore import Qt

from app.config.settings import AppSettings
from app.core.app_service import ApplicationService
from app.history.models import GenerationRecord
from app.history.repository import LocalHistoryRepository
from app.history.service import HistoryService
from app.inference.mock import MockInferenceEngine
from app.inference.models import (
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
)
from app.ui.views.history_view import HistoryView
from app.ui.views.generate_view import GenerateView


# Valid 1x1 PNG bytes for testing
TEST_PNG_BYTES = bytes([
    0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D,
    0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
    0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4, 0x89, 0x00, 0x00, 0x00,
    0x0A, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,
    0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49,
    0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82
])


@pytest.fixture
def temp_history_dir():
    """Provide a temporary directory for history storage testing."""
    tmp = tempfile.mkdtemp()
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def history_repo(temp_history_dir):
    """Provide a clean LocalHistoryRepository instance."""
    return LocalHistoryRepository(temp_history_dir)


@pytest.fixture
def history_service(history_repo):
    """Provide a clean HistoryService instance."""
    return HistoryService(history_repo)


# ---------------------------------------------------------------------------
# GenerationRecord Model Tests
# ---------------------------------------------------------------------------

def test_generation_record_dict_roundtrip():
    record = GenerationRecord(
        id="gen_test_001",
        image_path="/path/to/image.png",
        thumbnail_path="/path/to/thumb.png",
        prompt="A vibrant Cyberpunk city",
        negative_prompt="blurry, low quality",
        width=1024,
        height=768,
        steps=30,
        guidance=8.5,
        seed=42,
        model="flux-schnell",
        mode="text-to-image",
        denoising_strength=0.6,
        duration_seconds=3.5,
        metadata={"backend": "MockEngine"},
    )

    data = record.to_dict()
    assert data["id"] == "gen_test_001"
    assert data["prompt"] == "A vibrant Cyberpunk city"

    restored = GenerationRecord.from_dict(data)
    assert restored.id == record.id
    assert restored.prompt == record.prompt
    assert restored.seed == record.seed
    assert restored.guidance == record.guidance
    assert restored.metadata == {"backend": "MockEngine"}


# ---------------------------------------------------------------------------
# HistoryRepository Tests
# ---------------------------------------------------------------------------

def test_repository_save_and_reload(history_repo):
    record = GenerationRecord(
        id="gen_01",
        image_path="",
        thumbnail_path="",
        prompt="A mountain sunset",
        width=512,
        height=512,
        steps=20,
        guidance=7.0,
        seed=100,
    )

    saved = history_repo.save(record, TEST_PNG_BYTES)
    assert saved.id == "gen_01"
    assert os.path.exists(saved.image_path)
    assert os.path.exists(saved.thumbnail_path)
    assert os.path.exists(os.path.join(history_repo.records_dir, "gen_01.json"))

    # Reload using a NEW repository instance (simulates app restart)
    new_repo = LocalHistoryRepository(history_repo.storage_dir)
    all_records = new_repo.get_all()
    assert len(all_records) == 1
    assert all_records[0].id == "gen_01"
    assert all_records[0].prompt == "A mountain sunset"


def test_repository_handles_missing_image_files(history_repo):
    rec1 = GenerationRecord(id="gen_01", image_path="", thumbnail_path="", prompt="First image")
    rec2 = GenerationRecord(id="gen_02", image_path="", thumbnail_path="", prompt="Second image")

    history_repo.save(rec1, TEST_PNG_BYTES)
    history_repo.save(rec2, TEST_PNG_BYTES)

    # Delete image for rec1
    os.remove(history_repo.images_dir / "gen_01.png")

    records = history_repo.get_all()
    # rec1 should be skipped gracefully, rec2 remains intact
    assert len(records) == 1
    assert records[0].id == "gen_02"


def test_repository_handles_corrupt_json(history_repo):
    rec = GenerationRecord(id="gen_valid", image_path="", thumbnail_path="", prompt="Valid prompt")
    history_repo.save(rec, TEST_PNG_BYTES)

    # Create a corrupted json record file directly
    corrupt_file = history_repo.records_dir / "gen_corrupt.json"
    with open(corrupt_file, "w", encoding="utf-8") as f:
        f.write("{ INVALID JSON CONTENT :::")

    records = history_repo.get_all()
    assert len(records) == 1
    assert records[0].id == "gen_valid"


def test_repository_delete(history_repo):
    rec = GenerationRecord(id="gen_del", image_path="", thumbnail_path="", prompt="To be deleted")
    history_repo.save(rec, TEST_PNG_BYTES)

    assert len(history_repo.get_all()) == 1

    deleted = history_repo.delete("gen_del")
    assert deleted is True
    assert len(history_repo.get_all()) == 0
    assert not (history_repo.records_dir / "gen_del.json").exists()
    assert not (history_repo.images_dir / "gen_del.png").exists()


# ---------------------------------------------------------------------------
# HistoryService Tests
# ---------------------------------------------------------------------------

def test_service_save_successful_generation(history_service):
    req = GenerationRequest(prompt="Neon cat", width=512, height=512, steps=10, seed=42)
    result = GenerationResult(
        request=req,
        image_data=TEST_PNG_BYTES,
        seed_used=42,
        duration_seconds=1.2,
        status=GenerationStatus.COMPLETED,
    )

    record = history_service.save_generation(result, model_id="flux-schnell")
    assert record is not None
    assert record.prompt == "Neon cat"
    assert record.seed == 42

    history = history_service.get_history()
    assert len(history) == 1
    assert history[0].prompt == "Neon cat"


def test_service_ignores_failed_generation(history_service):
    req = GenerationRequest(prompt="Failed prompt")
    result = GenerationResult(
        request=req,
        status=GenerationStatus.ERROR,
        error="Simulation error",
    )

    record = history_service.save_generation(result)
    assert record is None
    assert len(history_service.get_history()) == 0


# ---------------------------------------------------------------------------
# End-to-End Application Integration Test
# ---------------------------------------------------------------------------

def test_app_service_auto_saves_generation_to_history(temp_history_dir):
    settings = AppSettings(history_dir=temp_history_dir)
    engine = MockInferenceEngine()
    app_service = ApplicationService(settings, engine)

    # Submit a generation job
    req = GenerationRequest(prompt="Auto save test", steps=2, seed=999)
    future = app_service.inference.submit(req)
    result = future.result()

    assert result.success is True

    # History service should have automatically recorded the successful run
    records = app_service.history_service.get_history()
    assert len(records) == 1
    assert records[0].prompt == "Auto save test"
    assert records[0].seed == 999


# ---------------------------------------------------------------------------
# UI View & Parameter Reuse Tests
# ---------------------------------------------------------------------------

def test_history_view_ui(qtbot, temp_history_dir):
    settings = AppSettings(history_dir=temp_history_dir)
    engine = MockInferenceEngine()
    app_service = ApplicationService(settings, engine)

    # Pre-populate 2 generations
    rec1 = GenerationRecord(id="g1", image_path="", thumbnail_path="", prompt="Landscape painting", seed=10)
    rec2 = GenerationRecord(id="g2", image_path="", thumbnail_path="", prompt="Portrait photo", seed=20)
    app_service.history_repo.save(rec1, TEST_PNG_BYTES)
    app_service.history_repo.save(rec2, TEST_PNG_BYTES)

    view = HistoryView(app_service)
    qtbot.addWidget(view)

    assert view.list_gallery.count() == 2

    # Test parameter reuse signal
    reused_records = []
    view.reuse_requested.connect(lambda r: reused_records.append(r))

    view._on_reuse_clicked()
    assert len(reused_records) == 1
    assert reused_records[0].prompt in ("Landscape painting", "Portrait photo")


def test_generate_view_apply_history_record(qtbot, temp_history_dir):
    settings = AppSettings(history_dir=temp_history_dir)
    engine = MockInferenceEngine()
    app_service = ApplicationService(settings, engine)

    gen_view = GenerateView(app_service)
    qtbot.addWidget(gen_view)

    record = GenerationRecord(
        id="rec_reuse",
        image_path="",
        thumbnail_path="",
        prompt="Fantasy dragon over castle",
        negative_prompt="blurry, dark",
        width=768,
        height=768,
        steps=15,
        guidance=9.0,
        seed=777,
        mode="text-to-image",
    )

    gen_view.apply_history_record(record)

    assert gen_view.txt_prompt.toPlainText() == "Fantasy dragon over castle"
    assert gen_view.txt_negative.toPlainText() == "blurry, dark"
    applied_settings = gen_view.settings_panel.get_settings()
    assert applied_settings["width"] == 768
    assert applied_settings["height"] == 768
    assert applied_settings["steps"] == 15
    assert applied_settings["seed"] == 777
    assert applied_settings["guidance"] == 9.0
