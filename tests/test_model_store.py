"""Tests for LocalModelStore — path resolution, presence checks, and validation."""
import pytest
from pathlib import Path

from app.models.errors import ModelNotInstalledError, ModelValidationError
from app.models.spec import ModelSpec
from app.models.store import LocalModelStore


def _spec(model_id: str = "flux-schnell", runtime: str = "diffusers_flux") -> ModelSpec:
    return ModelSpec(
        model_id=model_id,
        display_name="Test",
        description="Test",
        source="org/test",
        runtime=runtime,
        license="Apache 2.0",
        min_vram_gb=8.0,
    )


def _populate_valid_flux(model_dir: Path) -> None:
    """Create the minimum file/dir structure for a valid diffusers_flux install."""
    model_dir.mkdir(parents=True, exist_ok=True)
    required = [
        "model_index.json",
        "scheduler",
        "transformer",
        "tokenizer",
        "tokenizer_2",
        "text_encoder",
        "text_encoder_2",
        "vae",
    ]
    for name in required:
        child = model_dir / name
        if name.endswith(".json"):
            child.write_text("{}")
        else:
            child.mkdir(exist_ok=True)
            (child / ".keep").write_text("")


class TestLocalModelStore:
    def test_model_path_returns_correct_path(self, tmp_path):
        store = LocalModelStore(tmp_path)
        assert store.model_path("flux-schnell") == tmp_path / "flux-schnell"

    def test_is_installed_false_when_missing(self, tmp_path):
        store = LocalModelStore(tmp_path)
        assert store.is_installed("flux-schnell") is False

    def test_is_installed_false_for_empty_dir(self, tmp_path):
        (tmp_path / "flux-schnell").mkdir()
        store = LocalModelStore(tmp_path)
        assert store.is_installed("flux-schnell") is False

    def test_is_installed_true_for_non_empty_dir(self, tmp_path):
        model_dir = tmp_path / "flux-schnell"
        model_dir.mkdir()
        (model_dir / "model_index.json").write_text("{}")
        store = LocalModelStore(tmp_path)
        assert store.is_installed("flux-schnell") is True

    def test_ensure_models_dir_creates_dir(self, tmp_path):
        models_path = tmp_path / "models"
        store = LocalModelStore(models_path)
        store.ensure_models_dir()
        assert models_path.exists()

    def test_validate_installation_missing_dir(self, tmp_path):
        store = LocalModelStore(tmp_path)
        errors = store.validate_installation(_spec())
        assert errors  # should report directory missing

    def test_validate_installation_missing_files(self, tmp_path):
        model_dir = tmp_path / "flux-schnell"
        model_dir.mkdir()
        (model_dir / "model_index.json").write_text("{}")
        # Only model_index.json present — other dirs missing
        store = LocalModelStore(tmp_path)
        errors = store.validate_installation(_spec())
        assert errors  # should report missing items

    def test_validate_installation_valid(self, tmp_path):
        model_dir = tmp_path / "flux-schnell"
        _populate_valid_flux(model_dir)
        store = LocalModelStore(tmp_path)
        errors = store.validate_installation(_spec())
        assert errors == []

    def test_assert_valid_raises_not_installed(self, tmp_path):
        store = LocalModelStore(tmp_path)
        with pytest.raises(ModelNotInstalledError):
            store.assert_valid(_spec())

    def test_assert_valid_raises_validation_error(self, tmp_path):
        model_dir = tmp_path / "flux-schnell"
        model_dir.mkdir()
        (model_dir / "partial.json").write_text("{}")  # partial installation
        store = LocalModelStore(tmp_path)
        with pytest.raises(ModelValidationError):
            store.assert_valid(_spec())

    def test_assert_valid_passes_for_complete_install(self, tmp_path):
        model_dir = tmp_path / "flux-schnell"
        _populate_valid_flux(model_dir)
        store = LocalModelStore(tmp_path)
        store.assert_valid(_spec())  # must not raise

    def test_list_installed_ids_empty(self, tmp_path):
        store = LocalModelStore(tmp_path)
        assert store.list_installed_ids() == []

    def test_list_installed_ids_finds_models(self, tmp_path):
        for name in ("model-a", "model-b"):
            d = tmp_path / name
            d.mkdir()
            (d / "weights.bin").write_bytes(b"\x00")
        store = LocalModelStore(tmp_path)
        ids = store.list_installed_ids()
        assert "model-a" in ids
        assert "model-b" in ids

    def test_unknown_runtime_validation_has_no_required_files(self, tmp_path):
        model_dir = tmp_path / "custom-model"
        model_dir.mkdir()
        (model_dir / "any_file.bin").write_bytes(b"\x00")
        store = LocalModelStore(tmp_path)
        spec = _spec(model_id="custom-model", runtime="unknown_runtime")
        errors = store.validate_installation(spec)
        assert errors == []  # unknown runtimes have no required files defined
