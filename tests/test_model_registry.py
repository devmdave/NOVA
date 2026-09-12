"""Tests for ModelRegistry — registration, lookup, built-ins, status refresh."""
import pytest
from pathlib import Path

from app.models.errors import ModelNotFoundError, SpecValidationError
from app.models.registry import ModelRegistry
from app.models.spec import ModelSpec, ModelStatus


def _extra_spec(model_id: str = "extra-model") -> ModelSpec:
    return ModelSpec(
        model_id=model_id,
        display_name="Extra Model",
        description="A custom registered model",
        source="org/extra",
        runtime="diffusers_flux",
        license="MIT",
        min_vram_gb=4.0,
    )


class TestModelRegistryBuiltins:
    def test_builtin_flux_schnell_registered(self):
        registry = ModelRegistry(include_builtins=True)
        assert "flux-schnell" in registry

    def test_builtin_registry_has_one_spec(self):
        registry = ModelRegistry(include_builtins=True)
        assert len(registry) >= 1

    def test_no_builtins_option(self):
        registry = ModelRegistry(include_builtins=False)
        assert len(registry) == 0

    def test_flux_spec_fields(self):
        registry = ModelRegistry()
        spec = registry.get("flux-schnell")
        assert spec.runtime == "diffusers_flux"
        assert spec.license == "Apache 2.0"
        assert spec.min_vram_gb >= 8.0


class TestModelRegistryOperations:
    def test_register_valid_spec(self):
        registry = ModelRegistry(include_builtins=False)
        registry.register(_extra_spec())
        assert "extra-model" in registry

    def test_register_invalid_spec_raises(self):
        registry = ModelRegistry(include_builtins=False)
        bad = _extra_spec()
        bad.model_id = ""
        with pytest.raises(SpecValidationError):
            registry.register(bad)

    def test_get_existing_returns_spec(self):
        registry = ModelRegistry()
        spec = registry.get("flux-schnell")
        assert spec.model_id == "flux-schnell"

    def test_get_missing_raises(self):
        registry = ModelRegistry(include_builtins=False)
        with pytest.raises(ModelNotFoundError):
            registry.get("nonexistent")

    def test_get_or_none_missing_returns_none(self):
        registry = ModelRegistry(include_builtins=False)
        assert registry.get_or_none("nonexistent") is None

    def test_list_all(self):
        registry = ModelRegistry()
        all_specs = registry.list_all()
        assert len(all_specs) == len(registry)
        assert all(isinstance(s, ModelSpec) for s in all_specs)

    def test_list_by_runtime(self):
        registry = ModelRegistry()
        registry.register(_extra_spec("extra-flux"))
        flux_specs = registry.list_by_runtime("diffusers_flux")
        assert all(s.runtime == "diffusers_flux" for s in flux_specs)
        assert len(flux_specs) >= 2


class TestModelRegistryStatusRefresh:
    def test_refresh_marks_installed_when_dir_exists(self, tmp_path):
        registry = ModelRegistry()
        # Create a non-empty model directory
        model_dir = tmp_path / "flux-schnell"
        model_dir.mkdir()
        (model_dir / "model_index.json").write_text("{}")

        registry.refresh_statuses(tmp_path)
        assert registry.get("flux-schnell").status == ModelStatus.INSTALLED

    def test_refresh_leaves_not_installed_when_dir_missing(self, tmp_path):
        registry = ModelRegistry()
        registry.refresh_statuses(tmp_path)  # dir doesn't contain model
        assert registry.get("flux-schnell").status == ModelStatus.NOT_INSTALLED
