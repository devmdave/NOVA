"""
InferenceService — application-level orchestrator for image generation.

Sits between the Qt UI and the InferenceEngine.  The UI submits a
GenerationRequest and receives progress notifications + a final result.
It never imports a concrete engine or knows anything about models.

Thread model:
    - submit() returns immediately; generation runs in a thread-pool thread.
    - progress_callback is called from that worker thread; callers must ensure
      they are Qt-safe (e.g. emit a signal from the worker rather than touching
      widgets directly).
    - cancel() is safe to call from any thread.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Optional

from .engine import InferenceEngine, ProgressCallback
from .errors import BackendUnavailableError, ValidationError
from .models import GenerationRequest, GenerationResult, GenerationStatus

logger = logging.getLogger("nova.inference.service")


class InferenceService:
    """Thread-safe orchestrator wrapping a single InferenceEngine."""

    def __init__(self, engine: InferenceEngine, max_workers: int = 1) -> None:
        self._engine = engine
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="nova-inference")
        self._cancel_event: Optional[threading.Event] = None
        self._lock = threading.Lock()

        logger.info("InferenceService initialised with backend '%s'", engine.backend_name())

    # ---------------------------------------------------------------------- #
    # Public API                                                               #
    # ---------------------------------------------------------------------- #

    @property
    def engine(self) -> InferenceEngine:
        return self._engine

    def is_available(self) -> bool:
        """True when the engine reports itself ready."""
        return self._engine.is_available()

    def submit(
        self,
        request: GenerationRequest,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Future[GenerationResult]:
        """Validate and submit a generation request asynchronously.

        Returns a ``Future`` that resolves to a ``GenerationResult``.
        Raises ``ValidationError`` synchronously if the request is invalid.
        Raises ``BackendUnavailableError`` if the engine is not ready.
        """
        # Synchronous validation — fail fast before touching the thread pool
        errors = request.validate()
        if errors:
            raise ValidationError(errors)

        if not self._engine.is_available():
            raise BackendUnavailableError(
                f"Backend '{self._engine.backend_name()}' is not available."
            )

        with self._lock:
            # One generation at a time — create a fresh cancel event per job
            cancel_event = threading.Event()
            self._cancel_event = cancel_event

        logger.info(
            "Submitting generation — prompt=%r steps=%d",
            request.prompt[:60],
            request.steps,
        )

        future = self._executor.submit(
            self._run, request, progress_callback, cancel_event
        )
        return future

    def cancel(self) -> None:
        """Signal the currently running generation to stop."""
        with self._lock:
            if self._cancel_event:
                logger.info("Cancellation requested.")
                self._cancel_event.set()

    def shutdown(self) -> None:
        """Cleanly shut down the thread pool (call on application exit)."""
        self.cancel()
        self._executor.shutdown(wait=False)

    # ---------------------------------------------------------------------- #
    # Internal                                                                 #
    # ---------------------------------------------------------------------- #

    def _run(
        self,
        request: GenerationRequest,
        progress_callback: Optional[ProgressCallback],
        cancel_event: threading.Event,
    ) -> GenerationResult:
        """Execute generation inside the thread-pool thread."""
        try:
            result = self._engine.generate(
                request,
                progress_callback=progress_callback,
                cancel_event=cancel_event,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error in inference engine")
            result = GenerationResult(
                request=request,
                status=GenerationStatus.ERROR,
                error=f"Unexpected error: {exc}",
            )
        finally:
            with self._lock:
                # Clear the cancel event reference after the job finishes
                if self._cancel_event is cancel_event:
                    self._cancel_event = None

        return result
