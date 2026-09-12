import os
from dataclasses import dataclass


@dataclass
class AppSettings:
    """Application configuration settings."""
    app_name: str = "NOVA"
    version: str = "0.1.0"
    debug: bool = False

    # Local model storage — configurable via env var NOVA_MODELS_DIR
    models_dir: str = os.path.join(os.path.expanduser("~"), ".nova", "models")

    # The model to load when --real-model is requested.
    # Must match a ModelSpec.model_id in the registry.
    default_model_id: str = "flux-schnell"


def load_settings() -> AppSettings:
    """Load and return application settings.
    Reads environment variables; in a future stage this can also read
    a JSON/YAML config file.
    """
    return AppSettings(
        debug=os.environ.get("NOVA_DEBUG", "0") == "1",
        models_dir=os.environ.get(
            "NOVA_MODELS_DIR",
            os.path.join(os.path.expanduser("~"), ".nova", "models"),
        ),
        default_model_id=os.environ.get("NOVA_DEFAULT_MODEL", "flux-schnell"),
    )
