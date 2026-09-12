"""Tests for InferenceService — submit, cancel, validation, error wrapping."""
import pytest

from app.inference.errors import ValidationError
from app.inference.mock import MockInferenceEngine
from app.inference.models import GenerationRequest, GenerationStatus
from app.inference.service import InferenceService


@pytest.fixture
def service():
    svc = InferenceService(engine=MockInferenceEngine())
    yield svc
    svc.shutdown()


@pytest.fixture
def fast_request():
    return GenerationRequest(prompt="test prompt", steps=2)


class TestInferenceService:
    def test_is_available(self, service):
        assert service.is_available() is True

    def test_submit_invalid_request_raises(self, service):
        bad = GenerationRequest(prompt="", steps=2)
        with pytest.raises(ValidationError) as exc_info:
            service.submit(bad)
        assert "Prompt" in str(exc_info.value)

    def test_submit_returns_future(self, service, fast_request):
        from concurrent.futures import Future
        future = service.submit(fast_request)
        assert isinstance(future, Future)

    def test_successful_result_via_future(self, service, fast_request):
        result = service.submit(fast_request).result(timeout=10)
        assert result.success
        assert result.status == GenerationStatus.COMPLETED

    def test_progress_callback_forwarded(self, service):
        req = GenerationRequest(prompt="callback test", steps=3)
        received = []
        future = service.submit(req, progress_callback=lambda p: received.append(p))
        future.result(timeout=10)
        assert len(received) == 3

    def test_cancel_during_generation(self, service):
        req = GenerationRequest(prompt="slow job", steps=30)
        progress_count = []

        def cb(p):
            progress_count.append(p.step)
            if len(progress_count) == 2:
                service.cancel()

        result = service.submit(req, progress_callback=cb).result(timeout=15)
        assert result.cancelled
        assert len(progress_count) < req.steps

    def test_engine_error_wrapped_in_result(self, service):
        req = GenerationRequest(prompt="force error keyword", steps=2)
        result = service.submit(req).result(timeout=10)
        assert not result.success
        assert result.error is not None
