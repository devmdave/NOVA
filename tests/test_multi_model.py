"""
Unit and integration tests for NOVA's Multi-Model & Custom Local Model System.
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
from app.models.custom_detector import detect_and_validate_custom_model
from app.models.errors import RuntimeNotAvailableError
from app.models.registry import ModelRegistry
from app.models.selection import ModelSelectionService
from app.models.spec import ModelSpec, ModelStatus
from app.models.store import LocalModelStore
from app.runtime.resolver import RuntimeResolver
from app.ui.views.models_view import ModelsView


@pytest.fixture
def temp_dir():
    tmp = tempfile.mkdtemp()
    yield Path(tmp)
    shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Custom Model Detector Tests
# ---------------------------------------------------------------------------

def test_custom_detector_valid_flux_pipeline(temp_dir):
    model_folder = temp_dir / "custom_flux"
    model_folder.mkdir()

    # Create dummy model_index.json and required subfolders
    index_content = {
        "_class_name": "FluxPipeline",
        "transformer": ["transformer", "FluxTransformer2DModel"],
        "vae": ["vae", "AutoencoderKL"],
        "text_encoder": ["text_encoder", "CLIPTextModel"],
    }
    with open(model_folder / "model_index.json", "w", encoding="utf-8") as f:
        json.dump(index_content, f)

    (model_folder / "transformer").mkdir()
    (model_folder / "vae").mkdir()
    (model_folder / "text_encoder").mkdir()

    spec, errors = detect_and_validate_custom_model(model_folder)
    assert errors == []
    assert spec is not None
    assert spec.architecture == "flux-1"
    assert spec.runtime == "diffusers_flux"
    assert spec.is_custom is True


def test_custom_detector_rejects_missing_model_index(temp_dir):
    model_folder = temp_dir / "raw_weights"
    model_folder.mkdir()
    (model_folder / "model.safetensors").write_text("dummy")

    spec, errors = detect_and_validate_custom_model(model_folder)
    assert spec is None
    assert len(errors) == 1
    assert "Unsupported model architecture/runtime" in errors[0]


def test_custom_detector_rejects_unrecognized_pipeline(temp_dir):
    model_folder = temp_dir / "unknown_pipeline"
    model_folder.mkdir()

    index_content = {"_class_name": "UnknownCustomPipeline"}
    with open(model_folder / "model_index.json", "w", encoding="utf-8") as f:
        json.dump(index_content, f)

    spec, errors = detect_and_validate_custom_model(model_folder)
    assert spec is None
    assert "Unsupported model architecture/runtime" in errors[0]


def test_custom_detector_rejects_incomplete_folders(temp_dir):
    model_folder = temp_dir / "incomplete_flux"
    model_folder.mkdir()

    index_content = {
        "_class_name": "FluxPipeline",
        "transformer": ["transformer", "FluxTransformer2DModel"],
    }
    with open(model_folder / "model_index.json", "w", encoding="utf-8") as f:
        json.dump(index_content, f)

    # Note: transformer subfolder intentionally NOT created
    spec, errors = detect_and_validate_custom_model(model_folder)
    assert spec is None
    assert "Incomplete model directory" in errors[0]


# ---------------------------------------------------------------------------
# RuntimeResolver Tests
# ---------------------------------------------------------------------------

def test_runtime_resolver_supported_runtime(temp_dir):
    spec = ModelSpec(
        model_id="flux-test",
        display_name="FLUX Test",
        description="Test",
        source="test",
        runtime="diffusers_flux",
    )
    store = LocalModelStore(temp_dir)

    # When use_real_model is False, returns MockInferenceEngine safely
    engine = RuntimeResolver.resolve_engine(spec, store, use_real_model=False)
    assert engine.backend_name() == "MockEngine"


def test_runtime_resolver_unsupported_runtime(temp_dir):
    spec = ModelSpec(
        model_id="sdxl-test",
        display_name="SDXL Test",
        description="Test",
        source="test",
        runtime="diffusers_unsupported_adapter",
    )
    store = LocalModelStore(temp_dir)

    with pytest.raises(RuntimeNotAvailableError) as exc_info:
        RuntimeResolver.resolve_engine(spec, store, use_real_model=True)

    assert "Unsupported model architecture/runtime" in str(exc_info.value)


# ---------------------------------------------------------------------------
# ModelRegistry Multi-Model Tests
# ---------------------------------------------------------------------------

def test_model_registry_multi_model_support(temp_dir):
    registry = ModelRegistry(include_builtins=True)
    assert len(registry) >= 1

    custom_spec = ModelSpec(
        model_id="custom-sdxl",
        display_name="Custom SDXL Model",
        description="Custom local model",
        source=str(temp_dir),
        architecture="sdxl",
        runtime="diffusers_sdxl",
        is_custom=True,
    )

    registry.register(custom_spec)
    assert len(registry) >= 2
    assert "custom-sdxl" in registry
    assert registry.get("custom-sdxl").architecture == "sdxl"


# ---------------------------------------------------------------------------
# ModelsView UI Tests
# ---------------------------------------------------------------------------

def test_models_view_ui(qtbot, temp_dir):
    settings = AppSettings(models_dir=str(temp_dir / "models"), history_dir=str(temp_dir / "history"))
    engine = MockInferenceEngine()
    app_service = ApplicationService(settings, engine)

    view = ModelsView(app_service)
    qtbot.addWidget(view)

    # Check hardware & models displayed
    assert "CPU:" in view.lbl_cpu.text()
    assert view.models_list_layout.count() >= 1

    # Test selecting a model
    view._on_select_model("flux-schnell")
    assert app_service.settings.default_model_id == "flux-schnell"
