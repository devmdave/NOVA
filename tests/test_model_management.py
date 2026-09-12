"""
Unit and UI integration tests for NOVA's Local Model Management System.
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
from app.inference.mock import MockInferenceEngine
from app.models.registry import ModelRegistry
from app.models.service import ModelService
from app.models.spec import ModelSpec, ModelStatus
from app.models.store import LocalModelStore
from app.ui.views.models_view import ModelDetailDialog, ModelsView, RemoveModelDialog


@pytest.fixture
def temp_dir():
    tmp = tempfile.mkdtemp()
    yield Path(tmp)
    shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Model Service & State Transition Tests
# ---------------------------------------------------------------------------

def test_model_state_transitions_ready(temp_dir):
    models_dir = temp_dir / "models"
    models_dir.mkdir()
    flux_folder = models_dir / "flux-schnell"
    flux_folder.mkdir()

    # Create dummy required files for FLUX
    for item in ["model_index.json", "scheduler", "transformer", "tokenizer", "tokenizer_2", "text_encoder", "text_encoder_2", "vae"]:
        (flux_folder / item).mkdir() if item != "model_index.json" else (flux_folder / item).write_text("{}")

    settings = AppSettings(models_dir=str(models_dir), history_dir=str(temp_dir / "history"))
    engine = MockInferenceEngine()
    app_service = ApplicationService(settings, engine)

    service = app_service.model_service
    is_valid, problems = service.validate_model("flux-schnell")

    assert is_valid is True
    assert problems == []
    spec = service.get_model("flux-schnell")
    assert spec.status == ModelStatus.READY
    assert spec.error_message is None


def test_model_state_transitions_invalid(temp_dir):
    models_dir = temp_dir / "models"
    models_dir.mkdir()
    flux_folder = models_dir / "flux-schnell"
    flux_folder.mkdir()

    # Create incomplete files (missing transformer)
    (flux_folder / "model_index.json").write_text("{}")

    settings = AppSettings(models_dir=str(models_dir), history_dir=str(temp_dir / "history"))
    engine = MockInferenceEngine()
    app_service = ApplicationService(settings, engine)

    service = app_service.model_service
    is_valid, problems = service.validate_model("flux-schnell")

    assert is_valid is False
    assert len(problems) > 0
    spec = service.get_model("flux-schnell")
    assert spec.status == ModelStatus.INVALID
    assert "Missing required items" in spec.error_message


def test_model_selection(temp_dir):
    settings = AppSettings(models_dir=str(temp_dir / "models"), history_dir=str(temp_dir / "history"))
    engine = MockInferenceEngine()
    app_service = ApplicationService(settings, engine)

    # Register dummy model
    spec2 = ModelSpec(model_id="sdxl-base", display_name="SDXL Base", source="sdxl", architecture="sdxl")
    app_service.model_registry.register(spec2)

    success = app_service.model_service.select_active_model("sdxl-base")
    assert success is True
    assert app_service.settings.default_model_id == "sdxl-base"


def test_rescan_model_after_file_changes(temp_dir):
    models_dir = temp_dir / "models"
    models_dir.mkdir()

    settings = AppSettings(models_dir=str(models_dir), history_dir=str(temp_dir / "history"))
    engine = MockInferenceEngine()
    app_service = ApplicationService(settings, engine)
    service = app_service.model_service

    # Initially missing files
    status, problems = service.rescan_model("flux-schnell")
    assert status == ModelStatus.INVALID

    # Now create valid files
    flux_folder = models_dir / "flux-schnell"
    flux_folder.mkdir()
    for item in ["model_index.json", "scheduler", "transformer", "tokenizer", "tokenizer_2", "text_encoder", "text_encoder_2", "vae"]:
        (flux_folder / item).mkdir() if item != "model_index.json" else (flux_folder / item).write_text("{}")

    status, problems = service.rescan_model("flux-schnell")
    assert status == ModelStatus.READY


# ---------------------------------------------------------------------------
# Remove Behavior Tests
# ---------------------------------------------------------------------------

def test_remove_model_from_registry_keep_files(temp_dir):
    models_dir = temp_dir / "models"
    models_dir.mkdir()
    custom_dir = temp_dir / "custom_model"
    custom_dir.mkdir()
    (custom_dir / "model_index.json").write_text('{"_class_name": "FluxPipeline"}')

    settings = AppSettings(models_dir=str(models_dir), history_dir=str(temp_dir / "history"))
    engine = MockInferenceEngine()
    app_service = ApplicationService(settings, engine)

    spec, errors = app_service.model_service.register_custom_model(custom_dir)
    assert spec is not None

    # Remove from NOVA only (delete_files=False)
    success, msg = app_service.model_service.remove_model(spec.model_id, delete_files=False)
    assert success is True
    assert app_service.model_registry.get_or_none(spec.model_id) is None
    assert custom_dir.exists()  # Files remain intact on disk


def test_remove_model_with_delete_files(temp_dir):
    models_dir = temp_dir / "models"
    models_dir.mkdir()
    custom_dir = temp_dir / "custom_model_to_delete"
    custom_dir.mkdir()
    (custom_dir / "model_index.json").write_text('{"_class_name": "FluxPipeline"}')

    settings = AppSettings(models_dir=str(models_dir), history_dir=str(temp_dir / "history"))
    engine = MockInferenceEngine()
    app_service = ApplicationService(settings, engine)

    spec, errors = app_service.model_service.register_custom_model(custom_dir)
    assert spec is not None
    assert custom_dir.exists()

    # Remove with delete_files=True
    success, msg = app_service.model_service.remove_model(spec.model_id, delete_files=True)
    assert success is True
    assert app_service.model_registry.get_or_none(spec.model_id) is None
    assert not custom_dir.exists()  # Files deleted permanently from disk


# ---------------------------------------------------------------------------
# Restart Persistence Test
# ---------------------------------------------------------------------------

def test_custom_model_persists_across_restarts(temp_dir):
    models_dir = temp_dir / "models"
    models_dir.mkdir()
    custom_dir = temp_dir / "my_custom_flux"
    custom_dir.mkdir()
    (custom_dir / "model_index.json").write_text('{"_class_name": "FluxPipeline"}')

    settings = AppSettings(models_dir=str(models_dir), history_dir=str(temp_dir / "history"))
    engine = MockInferenceEngine()
    app_service1 = ApplicationService(settings, engine)

    spec, _ = app_service1.model_service.register_custom_model(custom_dir)
    assert spec is not None

    # Simulate app restart with a fresh ApplicationService
    app_service2 = ApplicationService(settings, engine)
    reloaded_spec = app_service2.model_registry.get_or_none(spec.model_id)

    assert reloaded_spec is not None
    assert reloaded_spec.model_id == spec.model_id
    assert reloaded_spec.is_custom is True


# ---------------------------------------------------------------------------
# UI Dialog Tests
# ---------------------------------------------------------------------------

def test_remove_model_dialog_ui(qtbot, temp_dir):
    settings = AppSettings(models_dir=str(temp_dir / "models"), history_dir=str(temp_dir / "history"))
    engine = MockInferenceEngine()
    app_service = ApplicationService(settings, engine)

    spec = ModelSpec(model_id="test_remove", display_name="Test Model", source=str(temp_dir))
    app_service.model_registry.register(spec)

    dialog = RemoveModelDialog(spec, app_service)
    qtbot.addWidget(dialog)
    dialog.show()

    # Default radio option is "Keep files on disk" -> Remove button enabled
    assert dialog.rad_keep_files.isChecked()
    assert dialog.btn_remove.isEnabled() is True

    # Switch to "Delete files from disk" -> Confirmation checkbox shown, Remove button disabled until checked
    dialog.rad_delete_files.setChecked(True)
    assert dialog.chk_confirm.isVisible() is True
    assert dialog.btn_remove.isEnabled() is False

    # Check confirmation box -> Remove button enabled
    dialog.chk_confirm.setChecked(True)
    assert dialog.btn_remove.isEnabled() is True
