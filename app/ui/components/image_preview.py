"""
ImagePreview — widget for displaying generation states and results.

Handles four states: Idle, Generating, Completed (with real image), Error.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget, QPushButton, QFileDialog

from app.inference import GenerationResult

logger = logging.getLogger("nova.ui.image_preview")


class ImagePreview(QWidget):
    """Preview area that reflects the current generation state.

    When generation completes, renders the actual PNG image bytes from
    GenerationResult.image_data into a scaled QPixmap.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ImagePreviewContainer")
        self._setup_ui()
        self.set_state_idle()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # Image display label — fills available space
        self.lbl_image = QLabel()
        self.lbl_image.setObjectName("ImagePreviewLabel")
        self.lbl_image.setAlignment(Qt.AlignCenter)
        self.lbl_image.setWordWrap(True)
        self.lbl_image.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.lbl_image.setMinimumSize(200, 200)
        layout.addWidget(self.lbl_image, stretch=1)

        # Metadata line below image
        self.lbl_meta = QLabel()
        self.lbl_meta.setObjectName("ImagePreviewMeta")
        self.lbl_meta.setAlignment(Qt.AlignCenter)
        self.lbl_meta.setWordWrap(True)
        self.lbl_meta.hide()
        layout.addWidget(self.lbl_meta)

        # Save button
        self.btn_save = QPushButton("Save Image")
        self.btn_save.setObjectName("SecondaryButton")
        self.btn_save.clicked.connect(self._on_save_clicked)
        self.btn_save.hide()
        layout.addWidget(self.btn_save)

    # ------------------------------------------------------------------ #
    # State setters — called from the Qt main thread                      #
    # ------------------------------------------------------------------ #

    def set_state_idle(self) -> None:
        self._clear_pixmap()
        self.lbl_image.setText("Your generated image will appear here.")
        self.lbl_image.setProperty("previewState", "idle")
        self._refresh_style(self.lbl_image)
        self.lbl_meta.hide()
        self.btn_save.hide()

    def set_state_generating(self) -> None:
        self._clear_pixmap()
        self.lbl_image.setText("Generating…")
        self.lbl_image.setProperty("previewState", "generating")
        self._refresh_style(self.lbl_image)
        self.lbl_meta.hide()
        self.btn_save.hide()

    def set_state_completed(self, result: GenerationResult) -> None:
        """Render the generated image and show metadata."""
        pixmap = self._result_to_pixmap(result)

        if pixmap is not None and not pixmap.isNull():
            self.lbl_image.setText("")
            self.lbl_image.setPixmap(self._scale_pixmap(pixmap))
            self.lbl_image.setProperty("previewState", "completed")
            self._refresh_style(self.lbl_image)
        else:
            # Fallback: no image data — show text confirmation
            self.lbl_image.setText("✓ Generation Complete")
            self.lbl_image.setProperty("previewState", "completed")
            self._refresh_style(self.lbl_image)

        if self._current_pixmap is not None and not self._current_pixmap.isNull():
            self.btn_save.show()
        else:
            self.btn_save.hide()

        # Metadata row
        meta_parts: list[str] = []
        if result.seed_used >= 0:
            meta_parts.append(f"Seed {result.seed_used}")
        if result.duration_seconds > 0:
            meta_parts.append(f"{result.duration_seconds:.1f}s")
        backend = result.metadata.get("backend", "")
        if backend:
            meta_parts.append(backend)
        if result.request.width and result.request.height:
            meta_parts.append(f"{result.request.width}×{result.request.height}")

        self.lbl_meta.setText("  ·  ".join(meta_parts))
        self.lbl_meta.show()

    def set_state_error(self, message: str) -> None:
        self._clear_pixmap()
        self.lbl_image.setText(f"⚠  {message}")
        self.lbl_image.setProperty("previewState", "error")
        self._refresh_style(self.lbl_image)
        self.lbl_meta.hide()
        self.btn_save.hide()

    # ------------------------------------------------------------------ #
    # Resize event — re-scale when the widget is resized                 #
    # ------------------------------------------------------------------ #

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # Re-scale the currently displayed pixmap (if any) to fill the new size
        if self._current_pixmap is not None and not self._current_pixmap.isNull():
            self.lbl_image.setPixmap(self._scale_pixmap(self._current_pixmap))

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _on_save_clicked(self) -> None:
        if self._current_pixmap is None or self._current_pixmap.isNull():
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Image",
            "",
            "Images (*.png *.jpg *.jpeg);;All Files (*)"
        )
        if path:
            self._current_pixmap.save(path)

    _current_pixmap: QPixmap | None = None

    def _clear_pixmap(self) -> None:
        self._current_pixmap = None
        self.lbl_image.setPixmap(QPixmap())  # clear any previous image

    def _scale_pixmap(self, pixmap: QPixmap) -> QPixmap:
        """Scale pixmap to fit the label while keeping aspect ratio."""
        available = self.lbl_image.size()
        # Leave 8px padding on each side
        target = available.shrunkBy(
            __import__("PySide6.QtCore", fromlist=["QMargins"]).QMargins(8, 8, 8, 8)
        )
        if target.width() <= 0 or target.height() <= 0:
            return pixmap
        return pixmap.scaled(
            target,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )

    def _result_to_pixmap(self, result: GenerationResult) -> QPixmap | None:
        """Convert GenerationResult image data to a QPixmap."""
        # Try in-memory bytes first
        if result.image_data:
            try:
                pixmap = QPixmap()
                if pixmap.loadFromData(result.image_data):
                    self._current_pixmap = pixmap
                    return pixmap
                else:
                    logger.warning("loadFromData failed — image_data may be corrupt.")
            except Exception as exc:
                logger.warning("Failed to load image_data: %s", exc)

        # Fall back to a file path
        if result.image_path:
            try:
                pixmap = QPixmap(result.image_path)
                if not pixmap.isNull():
                    self._current_pixmap = pixmap
                    return pixmap
            except Exception as exc:
                logger.warning("Failed to load image_path '%s': %s", result.image_path, exc)

        return None

    @staticmethod
    def _refresh_style(widget: QLabel) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
