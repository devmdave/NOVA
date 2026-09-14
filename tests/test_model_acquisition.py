"""
Unit and integration tests for Model Acquisition, Downloader, HF inspection, and Model Store.
"""
import shutil
import threading
import pytest
from pathlib import Path
from PySide6.QtCore import QObject

from app.config.settings import AppSettings
from app.config.service import SettingsService
from app.models.catalog import get_official_catalog, get_catalog_item
from app.models.hf_utils import parse_hf_repo_id, inspect_hf_custom_model
import app.models.hf_utils as hf_utils
from app.models.acquisition import ModelAcquisitionService
from app.models.registry import ModelRegistry
from app.models.store import LocalModelStore
from app.models.spec import ModelSpec, ModelStatus
from app.models.service import ModelService
from app.core.app_service import ApplicationService
from app.inference.mock import MockInferenceEngine


@pytest.fixture
def temp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def acquisition_env(temp_dir):
    models_dir = temp_dir / "models"
    models_dir.mkdir()
    settings = AppSettings(models_dir=str(models_dir), history_dir=str(temp_dir / "history"))
    settings_service = SettingsService(settings)
    registry = ModelRegistry(include_builtins=True)
    store = LocalModelStore(models_dir)
    acquisition = ModelAcquisitionService(registry, store, settings_service)
    service = ModelService(registry, store, settings_service, acquisition)
    return {
        "models_dir": models_dir,
        "settings": settings,
        "settings_service": settings_service,
        "registry": registry,
        "store": store,
        "acquisition": acquisition,
        "service": service,
    }


def test_official_catalog():
    catalog = get_official_catalog()
    assert len(catalog) >= 3
    ids = [item.model_id for item in catalog]
    assert "flux-schnell" in ids
    assert "sdxl-turbo" in ids
    assert "sd15" in ids

    item = get_catalog_item("sdxl-turbo")
    assert item is not None
    assert item.architecture == "sdxl"


def test_parse_hf_repo_id():
    assert parse_hf_repo_id("black-forest-labs/FLUX.1-schnell") == "black-forest-labs/FLUX.1-schnell"
    assert parse_hf_repo_id("https://huggingface.co/stabilityai/sdxl-turbo") == "stabilityai/sdxl-turbo"
    assert parse_hf_repo_id("https://huggingface.co/runwayml/stable-diffusion-v1-5/tree/main") == "runwayml/stable-diffusion-v1-5"
    assert parse_hf_repo_id("invalid-repo-string") is None


def test_inspect_hf_custom_model_supported():
    mock_index = {
        "_class_name": "FluxPipeline",
        "_diffusers_version": "0.30.0",
    }
    spec, errors = inspect_hf_custom_model("black-forest-labs/FLUX.1-schnell", index_data=mock_index)
    assert not errors
    assert spec is not None
    assert spec.architecture == "flux-1"
    assert spec.is_custom is True


def test_inspect_hf_custom_model_unsupported():
    mock_index = {
        "_class_name": "UnrecognizedCustomPipeline",
    }
    spec, errors = inspect_hf_custom_model("some-org/unknown-model", index_data=mock_index)
    assert spec is None
    assert len(errors) == 1
    assert "Unsupported model architecture" in errors[0]


def test_download_official_model(acquisition_env, qtbot):
    acq = acquisition_env["acquisition"]
    registry = acquisition_env["registry"]

    started = []
    finished = []

    acq.download_started.connect(lambda mid: started.append(mid))
    acq.download_finished.connect(lambda mid, ok, spec, err: finished.append((mid, ok, spec)))

    with qtbot.waitSignal(acq.download_finished, timeout=5000):
        ok, msg = acq.download_official_model("sdxl-turbo")
        assert ok is True

    assert "sdxl-turbo" in started
    assert len(finished) == 1
    mid, ok, spec = finished[0]
    assert mid == "sdxl-turbo"
    assert ok is True
    assert spec is not None
    assert registry.get("sdxl-turbo").status == ModelStatus.READY


def test_duplicate_model_download_rejected(acquisition_env):
    acq = acquisition_env["acquisition"]
    models_dir = acquisition_env["models_dir"]

    # Pre-create valid installed folder
    sd15_folder = models_dir / "sd15"
    sd15_folder.mkdir()
    (sd15_folder / "model_index.json").write_text("{}")
    acquisition_env["registry"].refresh_statuses(models_dir)

    ok, msg = acq.download_official_model("sd15")
    assert ok is False
    assert "already installed" in msg.lower()


def test_download_cancellation_cleans_staging(acquisition_env, qtbot):
    acq = acquisition_env["acquisition"]
    models_dir = acquisition_env["models_dir"]

    cancelled = []
    acq.download_cancelled.connect(lambda mid: cancelled.append(mid))

    spec = get_catalog_item("flux-schnell")

    with qtbot.waitSignal(acq.download_cancelled, timeout=5000):
        ok, msg = acq.start_acquisition(spec)
        assert ok is True
        acq.cancel_download("flux-schnell")

    assert "flux-schnell" in cancelled

    # Staging area should be removed and target folder should not exist
    staging = models_dir / ".downloads" / "flux-schnell_tmp"
    target = models_dir / "flux-schnell"
    assert not staging.exists()
    assert not target.exists()


def test_insufficient_disk_space_handling(acquisition_env):
    acq = acquisition_env["acquisition"]
    spec = get_catalog_item("flux-schnell")
    spec.model_size_gb = 99999.0  # Require 99.9 TB

    ok, msg = acq.start_acquisition(spec)
    assert ok is False
    assert "insufficient disk space" in msg.lower()


def test_custom_hf_import_flow(acquisition_env, qtbot, monkeypatch):
    acq = acquisition_env["acquisition"]
    registry = acquisition_env["registry"]

    monkeypatch.setattr(
        hf_utils,
        "fetch_hf_model_index",
        lambda repo_id: ({"_class_name": "FluxPipeline"}, None),
    )

    with qtbot.waitSignal(acq.download_finished, timeout=5000):
        ok, msg = acq.download_custom_hf_model("black-forest-labs/FLUX.1-schnell")
        assert ok is True

    assert "flux_1-schnell" in registry or "flux-schnell" in registry
