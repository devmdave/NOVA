"""
LocalModelStore — path resolution and installation validation for local model files.

Knows where model files live on disk and what a valid installation looks like.
Does not load model weights — that is the runtime adapter's job.
"""
from __future__ import annotations

import logging
from pathlib import Path

from .errors import ModelNotInstalledError, ModelValidationError
from .spec import ModelSpec

logger = logging.getLogger("nova.models.store")

# Files that must exist inside a model directory for a valid installation.
# Keys are runtime names; values are relative glob patterns.
_REQUIRED_FILES_BY_RUNTIME: dict[str, list[str]] = {
    "diffusers_flux": [
        "model_index.json",   # Diffusers pipeline index
        "scheduler",          # scheduler directory
        "transformer",        # main model weights directory
        "tokenizer",
        "tokenizer_2",
        "text_encoder",
        "text_encoder_2",
        "vae",
    ],
}


class LocalModelStore:
    """Manages the on-disk layout for locally installed model weights."""

    def __init__(self, models_dir: str | Path) -> None:
        self.models_dir = Path(models_dir)

    # ---------------------------------------------------------------------- #
    # Path helpers                                                             #
    # ---------------------------------------------------------------------- #

    def model_path(self, model_id: str) -> Path:
        """Return the directory where this model's weights live."""
        return self.models_dir / model_id

    def ensure_models_dir(self) -> Path:
        """Create the models root directory if it doesn't exist."""
        self.models_dir.mkdir(parents=True, exist_ok=True)
        return self.models_dir

    # ---------------------------------------------------------------------- #
    # Presence checks                                                          #
    # ---------------------------------------------------------------------- #

    def is_installed(self, model_id: str) -> bool:
        """True if the model directory exists and is non-empty."""
        path = self.model_path(model_id)
        return path.exists() and path.is_dir() and any(path.iterdir())

    def validate_installation(self, spec: ModelSpec) -> list[str]:
        """Return a list of problems with the installed files (empty = OK).

        Checks for required files/directories specific to the runtime.
        """
        if not self.is_installed(spec.model_id):
            return [f"Model directory '{self.model_path(spec.model_id)}' does not exist or is empty."]

        model_path = self.model_path(spec.model_id)
        required = _REQUIRED_FILES_BY_RUNTIME.get(spec.runtime, [])
        missing: list[str] = []
        for name in required:
            candidate = model_path / name
            if not candidate.exists():
                missing.append(name)

        if missing:
            return [f"Missing required items: {', '.join(missing)}"]
        return []

    def assert_valid(self, spec: ModelSpec) -> None:
        """Raise ModelNotInstalledError or ModelValidationError if anything is wrong."""
        if not self.is_installed(spec.model_id):
            raise ModelNotInstalledError(spec.model_id, str(self.models_dir))

        problems = self.validate_installation(spec)
        if problems:
            raise ModelValidationError(spec.model_id, problems)

        logger.debug("Model '%s' validation passed.", spec.model_id)

    # ---------------------------------------------------------------------- #
    # Discovery                                                                #
    # ---------------------------------------------------------------------- #

    def list_installed_ids(self) -> list[str]:
        """Return model_ids of every non-empty subdirectory of models_dir."""
        if not self.models_dir.exists():
            return []
        return [
            d.name
            for d in sorted(self.models_dir.iterdir())
            if d.is_dir() and any(d.iterdir())
        ]
