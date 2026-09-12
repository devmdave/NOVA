"""Tests for ModelSpec and ModelStatus."""
import pytest
from app.models.spec import ModelSpec, ModelStatus


def _valid_spec(**overrides) -> ModelSpec:
    defaults = dict(
        model_id="test-model",
        display_name="Test Model",
        description="A test model",
        source="org/test-model",
        runtime="diffusers_flux",
        license="Apache 2.0",
        min_vram_gb=8.0,
    )
    defaults.update(overrides)
    return ModelSpec(**defaults)


class TestModelSpec:
    def test_valid_spec_passes(self):
        assert _valid_spec().validate() == []

    def test_empty_model_id_fails(self):
        errs = _valid_spec(model_id="   ").validate()
        assert any("model_id" in e for e in errs)

    def test_empty_display_name_fails(self):
        errs = _valid_spec(display_name="").validate()
        assert any("display_name" in e for e in errs)

    def test_empty_source_fails(self):
        errs = _valid_spec(source="").validate()
        assert any("source" in e for e in errs)

    def test_empty_runtime_fails(self):
        errs = _valid_spec(runtime="").validate()
        assert any("runtime" in e for e in errs)

    def test_negative_vram_fails(self):
        errs = _valid_spec(min_vram_gb=-1.0).validate()
        assert any("vram" in e.lower() for e in errs)

    def test_negative_recommended_vram_fails(self):
        errs = _valid_spec(recommended_vram_gb=-2.0).validate()
        assert any("recommended_vram_gb" in e.lower() for e in errs)

    def test_recommended_vram_less_than_min_fails(self):
        errs = _valid_spec(min_vram_gb=16.0, recommended_vram_gb=8.0).validate()
        assert any("cannot be less than min_vram_gb" in e for e in errs)

    def test_negative_model_size_fails(self):
        errs = _valid_spec(model_size_gb=-5.0).validate()
        assert any("model_size_gb" in e.lower() for e in errs)

    def test_bad_width_fails(self):
        errs = _valid_spec(default_width=777).validate()
        assert any("width" in e.lower() for e in errs)

    def test_bad_height_fails(self):
        errs = _valid_spec(default_height=0).validate()
        assert any("height" in e.lower() for e in errs)

    def test_steps_ordering_fails(self):
        # steps_default < steps_min
        errs = _valid_spec(steps_min=10, steps_default=5, steps_max=20).validate()
        assert any("steps" in e.lower() for e in errs)

    def test_multiple_errors_returned(self):
        errs = _valid_spec(model_id="", source="", default_width=3).validate()
        assert len(errs) >= 3

    def test_default_status_is_not_installed(self):
        spec = _valid_spec()
        assert spec.status == ModelStatus.NOT_INSTALLED

    def test_tags_default_empty(self):
        spec = _valid_spec()
        assert spec.tags == []

    def test_tags_set(self):
        spec = _valid_spec(tags=["text-to-image", "flux"])
        assert "flux" in spec.tags
