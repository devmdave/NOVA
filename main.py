"""NOVA application entry point."""
from __future__ import annotations

import argparse
import logging
import sys

from PySide6.QtWidgets import QApplication

from app.config.settings import load_settings
from app.core.app_service import ApplicationService
from app.core.logging_setup import setup_logging
from app.inference.engine import InferenceEngine
from app.ui.main_window import MainWindow
from app.ui.theme import apply_theme

logger = logging.getLogger("nova.main")


def _build_engine(use_real_model: bool, settings) -> InferenceEngine:
    """Construct and return the appropriate InferenceEngine.

    When ``use_real_model`` is True, loads DiffusersFluxRuntime from the
    path in settings.  Falls back to MockInferenceEngine on any error.
    """
    if not use_real_model:
        from app.inference.mock import MockInferenceEngine
        return MockInferenceEngine()

    # Real model path
    from app.models.errors import (
        ModelNotInstalledError,
        RuntimeNotAvailableError,
    )
    from app.models.registry import ModelRegistry
    from app.models.store import LocalModelStore
    from app.runtime.diffusers_flux import DiffusersFluxEngine, DiffusersFluxRuntime

    model_id = settings.default_model_id
    store = LocalModelStore(settings.models_dir)
    registry = ModelRegistry(include_builtins=True)

    try:
        spec = registry.get(model_id)
    except Exception as exc:
        logger.error("Model spec not found: %s. Falling back to mock.", exc)
        from app.inference.mock import MockInferenceEngine
        return MockInferenceEngine()

    try:
        store.assert_valid(spec)
    except (ModelNotInstalledError, Exception) as exc:
        logger.error("Model not installed: %s. Falling back to mock.", exc)
        from app.inference.mock import MockInferenceEngine
        return MockInferenceEngine()

    try:
        runtime = DiffusersFluxRuntime()
        logger.info("Loading model '%s' from '%s'…", model_id, store.model_path(model_id))
        runtime.load(
            store.model_path(model_id),
            progress_callback=lambda msg, frac: logger.info("[%.0f%%] %s", frac * 100, msg),
        )
        return DiffusersFluxEngine(runtime)
    except RuntimeNotAvailableError as exc:
        logger.error("%s. Falling back to mock.", exc)
        from app.inference.mock import MockInferenceEngine
        return MockInferenceEngine()
    except Exception as exc:
        logger.exception("Failed to load model. Falling back to mock.")
        from app.inference.mock import MockInferenceEngine
        return MockInferenceEngine()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NOVA — Local AI Image Generation")
    parser.add_argument(
        "--real-model",
        action="store_true",
        default=False,
        help=(
            "Load the real inference model (requires pip install -e .[inference] "
            "and downloaded model weights)."
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Application entry point."""
    args = _parse_args()

    # 1. Configuration
    settings = load_settings()

    # 2. Logging
    setup_logging(debug=settings.debug)
    use_real = args.real_model or settings.use_real_model
    logger.info("Starting NOVA %s (real-model=%s)", settings.version, use_real)

    # 3. Build the inference engine
    engine = _build_engine(use_real, settings)

    # 4. Compose the application service
    app_service = ApplicationService(settings=settings, inference_engine=engine)

    # 5. Qt application
    app = QApplication(sys.argv)
    apply_theme(app)

    # 6. Main window
    window = MainWindow(app_service=app_service)
    window.show()

    # 7. Event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
