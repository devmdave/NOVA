"""
HistoryView — gallery and details view for local generation history.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.app_service import ApplicationService
from app.history.models import GenerationRecord

logger = logging.getLogger("nova.ui.history_view")


class HistoryView(QWidget):
    """Gallery and inspection view for past image generations."""

    reuse_requested = Signal(object)  # Emits GenerationRecord when user clicks "Reuse Parameters"

    def __init__(self, app_service: ApplicationService) -> None:
        super().__init__()
        self._service = app_service
        self._history_service = app_service.history_service
        self._selected_record: Optional[GenerationRecord] = None
        self._records: list[GenerationRecord] = []

        self._setup_ui()

        # Connect history service signals for auto-refresh
        self._history_service.record_added.connect(self._on_record_added)
        self._history_service.record_deleted.connect(self._on_record_deleted)
        self._history_service.history_cleared.connect(self.reload_history)

        self.reload_history()

    # ---------------------------------------------------------------------- #
    # UI Setup                                                                 #
    # ---------------------------------------------------------------------- #

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # Header bar
        header_layout = QHBoxLayout()
        lbl_title = QLabel("Generation History")
        lbl_title.setObjectName("ViewTitle")
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(lbl_title)

        header_layout.addStretch()

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Filter by prompt keyword…")
        self.txt_search.setClearButtonEnabled(True)
        self.txt_search.setFixedWidth(240)
        self.txt_search.textChanged.connect(self._on_filter_changed)
        header_layout.addWidget(self.txt_search)

        btn_clear = QPushButton("Clear History")
        btn_clear.setObjectName("SecondaryButton")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.clicked.connect(self._on_clear_clicked)
        header_layout.addWidget(btn_clear)

        root.addLayout(header_layout)

        # Main splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ---- Left Pane: Gallery ------------------------------------------ #
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 10, 0)
        left_layout.setSpacing(8)

        self.lbl_count = QLabel("0 generations stored")
        self.lbl_count.setStyleSheet("color: #888888; font-size: 12px;")
        left_layout.addWidget(self.lbl_count)

        self.list_gallery = QListWidget()
        self.list_gallery.setObjectName("HistoryGallery")
        self.list_gallery.setViewMode(QListWidget.IconMode)
        self.list_gallery.setIconSize(QSize(160, 160))
        self.list_gallery.setResizeMode(QListWidget.Adjust)
        self.list_gallery.setSpacing(12)
        self.list_gallery.setMovement(QListWidget.Static)
        self.list_gallery.setStyleSheet(
            "QListWidget::item { padding: 6px; border-radius: 6px; background-color: #1e1e24; }"
            "QListWidget::item:selected { background-color: #2b3a55; border: 1px solid #4a7bb0; }"
        )
        self.list_gallery.currentItemChanged.connect(self._on_item_selected)
        left_layout.addWidget(self.list_gallery)

        # Empty state label
        self.lbl_empty = QLabel("No generation history yet.\nGenerated images will appear here.")
        self.lbl_empty.setAlignment(Qt.AlignCenter)
        self.lbl_empty.setStyleSheet("color: #777; font-size: 14px; margin: 40px;")
        left_layout.addWidget(self.lbl_empty)

        # ---- Right Pane: Detail Inspection ------------------------------- #
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 0, 0, 0)
        right_layout.setSpacing(12)

        # Large image preview
        self.lbl_preview = QLabel("Select a generation to preview")
        self.lbl_preview.setAlignment(Qt.AlignCenter)
        self.lbl_preview.setMinimumHeight(280)
        self.lbl_preview.setStyleSheet(
            "background-color: #16161a; border: 1px solid #2a2a30; border-radius: 8px;"
        )
        right_layout.addWidget(self.lbl_preview)

        # Action Buttons
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)

        self.btn_reuse = QPushButton("Reuse Parameters")
        self.btn_reuse.setObjectName("PrimaryButton")
        self.btn_reuse.setCursor(Qt.PointingHandCursor)
        self.btn_reuse.setEnabled(False)
        self.btn_reuse.clicked.connect(self._on_reuse_clicked)

        self.btn_export = QPushButton("Export Image")
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._on_export_clicked)

        self.btn_open = QPushButton("Open File")
        self.btn_open.setCursor(Qt.PointingHandCursor)
        self.btn_open.setEnabled(False)
        self.btn_open.clicked.connect(self._on_open_clicked)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setStyleSheet("background-color: #8b2626; color: white; border-radius: 4px; padding: 6px 12px;")
        self.btn_delete.setCursor(Qt.PointingHandCursor)
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._on_delete_clicked)

        actions_layout.addWidget(self.btn_reuse)
        actions_layout.addWidget(self.btn_export)
        actions_layout.addWidget(self.btn_open)
        actions_layout.addWidget(self.btn_delete)
        right_layout.addLayout(actions_layout)

        # Metadata Group
        meta_group = QGroupBox("Generation Details")
        form_layout = QFormLayout(meta_group)
        form_layout.setSpacing(8)

        self.lbl_model_val = QLabel("—")
        self.lbl_mode_val = QLabel("—")
        self.lbl_timestamp_val = QLabel("—")
        self.lbl_dim_val = QLabel("—")
        self.lbl_steps_val = QLabel("—")
        self.lbl_guidance_val = QLabel("—")
        self.lbl_seed_val = QLabel("—")
        self.lbl_denoising_val = QLabel("—")
        self.lbl_duration_val = QLabel("—")

        form_layout.addRow("Model:", self.lbl_model_val)
        form_layout.addRow("Mode:", self.lbl_mode_val)
        form_layout.addRow("Timestamp:", self.lbl_timestamp_val)
        form_layout.addRow("Dimensions:", self.lbl_dim_val)
        form_layout.addRow("Steps:", self.lbl_steps_val)
        form_layout.addRow("Guidance / CFG:", self.lbl_guidance_val)
        form_layout.addRow("Seed:", self.lbl_seed_val)
        form_layout.addRow("Denoising:", self.lbl_denoising_val)
        form_layout.addRow("Generation Time:", self.lbl_duration_val)

        right_layout.addWidget(meta_group)

        # Prompt & Negative Prompt
        prompt_group = QGroupBox("Prompt")
        prompt_layout = QVBoxLayout(prompt_group)
        self.txt_prompt_val = QTextEdit()
        self.txt_prompt_val.setReadOnly(True)
        self.txt_prompt_val.setMaximumHeight(90)
        prompt_layout.addWidget(self.txt_prompt_val)
        right_layout.addWidget(prompt_group)

        neg_group = QGroupBox("Negative Prompt")
        neg_layout = QVBoxLayout(neg_group)
        self.txt_neg_val = QTextEdit()
        self.txt_neg_val.setReadOnly(True)
        self.txt_neg_val.setMaximumHeight(60)
        neg_layout.addWidget(self.txt_neg_val)
        right_layout.addWidget(neg_group)

        right_layout.addStretch()
        right_scroll.setWidget(right_widget)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_scroll)
        splitter.setSizes([500, 500])

        root.addWidget(splitter)

    # ---------------------------------------------------------------------- #
    # Data Loading & Display                                                   #
    # ---------------------------------------------------------------------- #

    def reload_history(self) -> None:
        """Reload records from history service into gallery."""
        self._records = self._history_service.get_history()
        self._populate_gallery(self._records)

    def _populate_gallery(self, records: list[GenerationRecord]) -> None:
        """Populate list widget with thumbnail items."""
        self.list_gallery.clear()
        filter_text = self.txt_search.text().strip().lower()

        visible_count = 0
        for record in records:
            if filter_text and filter_text not in record.prompt.lower():
                continue

            item = QListWidgetItem()
            thumb_path = record.thumbnail_path or record.image_path

            if os.path.exists(thumb_path):
                pixmap = QPixmap(thumb_path)
                if not pixmap.isNull():
                    item.setIcon(QIcon(pixmap))

            # Truncate prompt for display under thumbnail
            short_prompt = record.prompt[:25] + "…" if len(record.prompt) > 25 else record.prompt
            item.setText(short_prompt)
            item.setToolTip(f"{record.prompt}\n\nSeed: {record.seed} | {record.width}x{record.height}")
            item.setData(Qt.UserRole, record)

            self.list_gallery.addItem(item)
            visible_count += 1

        self.lbl_count.setText(f"{visible_count} generation(s) stored")

        if visible_count == 0:
            self.list_gallery.hide()
            self.lbl_empty.show()
            self._clear_details()
        else:
            self.list_gallery.show()
            self.lbl_empty.hide()
            # Select first item if nothing selected
            if self.list_gallery.count() > 0:
                self.list_gallery.setCurrentRow(0)

    def _clear_details(self) -> None:
        """Clear detail pane controls."""
        self._selected_record = None
        self.lbl_preview.setText("Select a generation to preview")
        self.lbl_preview.setPixmap(QPixmap())
        self.lbl_model_val.setText("—")
        self.lbl_mode_val.setText("—")
        self.lbl_timestamp_val.setText("—")
        self.lbl_dim_val.setText("—")
        self.lbl_steps_val.setText("—")
        self.lbl_guidance_val.setText("—")
        self.lbl_seed_val.setText("—")
        self.lbl_denoising_val.setText("—")
        self.lbl_duration_val.setText("—")
        self.txt_prompt_val.setPlainText("")
        self.txt_neg_val.setPlainText("")

        self.btn_reuse.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.btn_open.setEnabled(False)
        self.btn_delete.setEnabled(False)

    def _show_details(self, record: GenerationRecord) -> None:
        """Display details for the selected record."""
        self._selected_record = record

        # Show image preview
        if os.path.exists(record.image_path):
            pixmap = QPixmap(record.image_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    QSize(440, 320),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                self.lbl_preview.setPixmap(scaled)
            else:
                self.lbl_preview.setText("Image failed to load")
        else:
            self.lbl_preview.setText("Image file missing")

        # Fill metadata
        self.lbl_model_val.setText(record.model or "flux-schnell")
        self.lbl_mode_val.setText(record.mode or "text-to-image")

        # Format timestamp nicely
        ts_str = record.timestamp
        if "T" in ts_str:
            ts_str = ts_str.replace("T", " ")[:19]
        self.lbl_timestamp_val.setText(ts_str)

        self.lbl_dim_val.setText(f"{record.width} × {record.height}")
        self.lbl_steps_val.setText(str(record.steps))
        self.lbl_guidance_val.setText(f"{record.guidance:.1f}")
        self.lbl_seed_val.setText(str(record.seed))
        self.lbl_denoising_val.setText(f"{record.denoising_strength:.2f}")
        self.lbl_duration_val.setText(f"{record.duration_seconds:.2f}s")

        self.txt_prompt_val.setPlainText(record.prompt)
        self.txt_neg_val.setPlainText(record.negative_prompt or "None")

        self.btn_reuse.setEnabled(True)
        self.btn_export.setEnabled(True)
        self.btn_open.setEnabled(True)
        self.btn_delete.setEnabled(True)

    # ---------------------------------------------------------------------- #
    # Slots                                                                    #
    # ---------------------------------------------------------------------- #

    @Slot(QListWidgetItem, QListWidgetItem)
    def _on_item_selected(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        if current is None:
            self._clear_details()
            return
        record: GenerationRecord = current.data(Qt.UserRole)
        if record:
            self._show_details(record)

    @Slot(str)
    def _on_filter_changed(self, text: str) -> None:
        self._populate_gallery(self._records)

    @Slot()
    def _on_reuse_clicked(self) -> None:
        if self._selected_record:
            logger.info("User requested reuse of parameters for record %s", self._selected_record.id)
            self.reuse_requested.emit(self._selected_record)

    @Slot()
    def _on_export_clicked(self) -> None:
        if not self._selected_record or not os.path.exists(self._selected_record.image_path):
            return

        default_name = f"nova_{self._selected_record.id}.png"
        target_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Generated Image",
            default_name,
            "PNG Images (*.png);;All Files (*)",
        )
        if target_path:
            try:
                shutil.copyfile(self._selected_record.image_path, target_path)
                logger.info("Exported image to %s", target_path)
            except Exception as exc:
                QMessageBox.critical(self, "Export Failed", f"Could not export image: {exc}")

    @Slot()
    def _on_open_clicked(self) -> None:
        if self._selected_record and os.path.exists(self._selected_record.image_path):
            file_url = QUrl.fromLocalFile(self._selected_record.image_path)
            QDesktopServices.openUrl(file_url)

    @Slot()
    def _on_delete_clicked(self) -> None:
        if not self._selected_record:
            return

        reply = QMessageBox.question(
            self,
            "Delete Generation",
            f"Are you sure you want to delete this generation from history?\nPrompt: {self._selected_record.prompt[:50]}…",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            record_id = self._selected_record.id
            self._history_service.delete_record(record_id)

    @Slot()
    def _on_clear_clicked(self) -> None:
        if not self._records:
            return

        reply = QMessageBox.question(
            self,
            "Clear Entire History",
            "Are you sure you want to delete ALL generation history? This action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._history_service.clear_history()

    @Slot(GenerationRecord)
    def _on_record_added(self, record: GenerationRecord) -> None:
        self.reload_history()

    @Slot(str)
    def _on_record_deleted(self, record_id: str) -> None:
        self.reload_history()
