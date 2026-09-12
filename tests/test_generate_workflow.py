"""
End-to-end tests for the Generate workflow.
Validates the UI's interaction with the underlying inference service.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt

from app.config.settings import AppSettings
from app.core.app_service import ApplicationService
from app.inference.mock import MockInferenceEngine
from app.ui.views.generate_view import GenerateView


@pytest.fixture
def mock_service(tmp_path):
    settings = AppSettings(models_dir=str(tmp_path), default_model_id="flux-schnell")
    engine = MockInferenceEngine()
    return ApplicationService(settings, engine)


def test_generate_view_initializes_with_model_defaults(qtbot, mock_service):
    """View primes settings from the active ModelSpec."""
    view = GenerateView(mock_service)
    qtbot.addWidget(view)

    settings = view.settings_panel.get_settings()
    assert settings["steps"] == 4  # from FLUX spec
    assert settings["guidance"] == 0.0
    assert settings["width"] == 1024


def test_generation_guard_model_not_installed(qtbot, mock_service, monkeypatch):
    """If the model is not ready, clicking Generate shows an error and does not submit."""
    view = GenerateView(mock_service)
    qtbot.addWidget(view)
    view.txt_prompt.setPlainText("valid prompt")

    # Force the engine to report unavailable
    monkeypatch.setattr(mock_service.inference, "is_available", lambda: False)

    # Click generate
    qtbot.mouseClick(view.btn_generate, Qt.LeftButton)

    # State should immediately jump to error
    assert view.preview.lbl_image.property("previewState") == "error"
    assert "not loaded" in view.preview.lbl_image.text() or "not installed" in view.preview.lbl_image.text()
    
    # Worker should not have been created
    assert view._active_worker is None


def test_successful_generation_flow(qtbot, mock_service):
    """End-to-end successful generation using the MockEngine."""
    view = GenerateView(mock_service)
    qtbot.addWidget(view)
    view.txt_prompt.setPlainText("test prompt")
    
    qtbot.mouseClick(view.btn_generate, Qt.LeftButton)
    
    worker = view._active_worker
    assert worker is not None
    
    # Wait for the worker to finish and the UI slot to process
    qtbot.waitUntil(lambda: view.btn_generate.isEnabled(), timeout=5000)

    # Generation finished. Assert UI updated.
    assert view.btn_generate.isEnabled() is True
    assert view.preview.lbl_image.property("previewState") == "completed"
    
    # Meta label should contain the backend name
    assert "MockEngine" in view.preview.lbl_meta.text()


def test_cancellation_flow(qtbot, mock_service):
    """User can cancel an in-progress generation."""
    view = GenerateView(mock_service)
    qtbot.addWidget(view)
    
    # Override the spinbox maximum (usually clamped by the model spec) so we can set 50
    view.settings_panel.spin_steps.setMaximum(50)
    # Set steps to 50 so generation takes ~7.5 seconds, giving us time to cancel
    view.settings_panel.spin_steps.setValue(50)
    view.txt_prompt.setPlainText("test prompt")
    
    qtbot.mouseClick(view.btn_generate, Qt.LeftButton)
    
    worker = view._active_worker
    assert worker is not None
    
    # Wait for the background thread to actually start generation
    qtbot.waitSignal(worker.signals.progress, timeout=2000)
    
    # Ensure UI state has updated and cancel button is enabled
    qtbot.waitUntil(lambda: view.btn_cancel.isEnabled(), timeout=1000)
    
    # Trigger cancellation via the view's slot directly
    view._on_cancel_clicked()
        
    qtbot.waitUntil(lambda: view.btn_generate.isEnabled(), timeout=5000)

    assert view.btn_generate.isEnabled() is True
    assert view.preview.lbl_image.property("previewState") == "cancelled"


def test_worker_validation_error_propagation(qtbot, mock_service, monkeypatch):
    """If submission fails with ValidationError (service-side), it's emitted cleanly."""
    from app.inference.errors import ValidationError
    
    def failing_submit(*args, **kwargs):
        raise ValidationError(["Invalid settings."])
        
    monkeypatch.setattr(mock_service.inference, "submit", failing_submit)
    
    view = GenerateView(mock_service)
    qtbot.addWidget(view)
    
    view.txt_prompt.setPlainText("valid prompt")
    qtbot.mouseClick(view.btn_generate, Qt.LeftButton)
    
    # The worker will run and instantly emit an error finished signal
    qtbot.waitUntil(lambda: view.preview.lbl_image.property("previewState") == "error", timeout=1000)
    
    assert "Invalid settings." in view.preview.lbl_image.text()
    assert view.btn_generate.isEnabled() is True
