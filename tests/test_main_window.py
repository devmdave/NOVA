"""
Tests for MainWindow startup, view stack setup, navigation, and shutdown behavior.
"""
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication

from app.config.settings import AppSettings
from app.core.app_service import ApplicationService
from app.inference.mock import MockInferenceEngine
from app.ui.main_window import MainWindow


@pytest.fixture
def temp_dir(tmp_path):
    return tmp_path


def test_main_window_initialization_and_navigation(qtbot, temp_dir):
    settings = AppSettings(
        models_dir=str(temp_dir / "models"),
        history_dir=str(temp_dir / "history"),
    )
    engine = MockInferenceEngine()
    app_service = ApplicationService(settings, engine)

    window = MainWindow(app_service=app_service)
    qtbot.addWidget(window)
    window.show()

    assert window.windowTitle() == "NOVA — AI Image Generation"
    assert window.stacked_widget.count() == 5

    # Check pages exist
    assert "generate" in window.views
    assert "trends" in window.views
    assert "history" in window.views
    assert "models" in window.views
    assert "settings" in window.views

    # Test navigation
    window._handle_navigation("models")
    assert window.stacked_widget.currentWidget() == window.views["models"]

    window._handle_navigation("settings")
    assert window.stacked_widget.currentWidget() == window.views["settings"]

    window._handle_navigation("history")
    assert window.stacked_widget.currentWidget() == window.views["history"]

    window.close()
