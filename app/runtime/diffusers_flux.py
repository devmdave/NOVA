"""
DiffusersFluxRuntime & DiffusersFluxEngine

Runtime adapter for FLUX.1-schnell via HuggingFace Diffusers.

Both classes perform lazy imports of torch and diffusers so that the rest
of the application can import this module without those packages installed.
They only fail at load/generate time with a clear RuntimeNotAvailableError.

Thread-safety:
    load() and generate() are intended to be called from a worker thread,
    not the Qt main thread.  The runtime holds a single pipeline instance.
"""
from __future__ import annotations

import io
import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from app.inference.engine import InferenceEngine, ProgressCallback
from app.inference.models import (
    GenerationProgress,
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
)
from app.models.errors import ModelLoadError, RuntimeNotAvailableError
from app.runtime.adapter import LoadProgressCallback, ModelRuntime

if TYPE_CHECKING:  # pragma: no cover
    pass  # type-only imports go here in future

logger = logging.getLogger("nova.runtime.diffusers_flux")

RUNTIME_NAME = "diffusers_flux"
INSTALL_HINT = "Install with: pip install -e .[inference]"


def _check_imports() -> None:
    """Raise RuntimeNotAvailableError if torch or diffusers are missing."""
    missing: list[str] = []
    try:
        import torch  # noqa: F401
    except ImportError:
        missing.append("torch")
    try:
        import diffusers  # noqa: F401
    except ImportError:
        missing.append("diffusers")
    if missing:
        raise RuntimeNotAvailableError(
            RUNTIME_NAME,
            f"Missing packages: {', '.join(missing)}. {INSTALL_HINT}",
        )


def _select_device() -> str:
    """Pick the best available compute device."""
    import torch
    if torch.cuda.is_available():
        logger.info("CUDA device detected: %s", torch.cuda.get_device_name(0))
        return "cuda"
    logger.warning(
        "No CUDA device detected. Falling back to CPU — generation will be very slow."
    )
    return "cpu"


def _select_dtype(device: str):
    """Pick the appropriate torch dtype for the device."""
    import torch
    if device == "cuda":
        return torch.bfloat16
    return torch.float32


# ---------------------------------------------------------------------------
# Runtime adapter
# ---------------------------------------------------------------------------

class DiffusersFluxRuntime(ModelRuntime):
    """Loads FLUX.1-schnell via diffusers.FluxPipeline."""

    def __init__(self) -> None:
        self._pipeline = None
        self._device: Optional[str] = None
        self._lock = threading.Lock()

    def runtime_name(self) -> str:
        return RUNTIME_NAME

    def is_loaded(self) -> bool:
        return self._pipeline is not None

    def load(
        self,
        model_path: Path,
        progress_callback: Optional[LoadProgressCallback] = None,
    ) -> None:
        """Load the FLUX.1-schnell pipeline from a local directory."""
        _check_imports()

        import torch
        from diffusers import FluxPipeline

        if self._pipeline is not None:
            logger.debug("Pipeline already loaded — skipping reload.")
            return

        device = _select_device()
        dtype = _select_dtype(device)

        logger.info(
            "Loading FLUX.1-schnell from '%s' on %s (%s)...",
            model_path, device, dtype,
        )

        if progress_callback:
            progress_callback("Loading model weights from disk…", 0.1)

        try:
            pipeline = FluxPipeline.from_pretrained(
                str(model_path),
                torch_dtype=dtype,
                local_files_only=True,
            )
        except Exception as exc:
            raise ModelLoadError("flux-schnell", str(exc)) from exc

        if progress_callback:
            progress_callback(f"Moving pipeline to {device}…", 0.7)

        try:
            pipeline = pipeline.to(device)
        except Exception as exc:
            raise ModelLoadError("flux-schnell", f"Failed to move to {device}: {exc}") from exc

        if progress_callback:
            progress_callback("Model ready.", 1.0)

        with self._lock:
            self._pipeline = pipeline
            self._device = device

        logger.info("FLUX.1-schnell loaded successfully on %s.", device)

    def unload(self) -> None:
        """Release the pipeline and free GPU memory."""
        with self._lock:
            if self._pipeline is None:
                return
            del self._pipeline
            self._pipeline = None
            self._device = None

        # Encourage Python/torch to release GPU memory
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

        logger.info("FLUX.1-schnell unloaded.")


