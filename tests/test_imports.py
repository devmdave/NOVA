"""Verify that all core package modules can be imported without error."""


def test_imports():
    """Smoke test — every public module must be importable."""
    import app
    from app.config.settings import AppSettings, load_settings
    from app.core.logging_setup import setup_logging
    from app.core.app_service import ApplicationService

    # Inference layer
    from app.inference import (
        InferenceEngine,
        InferenceService,
        GenerationRequest,
        GenerationResult,
        GenerationProgress,
        GenerationStatus,
    )
    from app.inference.mock import MockInferenceEngine

    # Models layer
    from app.models.interface import ModelManager

    # Hardware layer
    from app.hardware.capabilities import HardwareCapabilities, detect

    assert True
