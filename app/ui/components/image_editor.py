"""
ImageEditor — component for loading a source image and drawing a mask for inpainting.
"""
from __future__ import annotations

import io
from typing import Optional

from PySide6.QtCore import Qt, QPoint, QSize
from PySide6.QtGui import QImage, QPainter, QPen, QColor, QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QFileDialog,
    QLabel,
    QSlider,
    QSizePolicy,
)


class DrawingCanvas(QWidget):
    """A canvas that displays a source image and allows drawing a mask over it."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(256, 256)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._source_image = QImage()
        self._mask_image = QImage()
        
        # UI state
        self._mode = "text-to-image"
        self._brush_size = 20
        self._drawing = False
        self._last_point = QPoint()

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self.update()

    def set_brush_size(self, size: int) -> None:
        self._brush_size = size

    def load_image(self, path: str) -> bool:
        img = QImage(path)
        if img.isNull():
            return False
        
        # Convert to ARGB32 to ensure consistency
        self._source_image = img.convertToFormat(QImage.Format_ARGB32)
        # Create a mask image of the same size, filled with transparent black
        self._mask_image = QImage(self._source_image.size(), QImage.Format_ARGB32)
        self._mask_image.fill(Qt.transparent)
        
        self.update()
        return True

    def clear_mask(self) -> None:
        if not self._mask_image.isNull():
            self._mask_image.fill(Qt.transparent)
            self.update()

    def has_image(self) -> bool:
        return not self._source_image.isNull()

    def get_source_bytes(self) -> Optional[bytes]:
        if self._source_image.isNull():
            return None
        buffer = io.BytesIO()
        self._source_image.save(buffer, format="PNG")
        return buffer.getvalue()

    def get_mask_bytes(self) -> Optional[bytes]:
        """Return the mask as a white-on-black image (white = masked area)."""
        if self._mask_image.isNull():
            return None
        
        # Convert our transparent/white mask into a black/white mask for the backend
        export_mask = QImage(self._mask_image.size(), QImage.Format_Grayscale8)
        export_mask.fill(Qt.black)
        
        painter = QPainter(export_mask)
        # We just draw the mask image over the black background. 
        # The mask image has white pixels where drawn, so it will show up as white on black.
        painter.drawImage(0, 0, self._mask_image)
        painter.end()

        buffer = io.BytesIO()
        export_mask.save(buffer, format="PNG")
        return buffer.getvalue()

    # -- Drawing Events ---------------------------------------------------- #

    def mousePressEvent(self, event) -> None:
        if self._mode != "inpainting" or self._source_image.isNull():
            return
        if event.button() == Qt.LeftButton:
            self._drawing = True
            self._last_point = self._map_to_image(event.pos())

    def mouseMoveEvent(self, event) -> None:
        if not self._drawing or self._mode != "inpainting" or self._source_image.isNull():
            return
        
        current_point = self._map_to_image(event.pos())
        self._draw_line_on_mask(self._last_point, current_point)
        self._last_point = current_point
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drawing = False

    def _map_to_image(self, widget_pos: QPoint) -> QPoint:
        """Map a coordinate from the widget space to the image space."""
        # Calculate how the image is scaled and offset in the widget
        img_w, img_h = self._source_image.width(), self._source_image.height()
        widget_w, widget_h = self.width(), self.height()

        # Find the scaled size keeping aspect ratio
        scaled_size = QSize(img_w, img_h).scaled(self.size(), Qt.KeepAspectRatio)
        
        x_offset = (widget_w - scaled_size.width()) // 2
        y_offset = (widget_h - scaled_size.height()) // 2

        # Remove offset
        x_img = widget_pos.x() - x_offset
        y_img = widget_pos.y() - y_offset

        # Scale back to original image size
        x_orig = int(x_img * (img_w / scaled_size.width()))
        y_orig = int(y_img * (img_h / scaled_size.height()))

        return QPoint(x_orig, y_orig)

    def _draw_line_on_mask(self, p1: QPoint, p2: QPoint) -> None:
        painter = QPainter(self._mask_image)
        # Use white for the mask, it will be rendered with opacity in paintEvent
        pen = QPen(Qt.white, self._brush_size, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(p1, p2)
        painter.end()

    # -- Painting ---------------------------------------------------------- #

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._source_image.isNull():
            # Draw placeholder text
            painter = QPainter(self)
            painter.setPen(Qt.gray)
            painter.drawText(self.rect(), Qt.AlignCenter, "No image loaded.\nClick 'Import Image' below.")
            painter.end()
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Scale keeping aspect ratio
        scaled_size = self._source_image.size().scaled(self.size(), Qt.KeepAspectRatio)
        x_offset = (self.width() - scaled_size.width()) // 2
        y_offset = (self.height() - scaled_size.height()) // 2
        target_rect = self.rect().intersected(
            QWidget().rect() # Just to construct a rect, actually we want the bounds
        )
        target_rect.setX(x_offset)
        target_rect.setY(y_offset)
        target_rect.setWidth(scaled_size.width())
        target_rect.setHeight(scaled_size.height())

        # Draw source image
        painter.drawImage(target_rect, self._source_image)

        # Draw mask on top (if in inpainting mode)
        if self._mode == "inpainting" and not self._mask_image.isNull():
            # We want to draw the mask semi-transparently so the user can see what they are masking.
            # We create a temporary pixmap to draw the mask with opacity
            mask_pixmap = QPixmap.fromImage(self._mask_image)
            painter.setOpacity(0.5)
            painter.drawPixmap(target_rect, mask_pixmap)
            painter.setOpacity(1.0)

        painter.end()


class ImageEditor(QWidget):
    """Component that wraps the DrawingCanvas and adds controls."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ImageEditor")
        self._mode = "text-to-image"
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.canvas = DrawingCanvas()
        layout.addWidget(self.canvas)

        # Controls row
        self.controls_layout = QHBoxLayout()
        
        self.btn_import = QPushButton("Import Image")
        self.btn_import.setObjectName("SecondaryButton")
        self.btn_import.clicked.connect(self._on_import_clicked)
        self.controls_layout.addWidget(self.btn_import)
        
        self.btn_clear_mask = QPushButton("Clear Mask")
        self.btn_clear_mask.setObjectName("SecondaryButton")
        self.btn_clear_mask.clicked.connect(self.canvas.clear_mask)
        self.controls_layout.addWidget(self.btn_clear_mask)
        
        self.lbl_brush = QLabel("Brush Size:")
        self.controls_layout.addWidget(self.lbl_brush)
        
        self.slider_brush = QSlider(Qt.Horizontal)
        self.slider_brush.setRange(5, 100)
        self.slider_brush.setValue(20)
        self.slider_brush.setFixedWidth(100)
        self.slider_brush.valueChanged.connect(self.canvas.set_brush_size)
        self.controls_layout.addWidget(self.slider_brush)
        
        self.controls_layout.addStretch()
        layout.addLayout(self.controls_layout)
        
        self.set_mode("text-to-image")

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self.canvas.set_mode(mode)
        
        # Hide the entire component if text-to-image
        self.setVisible(mode != "text-to-image")
        
        # Mask controls only visible in inpainting mode
        is_inpainting = (mode == "inpainting")
        self.btn_clear_mask.setVisible(is_inpainting)
        self.lbl_brush.setVisible(is_inpainting)
        self.slider_brush.setVisible(is_inpainting)

    def _on_import_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image",
            "",
            "Images (*.png *.jpg *.jpeg);;All Files (*)"
        )
        if path:
            self.canvas.load_image(path)

    def get_source_bytes(self) -> Optional[bytes]:
        return self.canvas.get_source_bytes()

    def get_mask_bytes(self) -> Optional[bytes]:
        return self.canvas.get_mask_bytes()