# ---------------------------------------------------------------------------
# InferenceEngine adapter
# ---------------------------------------------------------------------------

class DiffusersFluxEngine(InferenceEngine):
    """InferenceEngine that wraps DiffusersFluxRuntime.

    Converts NOVA's GenerationRequest into a Diffusers FluxPipeline call
    and converts the PIL Image output back to PNG bytes.
    """

    def __init__(self, runtime: DiffusersFluxRuntime) -> None:
        self._runtime = runtime

    def backend_name(self) -> str:
        return "DiffusersFlux (FLUX.1-schnell)"

    def is_available(self) -> bool:
        return self._runtime.is_loaded()

    def generate(
        self,
        request: GenerationRequest,
        progress_callback: Optional[ProgressCallback] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> GenerationResult:
        """Run FLUX.1-schnell generation."""
        if not self._runtime.is_loaded():
            return GenerationResult(
                request=request,
                status=GenerationStatus.ERROR,
                error="Model is not loaded. Call DiffusersFluxRuntime.load() first.",
            )

        if cancel_event and cancel_event.is_set():
            return GenerationResult(
                request=request,
                status=GenerationStatus.CANCELLED,
                error="Cancelled before generation started.",
            )

        seed = request.resolve_seed()
        start = time.monotonic()

        logger.info(
            "Generating with FLUX — prompt=%r size=%dx%d steps=%d seed=%d",
            request.prompt[:60], request.width, request.height, request.steps, seed,
        )

        if progress_callback:
            progress_callback(GenerationProgress(
                status=GenerationStatus.GENERATING,
                step=0,
                total_steps=request.steps,
                message="Starting generation…",
            ))

        try:
            import torch

            # Build a per-step callback that bridges Diffusers → NOVA progress
            _steps_done: list[int] = [0]

            def _diffusers_step_callback(pipeline, step_index, timestep, callback_kwargs):
                _steps_done[0] = step_index + 1
                if cancel_event and cancel_event.is_set():
                    # Diffusers >= 0.30 supports early stop via callback
                    pipeline._interrupt = True
                if progress_callback:
                    progress_callback(GenerationProgress(
                        status=GenerationStatus.GENERATING,
                        step=step_index + 1,
                        total_steps=request.steps,
                        message=f"Step {step_index + 1}/{request.steps}",
                    ))
                return callback_kwargs

            pipeline = self._runtime._pipeline  # type: ignore[attr-defined]

            generator = torch.Generator(
                device=self._runtime._device or "cpu"  # type: ignore[attr-defined]
            ).manual_seed(seed)

            output = pipeline(
                prompt=request.prompt,
                negative_prompt=request.negative_prompt or None,
                width=request.width,
                height=request.height,
                num_inference_steps=request.steps,
                guidance_scale=request.guidance,
                generator=generator,
                callback_on_step_end=_diffusers_step_callback,
                callback_on_step_end_tensor_inputs=["latents"],
            )

        except Exception as exc:  # noqa: BLE001
            logger.exception("FLUX generation failed")
            return GenerationResult(
                request=request,
                status=GenerationStatus.ERROR,
                error=str(exc),
            )

        # Check if interrupted by cancel
        if cancel_event and cancel_event.is_set():
            return GenerationResult(
                request=request,
                status=GenerationStatus.CANCELLED,
                error="Generation was cancelled.",
                seed_used=seed,
                duration_seconds=time.monotonic() - start,
            )

        # Convert PIL Image → PNG bytes
        image = output.images[0]
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()

        duration = time.monotonic() - start
        logger.info("Generation complete in %.1fs (seed=%d)", duration, seed)

        return GenerationResult(
            request=request,
            image_data=image_bytes,
            seed_used=seed,
            duration_seconds=duration,
            status=GenerationStatus.COMPLETED,
            metadata={
                "backend": self.backend_name(),
                "device": self._runtime._device,  # type: ignore[attr-defined]
                "width": request.width,
                "height": request.height,
            },
        )
