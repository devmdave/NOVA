"""
Tests for the DiffusersFluxRuntime / DiffusersFluxEngine adapter.

All tests use mocks — no actual model download or GPU is required.
torch and diffusers are mocked at the module level so these tests
pass even when those packages are not installed.
"""
from __future__ import annotations

import sys
import threading
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.inference.models import (
    GenerationRequest,
    GenerationStatus,
)
from app.models.errors import ModelLoadError, RuntimeNotAvailableError


# ---------------------------------------------------------------------------
# Helpers to build minimal fake torch + diffusers modules
# ---------------------------------------------------------------------------

def _make_fake_torch():
    torch = types.ModuleType("torch")
    torch.cuda = types.SimpleNamespace(
        is_available=lambda: False,
        empty_cache=lambda: None,
    )
    torch.bfloat16 = "bfloat16"
    torch.float32 = "float32"

    class FakeGenerator:
        def __init__(self, device="cpu"): pass
        def manual_seed(self, seed): return self

    torch.Generator = FakeGenerator
    return torch


def _make_fake_diffusers(fake_image):
    diffusers = types.ModuleType("diffusers")

    class FakePipeline:
        def __init__(self):
            self._interrupt = False

        @classmethod
        def from_pretrained(cls, path, **kwargs):
            return cls()

        def to(self, device):
            return self

        def __call__(self, prompt, **kwargs):
            cb = kwargs.get("callback_on_step_end")
            if cb:
                # Simulate one step callback
                cb(self, 0, 0, {})
            output = MagicMock()
            output.images = [fake_image]
            return output

    diffusers.FluxPipeline = FakePipeline
    return diffusers


def _make_fake_pil_image():
    """Return a minimal PIL Image-like object that saves to valid PNG bytes."""
    import io as _io
    img = MagicMock()
    # When save() is called, write minimal bytes to the buffer
    def _save(buf, format=None):
        buf.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
    img.save.side_effect = _save
    return img


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDiffusersFluxRuntimeImportCheck:
    def test_raises_when_torch_missing(self):
        """RuntimeNotAvailableError raised when torch is not importable."""
        with patch.dict(sys.modules, {"torch": None, "diffusers": None}):
            from app.runtime import diffusers_flux
            # Force reimport with patched modules
            import importlib
            importlib.reload(diffusers_flux)
            with pytest.raises(RuntimeNotAvailableError):
                diffusers_flux._check_imports()


class TestDiffusersFluxRuntimeWithMocks:
    """Tests using injected fake torch + diffusers modules."""

    @pytest.fixture
    def fake_image(self):
        return _make_fake_pil_image()

    @pytest.fixture
    def patched_modules(self, fake_image):
        fake_torch = _make_fake_torch()
        fake_diffusers = _make_fake_diffusers(fake_image)
        with patch.dict(sys.modules, {"torch": fake_torch, "diffusers": fake_diffusers}):
            yield

    @pytest.fixture
    def runtime(self, patched_modules):
        from app.runtime.diffusers_flux import DiffusersFluxRuntime
        return DiffusersFluxRuntime()

    def test_not_loaded_initially(self, runtime):
        assert runtime.is_loaded() is False

    def test_runtime_name(self, runtime):
        assert runtime.runtime_name() == "diffusers_flux"

    def test_load_sets_is_loaded(self, tmp_path, runtime):
        runtime.load(tmp_path)
        assert runtime.is_loaded() is True

    def test_load_calls_progress_callback(self, tmp_path, runtime):
        messages = []
        runtime.load(tmp_path, progress_callback=lambda msg, frac: messages.append(msg))
        assert len(messages) >= 1

    def test_unload_clears_pipeline(self, tmp_path, runtime):
        runtime.load(tmp_path)
        runtime.unload()
        assert runtime.is_loaded() is False

    def test_unload_when_not_loaded_is_safe(self, runtime):
        runtime.unload()  # must not raise

    def test_load_twice_is_idempotent(self, tmp_path, runtime):
        runtime.load(tmp_path)
        runtime.load(tmp_path)  # second call should no-op
        assert runtime.is_loaded() is True


class TestDiffusersFluxEngineWithMocks:
    @pytest.fixture
    def fake_image(self):
        return _make_fake_pil_image()

    @pytest.fixture
    def engine(self, fake_image, tmp_path):
        fake_torch = _make_fake_torch()
        fake_diffusers = _make_fake_diffusers(fake_image)
        with patch.dict(sys.modules, {"torch": fake_torch, "diffusers": fake_diffusers}):
            from app.runtime.diffusers_flux import DiffusersFluxEngine, DiffusersFluxRuntime
            rt = DiffusersFluxRuntime()
            rt.load(tmp_path)
            yield DiffusersFluxEngine(rt)

    def test_is_available_when_loaded(self, engine):
        assert engine.is_available() is True

    def test_backend_name(self, engine):
        assert "FLUX" in engine.backend_name()

    def test_generate_success(self, engine):
        req = GenerationRequest(prompt="a cat", steps=1)
        result = engine.generate(req)
        assert result.success
        assert result.status == GenerationStatus.COMPLETED
        assert result.seed_used >= 0
        assert result.image_data is not None

    def test_generate_returns_error_when_not_loaded(self, fake_image, tmp_path):
        fake_torch = _make_fake_torch()
        fake_diffusers = _make_fake_diffusers(fake_image)
        with patch.dict(sys.modules, {"torch": fake_torch, "diffusers": fake_diffusers}):
            from app.runtime.diffusers_flux import DiffusersFluxEngine, DiffusersFluxRuntime
            rt = DiffusersFluxRuntime()   # not loaded
            eng = DiffusersFluxEngine(rt)
            req = GenerationRequest(prompt="test", steps=1)
            result = eng.generate(req)
            assert result.status == GenerationStatus.ERROR

    def test_generate_cancelled_before_start(self, engine):
        cancel = threading.Event()
        cancel.set()
        req = GenerationRequest(prompt="test", steps=1)
        result = engine.generate(req, cancel_event=cancel)
        assert result.status == GenerationStatus.CANCELLED

    def test_generate_progress_callback_called(self, engine):
        steps = []
        req = GenerationRequest(prompt="test", steps=1)
        engine.generate(req, progress_callback=lambda p: steps.append(p.step))
        assert len(steps) >= 1
