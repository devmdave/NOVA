"""
Mock inference engine for UI development and automated testing.

Implements InferenceEngine without any real model dependencies.
Simulates step-by-step progress, cancellation, and error paths.
"""
from __future__ import annotations

import time
import logging
from typing import Optional

from .engine import InferenceEngine, ProgressCallback
from .errors import GenerationCancelledError
from .models import (
    GenerationProgress,
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
)

import threading

logger = logging.getLogger("nova.inference.mock")

# Minimal 1×1 grey PNG (valid PNG bytes — no external dependencies)
_PLACEHOLDER_PNG = bytes([
    0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D,
    0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
    0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4, 0x89, 0x00, 0x00, 0x00,
    0x0A, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,
    0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49,
    0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82
])

_STEP_DELAY_SECONDS = 0.15   # delay per simulated step


class MockInferenceEngine(InferenceEngine):
    """Simulates a local image-generation backend for development / testing."""

    def backend_name(self) -> str:
        return "MockEngine"

    def is_available(self) -> bool:
        return True

    def generate(
        self,
        request: GenerationRequest,
        progress_callback: Optional[ProgressCallback] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> GenerationResult:
        seed = request.resolve_seed()
        start = time.monotonic()

        logger.debug(
            "MockInferenceEngine.generate — prompt=%r steps=%d seed=%d",
            request.prompt[:60],
            request.steps,
            seed,
        )

        # ------------------------------------------------------------------ #
        # Simulate per-step progress with cancellation checks                 #
        # ------------------------------------------------------------------ #
        for step in range(1, request.steps + 1):
            # Honour cancellation between every step
            if cancel_event and cancel_event.is_set():
                logger.info("Generation cancelled at step %d/%d", step, request.steps)
                return GenerationResult(
                    request=request,
                    seed_used=seed,
                    duration_seconds=time.monotonic() - start,
                    status=GenerationStatus.CANCELLED,
                    error="Generation cancelled by user.",
                )

            if progress_callback:
                progress_callback(
                    GenerationProgress(
                        status=GenerationStatus.GENERATING,
                        step=step,
                        total_steps=request.steps,
                        message=f"Step {step}/{request.steps}",
                    )
                )

            time.sleep(_STEP_DELAY_SECONDS)

        # ------------------------------------------------------------------ #
        # Simulate error when prompt contains the word "error"                #
        # ------------------------------------------------------------------ #
        if "error" in request.prompt.lower():
            logger.warning("MockEngine simulating error for prompt: %r", request.prompt[:60])
            return GenerationResult(
                request=request,
                seed_used=seed,
                duration_seconds=time.monotonic() - start,
                status=GenerationStatus.ERROR,
                error="Simulated generation error triggered by prompt keyword.",
            )

        duration = time.monotonic() - start
        logger.info("MockEngine completed in %.2fs (seed=%d)", duration, seed)

        return GenerationResult(
            request=request,
            image_data=_PLACEHOLDER_PNG,
            seed_used=seed,
            duration_seconds=duration,
            status=GenerationStatus.COMPLETED,
            metadata={
                "backend": self.backend_name(),
                "width": request.width,
                "height": request.height,
            },
        )
