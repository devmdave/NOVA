"""
RuntimeResolver — resolves ModelSpec and runtime name to the appropriate Runtime Adapter and InferenceEngine.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Type

from app.inference.engine import InferenceEngine
from app.models.errors import ModelNotInstalledError, RuntimeNotAvailableError
from app.models.spec import ModelSpec
from app.models.store import LocalModelStore

logger = logging.getLogger("nova.runtime.resolver")


class RuntimeResolver:
    """Dispatches model specifications to concrete runtime adapters."""

    SUPPORTED_RUNTIMES = {"diffusers_flux"}

    @classmethod
    def is_runtime_supported(cls, runtime_name: str) -> bool:
        """Check if a runtime adapter is registered and supported."""
        return runtime_name in cls.SUPPORTED_RUNTIMES

    @classmethod
    def resolve_engine(
        cls,
        spec: ModelSpec,
        model_store: LocalModelStore,
        use_real_model: bool = True,
    ) -> InferenceEngine:
        """Construct and return the appropriate InferenceEngine for the model spec.

        Falls back to MockInferenceEngine if use_real_model is False or if runtime loading fails.
        Raises RuntimeNotAvailableError if the spec uses an unsupported runtime.
        """
        if not use_real_model:
            from app.inference.mock import MockInferenceEngine
            return MockInferenceEngine()

        if not cls.is_runtime_supported(spec.runtime):
            logger.warning("Unsupported runtime '%s' for model '%s'", spec.runtime, spec.model_id)
            raise RuntimeNotAvailableError(
                spec.runtime,
                f"Unsupported model architecture/runtime — runtime adapter '{spec.runtime}' is not installed."
            )

        if spec.runtime == "diffusers_flux":
            from app.runtime.diffusers_flux import DiffusersFluxEngine, DiffusersFluxRuntime

            model_path = Path(spec.source) if spec.is_custom else model_store.model_path(spec.model_id)

            if not model_path.exists() or not any(model_path.iterdir()):
                raise ModelNotInstalledError(spec.model_id, str(model_store.models_dir))

            try:
                runtime = DiffusersFluxRuntime()
                logger.info("Loading model '%s' via DiffusersFluxRuntime from '%s'…", spec.model_id, model_path)
                runtime.load(
                    model_path,
                    progress_callback=lambda msg, frac: logger.info("[%.0f%%] %s", frac * 100, msg),
                )
                return DiffusersFluxEngine(runtime)
            except Exception as exc:
                logger.exception("Failed to load model '%s': %s", spec.model_id, exc)
                raise

        raise RuntimeNotAvailableError(
            spec.runtime,
            f"Unsupported model architecture/runtime: {spec.runtime}"
        )
