"""
Application configuration settings and persistence for NOVA.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nova.config.settings")


def get_default_config_path() -> Path:
    """Return path to default config file (~/.nova/config.json or NOVA_CONFIG_PATH)."""
    env_path = os.environ.get("NOVA_CONFIG_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return Path(os.path.expanduser("~")) / ".nova" / "config.json"


@dataclass
class AppSettings:
    """Application configuration settings."""

    app_name: str = "NOVA"
    version: str = "0.1.0"
    debug: bool = False

    # Storage locations
    models_dir: str = os.path.join(os.path.expanduser("~"), ".nova", "models")
    history_dir: str = os.path.join(os.path.expanduser("~"), ".nova", "history")

    # Generation defaults
    default_model_id: str = "flux-schnell"
    default_width: int = 1024
    default_height: int = 1024
    default_steps: int = 20
    default_guidance: float = 7.5
    default_seed: int = -1

    # Backend & Hardware
    use_real_model: bool = False
    device_preference: str = "auto"  # "auto", "cuda", "cpu"

    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AppSettings:
        """Construct AppSettings safely from dictionary, filtering out unknown keys."""
        valid_keys = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)

    def validate(self) -> List[str]:
        """Validate settings and return a list of human-readable error messages."""
        errors: List[str] = []

        if not self.models_dir or not str(self.models_dir).strip():
            errors.append("Model storage location must not be empty.")
        if not self.history_dir or not str(self.history_dir).strip():
            errors.append("History storage location must not be empty.")

        if self.default_width <= 0 or self.default_width % 8 != 0:
            errors.append(f"Default width must be a positive multiple of 8 (got {self.default_width}).")
        if self.default_height <= 0 or self.default_height % 8 != 0:
            errors.append(f"Default height must be a positive multiple of 8 (got {self.default_height}).")

        if not (1 <= self.default_steps <= 200):
            errors.append(f"Default steps must be between 1 and 200 (got {self.default_steps}).")
        if not (0.0 <= self.default_guidance <= 30.0):
            errors.append(f"Default guidance must be between 0.0 and 30.0 (got {self.default_guidance}).")
        if self.default_seed < -1:
            errors.append(f"Default seed must be >= -1 (got {self.default_seed}).")

        if self.device_preference not in ("auto", "cuda", "cpu"):
            errors.append(f"Device preference must be auto, cuda, or cpu (got '{self.device_preference}').")

        return errors

    def save(self, config_path: Optional[str | Path] = None) -> None:
        """Persist settings to JSON file atomically."""
        target_path = Path(config_path).expanduser().resolve() if config_path else get_default_config_path()
        target_path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = target_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2)
            shutil.move(temp_path, target_path)
            logger.info("Saved AppSettings to %s", target_path)
        except Exception as exc:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            logger.exception("Failed to save settings to %s", target_path)
            raise IOError(f"Could not save settings: {exc}") from exc


def load_settings(config_path: Optional[str | Path] = None) -> AppSettings:
    """Load settings from JSON file with fallback to env vars and defaults."""
    target_path = Path(config_path).expanduser().resolve() if config_path else get_default_config_path()
    settings_data: Dict[str, Any] = {}

    if target_path.exists():
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    settings_data = data
                else:
                    logger.warning("Corrupted config in %s: not a JSON object", target_path)
        except Exception as exc:
            logger.warning("Failed to load settings from %s: %s", target_path, exc)

    settings = AppSettings.from_dict(settings_data)

    # Environment variable overrides
    if "NOVA_DEBUG" in os.environ:
        settings.debug = os.environ.get("NOVA_DEBUG", "0") in ("1", "true", "True")
    if "NOVA_MODELS_DIR" in os.environ:
        settings.models_dir = os.environ["NOVA_MODELS_DIR"]
    if "NOVA_HISTORY_DIR" in os.environ:
        settings.history_dir = os.environ["NOVA_HISTORY_DIR"]
    if "NOVA_DEFAULT_MODEL" in os.environ:
        settings.default_model_id = os.environ["NOVA_DEFAULT_MODEL"]
    if "NOVA_USE_REAL_MODEL" in os.environ:
        settings.use_real_model = os.environ.get("NOVA_USE_REAL_MODEL", "0") in ("1", "true", "True")

    # Validate loaded settings — fallback to defaults if invalid
    errors = settings.validate()
    if errors:
        logger.warning("Loaded settings contain invalid values: %s. Reverting invalid fields to defaults.", errors)
        default_settings = AppSettings()
        if settings.default_width <= 0 or settings.default_width % 8 != 0:
            settings.default_width = default_settings.default_width
        if settings.default_height <= 0 or settings.default_height % 8 != 0:
            settings.default_height = default_settings.default_height
        if not (1 <= settings.default_steps <= 200):
            settings.default_steps = default_settings.default_steps
        if not (0.0 <= settings.default_guidance <= 30.0):
            settings.default_guidance = default_settings.default_guidance
        if settings.default_seed < -1:
            settings.default_seed = default_settings.default_seed
        if settings.device_preference not in ("auto", "cuda", "cpu"):
            settings.device_preference = default_settings.device_preference

    return settings
