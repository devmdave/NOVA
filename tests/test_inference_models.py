"""Tests for GenerationRequest, GenerationResult, and GenerationProgress."""
import pytest
from app.inference.models import (
    GenerationRequest,
    GenerationProgress,
    GenerationResult,
    GenerationStatus,
)


class TestGenerationRequest:
    def test_defaults_are_valid(self):
        req = GenerationRequest(prompt="a cat")
        assert req.validate() == []

    def test_empty_prompt_fails(self):
        req = GenerationRequest(prompt="   ")
        errors = req.validate()
        assert any("Prompt" in e for e in errors)

    def test_bad_width_fails(self):
        req = GenerationRequest(prompt="test", width=777)
        errors = req.validate()
        assert any("Width" in e for e in errors)

    def test_bad_height_fails(self):
        req = GenerationRequest(prompt="test", height=0)
        errors = req.validate()
        assert any("Height" in e for e in errors)

    def test_bad_steps_fails(self):
        req = GenerationRequest(prompt="test", steps=0)
        errors = req.validate()
        assert any("Steps" in e for e in errors)

    def test_bad_guidance_fails(self):
        req = GenerationRequest(prompt="test", guidance=50.0)
        errors = req.validate()
        assert any("Guidance" in e for e in errors)

    def test_multiple_errors_returned(self):
        req = GenerationRequest(prompt="", width=999, steps=0)
        errors = req.validate()
        assert len(errors) >= 3

    def test_resolve_seed_random_when_minus_one(self):
        req = GenerationRequest(prompt="test", seed=-1)
        s1 = req.resolve_seed()
        s2 = req.resolve_seed()
        # Both must be non-negative; they may differ (randomly)
        assert s1 >= 0
        assert s2 >= 0

    def test_resolve_seed_fixed(self):
        req = GenerationRequest(prompt="test", seed=42)
        assert req.resolve_seed() == 42
        assert req.resolve_seed() == 42  # deterministic


class TestGenerationProgress:
    def test_fraction_zero_when_no_steps(self):
        p = GenerationProgress(status=GenerationStatus.GENERATING)
        assert p.fraction == 0.0

    def test_fraction_half(self):
        p = GenerationProgress(status=GenerationStatus.GENERATING, step=5, total_steps=10)
        assert p.fraction == 0.5

    def test_fraction_clamped_at_one(self):
        p = GenerationProgress(status=GenerationStatus.GENERATING, step=12, total_steps=10)
        assert p.fraction == 1.0


class TestGenerationResult:
    def test_success_property(self):
        req = GenerationRequest(prompt="test")
        r = GenerationResult(request=req, status=GenerationStatus.COMPLETED)
        assert r.success is True
        assert r.cancelled is False

    def test_cancelled_property(self):
        req = GenerationRequest(prompt="test")
        r = GenerationResult(request=req, status=GenerationStatus.CANCELLED)
        assert r.success is False
        assert r.cancelled is True

    def test_error_property(self):
        req = GenerationRequest(prompt="test")
        r = GenerationResult(request=req, status=GenerationStatus.ERROR, error="boom")
        assert r.success is False
        assert r.cancelled is False
        assert r.error == "boom"
