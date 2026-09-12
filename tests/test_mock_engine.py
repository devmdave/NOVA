"""Tests for MockInferenceEngine — progress, cancellation, error path."""
import threading
import pytest

from app.inference.mock import MockInferenceEngine
from app.inference.models import GenerationRequest, GenerationStatus


@pytest.fixture
def engine():
    return MockInferenceEngine()


@pytest.fixture
def simple_request():
    # Use 3 steps to keep tests fast
    return GenerationRequest(prompt="a peaceful mountain lake", steps=3)


class TestMockInferenceEngine:
    def test_is_available(self, engine):
        assert engine.is_available() is True

    def test_backend_name(self, engine):
        assert engine.backend_name() == "MockEngine"

    def test_successful_generation(self, engine, simple_request):
        result = engine.generate(simple_request)
        assert result.success
        assert result.status == GenerationStatus.COMPLETED
        assert result.seed_used >= 0
        assert result.duration_seconds > 0
        assert result.image_data is not None
        assert result.metadata.get("backend") == "MockEngine"

    def test_progress_callback_called(self, engine, simple_request):
        steps_seen = []

        def cb(progress):
            steps_seen.append(progress.step)

        engine.generate(simple_request, progress_callback=cb)
        assert len(steps_seen) == simple_request.steps
        assert steps_seen == list(range(1, simple_request.steps + 1))

    def test_error_path_triggered_by_keyword(self, engine):
        req = GenerationRequest(prompt="trigger an error please", steps=2)
        result = engine.generate(req)
        assert not result.success
        assert result.status == GenerationStatus.ERROR
        assert result.error is not None

    def test_cancellation_mid_run(self, engine):
        req = GenerationRequest(prompt="long running job", steps=20)
        cancel_event = threading.Event()

        progress_steps = []

        def cb(progress):
            progress_steps.append(progress.step)
            if progress.step >= 3:
                cancel_event.set()

        result = engine.generate(req, progress_callback=cb, cancel_event=cancel_event)
        assert result.cancelled
        assert result.status == GenerationStatus.CANCELLED
        # Should have run at most a handful of steps before cancelling
        assert len(progress_steps) < req.steps

    def test_image_data_is_valid_png_signature(self, engine, simple_request):
        result = engine.generate(simple_request)
        assert result.image_data[:4] == b'\x89PNG'
