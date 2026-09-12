"""
GenerationWorker — Qt runnable that calls InferenceService on a thread-pool thread.

The UI layer uses this to keep the Qt event loop free during generation.
Progress and completion signals are emitted back to the main thread where
Qt widgets can safely be updated.

Error handling strategy:
    - ValidationError / BackendUnavailableError raised by service.submit() are
      caught here and converted to a GenerationResult(status=ERROR) so that the
      UI always receives a typed result — never a raw exception.
    - Any other unexpected exception is also caught and wrapped.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from app.inference import (
    BackendUnavailableError,
    GenerationProgress,
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
    InferenceService,
    ValidationError,
)

logger = logging.getLogger("nova.ui.worker")


class WorkerSignals(QObject):
    """Qt signals emitted by GenerationWorker."""

    # Emitted after each diffusion step
    progress = Signal(GenerationProgress)

    # Emitted once when the job finishes (success, error, or cancelled)
    finished = Signal(GenerationResult)


class GenerationWorker(QRunnable):
    """Runs InferenceService.submit() in Qt's global thread pool.

    Constructed fresh per generation request so signals are never reused
    across jobs.
    """

    def __init__(self, service: InferenceService, request: GenerationRequest) -> None:
        super().__init__()
        self.service = service
        self.request = request
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        """Submit to InferenceService and emit results to the Qt main thread."""
        try:
            future = self.service.submit(
                self.request,
                progress_callback=self._on_progress,
            )
        except ValidationError as exc:
            # Request failed validation — convert to a user-friendly error result
            user_msg = _format_validation_error(exc)
            logger.warning("Validation error before generation: %s", user_msg)
            self.signals.finished.emit(GenerationResult(
                request=self.request,
                status=GenerationStatus.ERROR,
                error=user_msg,
            ))
            return
        except BackendUnavailableError:
            logger.warning("Backend unavailable — engine not ready.")
            self.signals.finished.emit(GenerationResult(
                request=self.request,
                status=GenerationStatus.ERROR,
                error=(
                    "No model is loaded. Please load a model before generating. "
                    "Start NOVA with --real-model, or install a model first."
                ),
            ))
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error submitting to InferenceService")
            self.signals.finished.emit(GenerationResult(
                request=self.request,
                status=GenerationStatus.ERROR,
                error=f"Unexpected error: {_safe_str(exc)}",
            ))
            return

        # Generation submitted — block THIS thread (not the Qt main thread) until done
        try:
            result = future.result()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error waiting for generation result")
            result = GenerationResult(
                request=self.request,
                status=GenerationStatus.ERROR,
                error=f"Generation failed unexpectedly: {_safe_str(exc)}",
            )

        self.signals.finished.emit(result)

    def _on_progress(self, progress: GenerationProgress) -> None:
        """Called from the inference thread — safe to emit Qt signals from here."""
        self.signals.progress.emit(progress)


# ---------------------------------------------------------------------------
# Error formatting helpers
# ---------------------------------------------------------------------------

def _format_validation_error(exc: ValidationError) -> str:
    """Convert a ValidationError to a single user-readable string."""
    if len(exc.messages) == 1:
        return exc.messages[0]
    return "; ".join(exc.messages)


def _safe_str(exc: Exception) -> str:
    """Return a safe, non-traceback string for display to the user."""
    return type(exc).__name__ + (f": {exc}" if str(exc) else "")
