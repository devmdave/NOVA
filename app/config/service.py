"""
SettingsService — managing application configuration changes and persistence.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QObject, Signal

from app.config.settings import AppSettings

logger = logging.getLogger("nova.config.service")


class SettingsService(QObject):
    """Core service for managing settings state, validation, and persistence."""

    settings_changed = Signal(AppSettings)

    def __init__(self, settings: AppSettings, config_path: Optional[str | Path] = None) -> None:
        super().__init__()
        self._settings = settings
        self._config_path = config_path

    @property
    def settings(self) -> AppSettings:
        return self._settings

    def get_settings(self) -> AppSettings:
        """Return current application settings."""
        return self._settings

    def save_settings(self, new_settings: AppSettings) -> List[str]:
        """Validate and persist updated settings.

        Returns a list of validation error strings if validation fails (empty = success).
        """
        errors = new_settings.validate()
        if errors:
            logger.warning("Validation failed for updated settings: %s", errors)
            return errors

        try:
            new_settings.save(self._config_path)
            self._settings = new_settings
            logger.info("Persisted updated settings successfully.")
            self.settings_changed.emit(self._settings)
            return []
        except Exception as exc:
            logger.exception("Failed to save settings: %s", exc)
            return [f"Could not save settings: {exc}"]

    def reset_defaults(self) -> AppSettings:
        """Reset settings to factory defaults and persist them."""
        defaults = AppSettings()
        defaults.app_name = self._settings.app_name
        defaults.version = self._settings.version

        try:
            defaults.save(self._config_path)
        except Exception as exc:
            logger.warning("Failed to persist default settings: %s", exc)

        self._settings = defaults
        logger.info("Reset settings to defaults.")
        self.settings_changed.emit(self._settings)
        return self._settings
