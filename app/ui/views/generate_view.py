"""
Generate screen — primary user-facing view for image generation.

Receives ApplicationService via constructor (dependency injection).
Does not import any model, engine, or hardware class directly.

Responsibilities:
  - Collect prompt, negative prompt, and settings from the user.
  - Pre-check that a compatible model is installed before submitting.
  - Submit GenerationRequest to InferenceService via GenerationWorker.
  - Display progress, results, and errors in the ImagePreview pane.
  - Lock inputs during generation; restore them on completion/cancel.
"""
from __future__ import annotations

import logging
import time

from PySide6.QtCore import Qt, QThreadPool, QTimer, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QProgressBar,
    QComboBox,
)

from app.core.app_service import ApplicationService
from app.inference import (
    GenerationProgress,
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
)
from app.models.spec import ModelStatus
from app.ui.components.image_preview import ImagePreview
from app.ui.components.settings_panel import SettingsPanel
from app.ui.components.image_editor import ImageEditor
from app.ui.worker import GenerationWorker

logger = logging.getLogger("nova.ui.generate_view")

# Human-readable labels for each model status shown in the UI.
_STATUS_TEXT: dict[ModelStatus, tuple[str, str]] = {
    # (label text, CSS property value for styling)
    ModelStatus.NOT_INSTALLED: ("Model not installed — run with --real-model and download weights", "error"),
    ModelStatus.INSTALLED:     ("Model installed — ready to load (use --real-model to enable)", "warning"),
    ModelStatus.LOADED:        ("Model loaded and ready", "ready"),
    ModelStatus.ERROR:         ("Model error — check logs", "error"),
}


