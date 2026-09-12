"""
ApplicationService — the dependency-injection root for NOVA.

``main.py`` constructs one instance and passes it to ``MainWindow``.
Centralising construction here eliminates global state and keeps
each layer testable in isolation.
"""
from __future__ import annotations

import logging

from app.config.settings import AppSettings
from app.hardware.capabilities import HardwareCapabilities, detect as detect_hardware
from app.inference.engine import InferenceEngine
from app.inference.service import InferenceService
from app.models.registry import ModelRegistry
from app.models.store import LocalModelStore
from app.models.selection import ModelSelectionService

logger = logging.getLogger("nova.core.app_service")


class ApplicationService:
    """Holds all application-scoped services and configuration.

    Instantiated once at startup.  Components receive this object rather
    than constructing their own collaborators.
    """

    def __init__(
        self,
        settings: AppSettings,
        inference_engine: InferenceEngine,
    ) -> None:
        self.settings = settings
        self.hardware: HardwareCapabilities = detect_hardware()
        self.inference = InferenceService(engine=inference_engine)

        self.model_registry = ModelRegistry(include_builtins=True)
        self.model_store = LocalModelStore(settings.models_dir)
        self.model_selection = ModelSelectionService()

        # Refresh registry statuses based on what's on disk
        self.model_registry.refresh_statuses(settings.models_dir)

        logger.info(
            "ApplicationService ready — backend=%s hardware=%s",
            inference_engine.backend_name(),
            self.hardware.summary(),
        )
        logger.info(
            "Model registry: %d spec(s) | models_dir=%s",
            len(self.model_registry),
            settings.models_dir,
        )

    def shutdown(self) -> None:
        """Gracefully shut down all managed services."""
        logger.info("ApplicationService shutting down…")
        self.inference.shutdown()
