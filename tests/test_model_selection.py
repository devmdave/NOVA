"""Tests for ModelSelectionService."""
import pytest
from app.hardware.capabilities import HardwareCapabilities, GpuInfo
from app.models.selection import ModelSelectionService
from app.models.spec import ModelSpec


def _valid_spec(model_id="test", **overrides) -> ModelSpec:
    defaults = dict(
        model_id=model_id,
        display_name="Test",
        description="test",
        source="org/test",
        runtime="dummy",
        license="Apache",
        min_vram_gb=8.0,
        recommended_vram_gb=12.0,
        model_size_gb=5.0,
        supported_vendors=["NVIDIA", "AMD"]
    )
    defaults.update(overrides)
    return ModelSpec(**defaults)


def _hw(ram_gb=16.0, has_gpu=True, vendor="NVIDIA", vram_gb=12.0) -> HardwareCapabilities:
    gpus = [GpuInfo(name=f"{vendor} GPU", vendor=vendor, vram_gb=vram_gb)] if has_gpu else []
    return HardwareCapabilities(
        cpu_name="Test CPU",
        cpu_cores=8,
        ram_gb=ram_gb,
        gpus=gpus,
    )


class TestModelSelectionService:
    @pytest.fixture
    def service(self):
        return ModelSelectionService()

    def test_missing_gpu_fails_if_required(self, service):
        hw = _hw(has_gpu=False)
        spec = _valid_spec(min_vram_gb=8.0)
        
        rec = service.evaluate(hw, [spec])
        compat = rec.evaluations[spec.model_id]
        
        assert not compat.is_compatible
        assert "requires a GPU" in compat.reasons[0]

    def test_unsupported_vendor_fails(self, service):
        hw = _hw(vendor="Intel")
        spec = _valid_spec(supported_vendors=["NVIDIA", "AMD"])
        
        rec = service.evaluate(hw, [spec])
        compat = rec.evaluations[spec.model_id]
        
        assert not compat.is_compatible
        assert "Intel" in compat.reasons[0]

    def test_insufficient_vram_fails(self, service):
        hw = _hw(vram_gb=4.0)
        spec = _valid_spec(min_vram_gb=8.0)
        
        rec = service.evaluate(hw, [spec])
        compat = rec.evaluations[spec.model_id]
        
        assert not compat.is_compatible
        assert "Insufficient VRAM" in compat.reasons[0]

    def test_insufficient_system_ram_fails(self, service):
        hw = _hw(ram_gb=8.0)
        spec = _valid_spec(model_size_gb=16.0)
        
        rec = service.evaluate(hw, [spec])
        compat = rec.evaluations[spec.model_id]
        
        assert not compat.is_compatible
        assert "Insufficient System RAM" in compat.reasons[0]

    def test_unknown_vram_assumes_compatible(self, service):
        hw = _hw(vram_gb=None)
        spec = _valid_spec(min_vram_gb=8.0)
        
        rec = service.evaluate(hw, [spec])
        compat = rec.evaluations[spec.model_id]
        
        assert compat.is_compatible
        assert any("Could not detect GPU VRAM" in r for r in compat.reasons)

    def test_recommends_best_compatible_model(self, service):
        hw = _hw(vram_gb=24.0)
        spec1 = _valid_spec(model_id="small", min_vram_gb=4.0, recommended_vram_gb=8.0, model_size_gb=2.0)
        spec2 = _valid_spec(model_id="large", min_vram_gb=16.0, recommended_vram_gb=24.0, model_size_gb=10.0)
        
        rec = service.evaluate(hw, [spec1, spec2])
        
        assert rec.evaluations["small"].is_compatible
        assert rec.evaluations["large"].is_compatible
        
        # Should pick the most capable model that fits
        assert rec.recommended_model_id == "large"

    def test_recommends_fallback_if_cannot_meet_recommended(self, service):
        hw = _hw(vram_gb=12.0)
        # Neither model meets its recommended VRAM
        spec1 = _valid_spec(model_id="small", min_vram_gb=4.0, recommended_vram_gb=16.0, model_size_gb=2.0)
        spec2 = _valid_spec(model_id="large", min_vram_gb=8.0, recommended_vram_gb=24.0, model_size_gb=6.0)
        
        rec = service.evaluate(hw, [spec1, spec2])
        
        assert rec.evaluations["small"].is_compatible
        assert rec.evaluations["large"].is_compatible
        
        # Falls back to largest compatible
        assert rec.recommended_model_id == "large"

    def test_no_compatible_model(self, service):
        hw = _hw(vram_gb=4.0)
        spec = _valid_spec(min_vram_gb=8.0)
        
        rec = service.evaluate(hw, [spec])
        assert rec.recommended_model_id is None