class GenerateView(QWidget):
    """Main Generate screen — prompt → settings → generate → preview."""

    def __init__(self, app_service: ApplicationService) -> None:
        super().__init__()
        self._service = app_service
        self._active_worker: GenerationWorker | None = None
        self._start_time: float = 0.0
        self._last_progress_msg: str = ""
        self._current_mode = "text-to-image"
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer_tick)
        self._setup_ui()
        self._prime_from_model()

        # Service signals
        self._service.settings_service.settings_changed.connect(lambda _: self._prime_from_model())
        self._service.model_service.model_updated.connect(lambda _: self._prime_from_model())
        self._service.model_service.model_removed.connect(lambda _: self._prime_from_model())
        self._service.model_service.registry_refreshed.connect(self._prime_from_model)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._prime_from_model()

    # ---------------------------------------------------------------------- #
    # UI construction                                                          #
    # ---------------------------------------------------------------------- #

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(8)

        # ---- Model status bar -------------------------------------------- #
        self.lbl_model_status = QLabel()
        self.lbl_model_status.setObjectName("ModelStatusLabel")
        self.lbl_model_status.setAlignment(Qt.AlignCenter)
        root.addWidget(self.lbl_model_status)

        # ---- Main splitter ------------------------------------------------ #
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ---- Left pane --------------------------------------------------- #
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 12, 0)
        left_layout.setSpacing(10)
        
        # Mode selector
        mode_layout = QHBoxLayout()
        mode_label = QLabel("Mode:")
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["Text-to-Image", "Image-to-Image", "Inpainting"])
        self.cmb_mode.currentIndexChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.cmb_mode)
        mode_layout.addStretch()
        left_layout.addLayout(mode_layout)
        
        # Image Editor
        self.image_editor = ImageEditor()
        left_layout.addWidget(self.image_editor)

        # Prompt
        prompt_label = QLabel("Prompt")
        prompt_label.setObjectName("FieldLabel")
        self.txt_prompt = QTextEdit()
        self.txt_prompt.setObjectName("PromptInput")
        self.txt_prompt.setPlaceholderText("Describe the image you want to generate…")
        self.txt_prompt.setMinimumHeight(110)
        self.txt_prompt.setMaximumHeight(200)
        left_layout.addWidget(prompt_label)
        left_layout.addWidget(self.txt_prompt)

        # Negative prompt
        neg_label = QLabel("Negative Prompt")
        neg_label.setObjectName("FieldLabel")
        self.txt_negative = QTextEdit()
        self.txt_negative.setObjectName("PromptInput")
        self.txt_negative.setPlaceholderText("Elements to avoid…")
        self.txt_negative.setMaximumHeight(70)
        left_layout.addWidget(neg_label)
        left_layout.addWidget(self.txt_negative)

        # Settings
        self.settings_panel = SettingsPanel()
        left_layout.addWidget(self.settings_panel)

        # Progress bar (hidden when idle)
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("GenerationProgress")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        left_layout.addWidget(self.progress_bar)

        # Progress status text (hidden when idle)
        self.lbl_progress_text = QLabel("")
        self.lbl_progress_text.setObjectName("ProgressStatusLabel")
        self.lbl_progress_text.setAlignment(Qt.AlignCenter)
        self.lbl_progress_text.hide()
        left_layout.addWidget(self.lbl_progress_text)

        # Action buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_generate = QPushButton("Generate")
        self.btn_generate.setObjectName("PrimaryButton")
        self.btn_generate.setMinimumHeight(46)
        self.btn_generate.setCursor(Qt.PointingHandCursor)
        self.btn_generate.clicked.connect(self._on_generate_clicked)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("SecondaryButton")
        self.btn_cancel.setMinimumHeight(46)
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)

        btn_row.addWidget(self.btn_generate)
        btn_row.addWidget(self.btn_cancel)
        left_layout.addLayout(btn_row)
        left_layout.addStretch()

        # ---- Right pane -------------------------------------------------- #
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 0, 0, 0)

        self.preview = ImagePreview()
        right_layout.addWidget(self.preview)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([420, 580])
        root.addWidget(splitter)

    # ---------------------------------------------------------------------- #
    # Model status priming                                                     #
    # ---------------------------------------------------------------------- #

    def _prime_from_model(self) -> None:
        """Apply the active model's recommended defaults to the UI."""
        registry = self._service.model_registry
        settings = self._service.settings

        spec = registry.get_or_none(settings.default_model_id)
        if spec is None:
            self._update_model_status_label(
                f"No model registered for id='{settings.default_model_id}'", "error"
            )
            return

        # Prime settings panel
        self.settings_panel.apply_model_spec(spec)

        # Show model status
        status_text, status_prop = _STATUS_TEXT.get(
            spec.status, (f"Unknown status: {spec.status}", "error")
        )

        # Hardware compatibility check
        hw = self._service.hardware
        rec = self._service.model_selection.evaluate(hw, [spec])
        compat = rec.evaluations.get(spec.model_id)

        if compat and not compat.is_compatible:
            status_prop = "error"
            status_text += " (Incompatible Hardware)"
            self.preview.set_state_error(
                f"Hardware Incompatible: {' '.join(compat.reasons)}\n\n"
                f"You can still try generating, but it may fail or be very slow."
            )
        elif compat and compat.is_compatible and rec.recommended_model_id == spec.model_id:
            status_text += " (Recommended)"

        self._update_model_status_label(
            f"{spec.display_name}  ·  {status_text}",
            status_prop,
        )

        self._check_mode_capability()

    def _check_mode_capability(self) -> None:
        """Check if the selected mode is supported by the current model."""
        registry = self._service.model_registry
        settings = self._service.settings
        spec = registry.get_or_none(settings.default_model_id)

        if spec is None or not self._service.inference.is_available():
            self.btn_generate.setEnabled(False)
            self.btn_generate.setToolTip("Model is not available. Please check settings.")
            self._show_model_unavailable_error()
            return
            
        if self._current_mode not in spec.capabilities:
            self.btn_generate.setEnabled(False)
            self.btn_generate.setToolTip(f"Mode not supported by '{spec.display_name}'")
            self.preview.set_state_error(
                f"Capability Not Supported\n\n"
                f"The model '{spec.display_name}' does not support {self._current_mode}.\n"
                f"Please switch to a supported mode or select a different model."
            )
        else:
            self.btn_generate.setEnabled(True)
            self.btn_generate.setToolTip("")
            self.preview.set_state_idle()

    def _update_model_status_label(self, text: str, status: str) -> None:
        self.lbl_model_status.setText(text)
        self.lbl_model_status.setProperty("modelStatus", status)
        self.lbl_model_status.style().unpolish(self.lbl_model_status)
        self.lbl_model_status.style().polish(self.lbl_model_status)

    def apply_history_record(self, record) -> None:
        """Populate controls from a history generation record."""
        if record.prompt:
            self.txt_prompt.setPlainText(record.prompt)
        if record.negative_prompt is not None:
            self.txt_negative.setPlainText(record.negative_prompt)

        mode_str = getattr(record, "mode", "text-to-image") or "text-to-image"
        mode_idx = {"text-to-image": 0, "image-to-image": 1, "inpainting": 2}.get(mode_str, 0)
        self.cmb_mode.setCurrentIndex(mode_idx)

        settings = {
            "width": record.width,
            "height": record.height,
            "steps": record.steps,
            "guidance": record.guidance,
            "seed": record.seed,
            "denoising_strength": getattr(record, "denoising_strength", 0.5),
        }
        self.settings_panel.set_settings(settings)

    def apply_trend(self, trend) -> None:
        """Populate prompt and recommended settings from a Trend template without generating."""
        if trend.prompt:
            self.txt_prompt.setPlainText(trend.prompt)
        if trend.negative_prompt is not None:
            self.txt_negative.setPlainText(trend.negative_prompt)

        rec = getattr(trend, "recommended_settings", {}) or {}
        mode_str = rec.get("mode", "text-to-image")
        mode_idx = {"text-to-image": 0, "image-to-image": 1, "inpainting": 2}.get(mode_str, 0)
        self.cmb_mode.setCurrentIndex(mode_idx)

        settings = {}
        if "width" in rec:
            settings["width"] = rec["width"]
        if "height" in rec:
            settings["height"] = rec["height"]
        if "steps" in rec:
            settings["steps"] = rec["steps"]
        if "guidance" in rec:
            settings["guidance"] = rec["guidance"]
        if "seed" in rec:
            settings["seed"] = rec["seed"]
        if "denoising_strength" in rec:
            settings["denoising_strength"] = rec["denoising_strength"]

        if settings:
            self.settings_panel.set_settings(settings)

    # ---------------------------------------------------------------------- #
    # Slots                                                                    #
    # ---------------------------------------------------------------------- #

    @Slot(int)
    def _on_mode_changed(self, index: int) -> None:
        mode_str = self.cmb_mode.currentText().lower()
        if mode_str == "text-to-image":
            self._current_mode = "text-to-image"
        elif mode_str == "image-to-image":
            self._current_mode = "image-to-image"
        elif mode_str == "inpainting":
            self._current_mode = "inpainting"
            
        self.image_editor.set_mode(self._current_mode)
        self.settings_panel.set_mode(self._current_mode)
        self._check_mode_capability()

    @Slot()
    def _on_generate_clicked(self) -> None:
        prompt = self.txt_prompt.toPlainText().strip()
        negative = self.txt_negative.toPlainText().strip()
        settings = self.settings_panel.get_settings()

        request = GenerationRequest(
            mode=self._current_mode,
            prompt=prompt,
            negative_prompt=negative,
            width=settings["width"],
            height=settings["height"],
            steps=settings["steps"],
            guidance=settings["guidance"],
            seed=settings["seed"],
            denoising_strength=settings.get("denoising_strength", 0.5),
            source_image_data=self.image_editor.get_source_bytes(),
            mask_image_data=self.image_editor.get_mask_bytes(),
        )

        # Client-side validation before hitting the service
        errors = request.validate()
        if errors:
            self.preview.set_state_error(" · ".join(errors))
            return

        # Pre-check: is a model available on the engine?
        if not self._service.inference.is_available():
            self._show_model_unavailable_error()
            return

        self._set_generating_state(request.steps)

        worker = GenerationWorker(self._service.inference, request)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_finished)
        self._active_worker = worker
        QThreadPool.globalInstance().start(worker)

    def _show_model_unavailable_error(self) -> None:
        """Show a friendly error when no model is loaded."""
        registry = self._service.model_registry
        settings = self._service.settings
        spec = registry.get_or_none(settings.default_model_id)

        if spec is None:
            msg = "No model is configured. Check your settings."
        elif spec.status == ModelStatus.NOT_INSTALLED:
            msg = (
                f"'{spec.display_name}' is not installed.\n\n"
                f"Download the model with:\n"
                f"  huggingface-cli download {spec.source} "
                f"--local-dir ~/.nova/models/{spec.model_id}\n\n"
                f"Then launch NOVA with: python main.py --real-model"
            )
        else:
            msg = (
                f"'{spec.display_name}' is not loaded.\n\n"
                f"Launch NOVA with: python main.py --real-model"
            )
        self.preview.set_state_error(msg)

    @Slot()
    def _on_cancel_clicked(self) -> None:
        logger.info("User requested cancellation.")
        self.btn_cancel.setEnabled(False)
        self._last_progress_msg = "Cancelling…"
        self._on_timer_tick()
        self._service.inference.cancel()

    @Slot(GenerationProgress)
    def _on_progress(self, progress: GenerationProgress) -> None:
        if progress.total_steps > 0:
            self.progress_bar.setRange(0, 100)
            pct = int(progress.fraction * 100)
            self.progress_bar.setValue(pct)
        else:
            self.progress_bar.setRange(0, 0)
        if progress.message:
            self._last_progress_msg = progress.message
            self._on_timer_tick()

    @Slot(GenerationResult)
    def _on_finished(self, result: GenerationResult) -> None:
        self._set_idle_state()

        if result.success:
            self.preview.set_state_completed(result)
            logger.info(
                "Generation finished — seed=%d duration=%.1fs",
                result.seed_used,
                result.duration_seconds,
            )
        elif result.cancelled:
            self.preview.set_state_cancelled()
            logger.info("Generation cancelled by user.")
        else:
            # Sanitise the error: don't show raw internal exception strings
            error_msg = _sanitise_error(result.error)
            self.preview.set_state_error(error_msg)
            logger.warning("Generation error: %s", result.error)

    # ---------------------------------------------------------------------- #
    # State transitions                                                        #
    # ---------------------------------------------------------------------- #

    def _set_generating_state(self, total_steps: int) -> None:
        self.btn_generate.setEnabled(False)
        self.btn_generate.setText("Generating…")
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate mode
        self.progress_bar.show()
        self._last_progress_msg = "Preparing…"
        self.lbl_progress_text.setText(self._last_progress_msg)
        self.lbl_progress_text.show()
        self._start_time = time.time()
        self._timer.start(100)
        # Lock prompt and settings inputs
        self.txt_prompt.setReadOnly(True)
        self.txt_negative.setReadOnly(True)
        self.settings_panel.set_enabled_all(False)
        self.preview.set_state_generating()

    def _set_idle_state(self) -> None:
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("Generate")
        self.btn_cancel.setEnabled(False)
        self.progress_bar.hide()
        self.progress_bar.setValue(0)
        self.lbl_progress_text.hide()
        self.lbl_progress_text.setText("")
        # Restore inputs
        self.txt_prompt.setReadOnly(False)
        self.txt_negative.setReadOnly(False)
        self.settings_panel.set_enabled_all(True)
        self._active_worker = None
        self._timer.stop()

    def _on_timer_tick(self) -> None:
        elapsed = time.time() - self._start_time
        self.lbl_progress_text.setText(f"{self._last_progress_msg} ({elapsed:.1f}s)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitise_error(raw: str | None) -> str:
    """Return a user-friendly error string.

    Strips raw Python exception class names and tracebacks that would
    confuse end users while retaining the meaningful message content.
    """
    if not raw:
        return "An unknown error occurred during generation."
    # Trim very long strings — show first 400 chars
    if len(raw) > 400:
        raw = raw[:400] + "…"
    return raw
