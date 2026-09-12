"""
ModelRegistry — in-memory catalogue of known models.

Ships with built-in specs (FLUX.1-schnell).
Additional specs can be registered at runtime.

The registry is pure Python — no IO, no torch, no diffusers imports.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .errors import ModelNotFoundError, SpecValidationError
from .spec import ModelSpec, ModelStatus

logger = logging.getLogger("nova.models.registry")


# ---------------------------------------------------------------------------
# Built-in model specifications
# ---------------------------------------------------------------------------

def _flux_schnell_spec() -> ModelSpec:
    return ModelSpec(
        model_id="flux-schnell",
        display_name="FLUX.1-schnell",
        description=(
            "A 12-billion parameter rectified flow transformer for text-to-image generation. "
            "State-of-the-art image quality with 1–4 step generation. "
            "Released by Black Forest Labs under the Apache 2.0 license."
        ),
        source="black-forest-labs/FLUX.1-schnell",
        runtime="diffusers_flux",
        license="Apache 2.0",
        min_vram_gb=16.0,
        recommended_vram_gb=24.0,
        model_size_gb=23.8,
        precision="bfloat16",
        capabilities=["text-to-image"],
        supported_vendors=["NVIDIA", "AMD", "Apple"],
        default_width=1024,
        default_height=1024,
        steps_min=1,
        steps_default=4,
        steps_max=20,
        guidance_default=0.0,
        tags=["text-to-image", "flux", "state-of-the-art"],
    )


_BUILTIN_SPECS: list[ModelSpec] = [
    _flux_schnell_spec(),
]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ModelRegistry:
    """In-memory catalogue of model specifications.

    Thread-safety: operations are not protected by a lock because the registry
    is read-mostly after startup.  If specs are added at runtime from multiple
    threads, the caller is responsible for serialisation.
    """

    def __init__(self, include_builtins: bool = True) -> None:
        self._specs: dict[str, ModelSpec] = {}

        if include_builtins:
            for spec in _BUILTIN_SPECS:
                self._register_unsafe(spec)

        logger.debug("ModelRegistry initialised with %d spec(s).", len(self._specs))

    # ---------------------------------------------------------------------- #
    # Registration                                                             #
    # ---------------------------------------------------------------------- #

    def register(self, spec: ModelSpec) -> None:
        """Register a new spec.  Raises SpecValidationError if spec is invalid."""
        errors = spec.validate()
        if errors:
            raise SpecValidationError(spec.model_id, errors)
        self._register_unsafe(spec)
        logger.info("Registered model spec '%s'.", spec.model_id)

    def _register_unsafe(self, spec: ModelSpec) -> None:
        self._specs[spec.model_id] = spec

    # ---------------------------------------------------------------------- #
    # Lookup                                                                   #
    # ---------------------------------------------------------------------- #

    def get(self, model_id: str) -> ModelSpec:
        """Return the spec for model_id. Raises ModelNotFoundError if missing."""
        try:
            return self._specs[model_id]
        except KeyError:
            raise ModelNotFoundError(model_id)

    def get_or_none(self, model_id: str) -> Optional[ModelSpec]:
        """Return the spec or None — never raises."""
        return self._specs.get(model_id)

    def list_all(self) -> list[ModelSpec]:
        """Return all registered specs (in registration order)."""
        return list(self._specs.values())

    def list_by_runtime(self, runtime_name: str) -> list[ModelSpec]:
        return [s for s in self._specs.values() if s.runtime == runtime_name]

    # ---------------------------------------------------------------------- #
    # Status refresh                                                           #
    # ---------------------------------------------------------------------- #

    def refresh_statuses(self, models_dir: str | Path) -> None:
        """Update each spec's status by checking whether files are on disk.

        Does NOT attempt to load models — only checks file presence.
        """
        models_path = Path(models_dir)
        for spec in self._specs.values():
            model_path = models_path / spec.model_id
            if model_path.exists() and any(model_path.iterdir()):
                if spec.status == ModelStatus.NOT_INSTALLED:
                    spec.status = ModelStatus.INSTALLED
                    logger.info("Model '%s' detected as installed.", spec.model_id)
            else:
                if spec.status == ModelStatus.INSTALLED:
                    spec.status = ModelStatus.NOT_INSTALLED
                    logger.warning("Model '%s' files missing, status reset.", spec.model_id)

    # ---------------------------------------------------------------------- #
    # Convenience                                                              #
    # ---------------------------------------------------------------------- #

    def __len__(self) -> int:
        return len(self._specs)

    def __contains__(self, model_id: str) -> bool:
        return model_id in self._specs
