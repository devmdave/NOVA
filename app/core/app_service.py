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

from app.history.repository import LocalHistoryRepository
from app.history.service import HistoryService
from app.inference.models import GenerationResult

from app.config.service import SettingsService

from app.trends.repository import LocalTrendsRepository
from app.trends.service import TrendsService

from app.models.service import ModelService

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
        self.settings_service = SettingsService(settings)
        self.settings_service.settings_changed.connect(self._on_settings_changed)

        self.hardware: HardwareCapabilities = detect_hardware()
        self.inference = InferenceService(engine=inference_engine)

        self.model_registry = ModelRegistry(include_builtins=True)
        self.model_store = LocalModelStore(settings.models_dir)
        self.model_selection = ModelSelectionService()
        self.model_service = ModelService(self.model_registry, self.model_store, self.settings_service)
        self.model_service.load_persisted_custom_models(settings.models_dir)

        # History persistence
        self.history_repo = LocalHistoryRepository(settings.history_dir)
        self.history_service = HistoryService(self.history_repo)

        # AI Trends discovery
        self.trends_repo = LocalTrendsRepository()
        self.trends_service = TrendsService(self.trends_repo)

        # Automatically save successful generations to history
        self.inference.add_completion_listener(self._on_generation_completed)

        # Refresh registry statuses based on what's on disk
        self.model_registry.refresh_statuses(settings.models_dir)

        logger.info(
            "ApplicationService ready — backend=%s hardware=%s history_dir=%s",
            inference_engine.backend_name(),
            self.hardware.summary(),
            settings.history_dir,
        )
        logger.info(
            "Model registry: %d spec(s) | models_dir=%s",
            len(self.model_registry),
            settings.models_dir,
        )

    def _on_settings_changed(self, new_settings: AppSettings) -> None:
        """Apply dynamic settings updates without restarting when practical."""
        self.settings = new_settings
        self.model_store = LocalModelStore(new_settings.models_dir)
        self.model_registry.refresh_statuses(new_settings.models_dir)
        logger.info("ApplicationService updated active settings dynamically.")

    def _on_generation_completed(self, result: GenerationResult) -> None:
        """Completion callback triggered whenever an inference run finishes."""
        if result.success:
            self.history_service.save_generation(
                result=result,
                model_id=self.settings.default_model_id,
            )

    def shutdown(self) -> None:
        """Gracefully shut down all managed services."""
        logger.info("ApplicationService shutting down…")
        self.inference.shutdown()
