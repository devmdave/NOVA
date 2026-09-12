"""
Unit and integration tests for NOVA's Settings system.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
import pytest
from PySide6.QtCore import Qt

from app.config.service import SettingsService
from app.config.settings import AppSettings, load_settings
from app.core.app_service import ApplicationService
from app.inference.mock import MockInferenceEngine
from app.ui.views.settings_view import SettingsView


@pytest.fixture
def temp_dir():
    tmp = tempfile.mkdtemp()
    yield Path(tmp)
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def config_file(temp_dir):
    return temp_dir / "config.json"


# ---------------------------------------------------------------------------
# AppSettings & Persistence Tests
# ---------------------------------------------------------------------------

def test_app_settings_defaults():
    settings = AppSettings()
    assert settings.app_name == "NOVA"
    assert settings.version == "0.1.0"
    assert settings.default_width == 1024
    assert settings.default_height == 1024
    assert settings.default_steps == 20
    assert settings.default_guidance == 7.5
    assert settings.default_seed == -1
    assert settings.use_real_model is False
    assert settings.device_preference == "auto"
    assert settings.validate() == []


def test_app_settings_dict_roundtrip():
    original = AppSettings(
        default_width=768,
        default_height=512,
        default_steps=30,
        default_guidance=8.5,
        default_seed=42,
        use_real_model=True,
        device_preference="cuda",
    )
    data = original.to_dict()
    restored = AppSettings.from_dict(data)

    assert restored.default_width == 768
    assert restored.default_height == 512
    assert restored.default_steps == 30
    assert restored.default_guidance == 8.5
    assert restored.default_seed == 42
    assert restored.use_real_model is True
    assert restored.device_preference == "cuda"


def test_app_settings_validation():
    invalid_settings = AppSettings(
        models_dir="",
        default_width=100,  # not multiple of 8
        default_height=0,
        default_steps=300,  # > 200
        default_guidance=-5.0,
        default_seed=-10,
        device_preference="tpu",  # invalid option
    )
    errors = invalid_settings.validate()
    assert len(errors) == 7
    assert any("Model storage" in e for e in errors)
    assert any("width" in e for e in errors)
    assert any("steps" in e for e in errors)
    assert any("Device preference" in e for e in errors)


def test_save_and_load_settings(config_file):
    settings = AppSettings(
        default_width=768,
        default_height=768,
        default_steps=15,
        use_real_model=True,
    )
    settings.save(config_file)
    assert config_file.exists()

    loaded = load_settings(config_file)
    assert loaded.default_width == 768
    assert loaded.default_height == 768
    assert loaded.default_steps == 15
    assert loaded.use_real_model is True


def test_load_settings_handles_corrupted_file(config_file):
    with open(config_file, "w", encoding="utf-8") as f:
        f.write("{ INVALID JSON CONTENT :::")

    loaded = load_settings(config_file)
    # Should fall back cleanly to defaults without crashing
    assert loaded.app_name == "NOVA"
    assert loaded.default_width == 1024


def test_load_settings_env_var_override(config_file, monkeypatch):
    settings = AppSettings(default_model_id="flux-schnell")
    settings.save(config_file)

    monkeypatch.setenv("NOVA_DEFAULT_MODEL", "custom-model")
    loaded = load_settings(config_file)
    assert loaded.default_model_id == "custom-model"


# ---------------------------------------------------------------------------
# SettingsService Tests
# ---------------------------------------------------------------------------

def test_settings_service_save_and_signal(config_file):
    initial = AppSettings()
    service = SettingsService(initial, config_file)

    emitted = []
    service.settings_changed.connect(lambda s: emitted.append(s))

    updated = AppSettings(default_width=512, default_height=512)
    errors = service.save_settings(updated)

    assert errors == []
    assert len(emitted) == 1
    assert emitted[0].default_width == 512
    assert service.get_settings().default_width == 512
    assert config_file.exists()


def test_settings_service_rejects_invalid_settings(config_file):
    initial = AppSettings()
    service = SettingsService(initial, config_file)

    invalid = AppSettings(default_width=123)  # Invalid width
    errors = service.save_settings(invalid)

    assert len(errors) > 0
    assert service.get_settings().default_width == 1024  # Unchanged


def test_settings_service_reset_defaults(config_file):
    initial = AppSettings(default_width=512)
    service = SettingsService(initial, config_file)
    service.save_settings(initial)

    reset_settings = service.reset_defaults()
    assert reset_settings.default_width == 1024
    assert service.get_settings().default_width == 1024


# ---------------------------------------------------------------------------
# ApplicationService Integration Test
# ---------------------------------------------------------------------------

def test_app_service_settings_integration(temp_dir):
    config_path = temp_dir / "config.json"
    models_dir = str(temp_dir / "models")
    os.makedirs(models_dir, exist_ok=True)

    settings = AppSettings(models_dir=models_dir, history_dir=str(temp_dir / "history"))
    engine = MockInferenceEngine()
    app_service = ApplicationService(settings, engine)
    app_service.settings_service._config_path = config_path

    new_models_dir = str(temp_dir / "new_models")
    os.makedirs(new_models_dir, exist_ok=True)
    updated = AppSettings(models_dir=new_models_dir, history_dir=str(temp_dir / "history"))

    errors = app_service.settings_service.save_settings(updated)
    assert errors == []
    assert app_service.settings.models_dir == new_models_dir
    assert app_service.model_store.models_dir == Path(new_models_dir)


# ---------------------------------------------------------------------------
# SettingsView UI Test
# ---------------------------------------------------------------------------

def test_settings_view_ui(qtbot, temp_dir):
    settings = AppSettings(models_dir=str(temp_dir / "models"), history_dir=str(temp_dir / "history"))
    engine = MockInferenceEngine()
    app_service = ApplicationService(settings, engine)
    app_service.settings_service._config_path = temp_dir / "config.json"

    view = SettingsView(app_service)
    qtbot.addWidget(view)

    # Initial state matches settings
    assert view.spin_width.value() == 1024
    assert view.spin_height.value() == 1024

    # Change controls
    view.spin_width.setValue(768)
    view.spin_height.setValue(768)
    view.spin_steps.setValue(15)

    # Click Save
    qtbot.mouseClick(view.btn_save, Qt.LeftButton)

    # Check service updated
    saved = app_service.settings_service.get_settings()
    assert saved.default_width == 768
    assert saved.default_height == 768
    assert saved.default_steps == 15

    # Click Reset Defaults
    qtbot.mouseClick(view.btn_reset, Qt.LeftButton)

    # Check reset
    reset_settings = app_service.settings_service.get_settings()
    assert reset_settings.default_width == 1024
    assert view.spin_width.value() == 1024
