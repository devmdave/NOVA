"""
Models View — local model management, scanning, validation, and removal.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.app_service import ApplicationService
from app.models.selection import ModelCompatibility, ModelRecommendation
from app.models.spec import ModelSpec, ModelStatus

logger = logging.getLogger("nova.ui.models_view")


# ---------------------------------------------------------------------------
# Dialog: Model Details Inspection
# ---------------------------------------------------------------------------

class ModelDetailDialog(QDialog):
    """Modal dialog displaying comprehensive details and validation results for a model."""

    def __init__(self, spec: ModelSpec, app_service: ApplicationService, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.spec = spec
        self._service = app_service
        self.setWindowTitle(f"Model Details — {spec.display_name}")
        self.setMinimumWidth(560)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        # Title Header
        lbl_title = QLabel(self.spec.display_name)
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(lbl_title)

        # Form Layout
        form = QFormLayout()
        form.setSpacing(8)

        form.addRow("Model ID:", QLabel(self.spec.model_id))
        form.addRow("Architecture:", QLabel(self.spec.architecture.upper()))
        form.addRow("Runtime Adapter:", QLabel(self.spec.runtime))
        form.addRow("Source / Path:", QLabel(str(self.spec.source)))
        form.addRow("Type:", QLabel("Custom Local Model" if self.spec.is_custom else "Built-in Model"))

        # Status badge
        lbl_status = QLabel(self.spec.status.name)
        if self.spec.status in (ModelStatus.READY, ModelStatus.INSTALLED):
            lbl_status.setStyleSheet("color: #4DCC88; font-weight: bold;")
        elif self.spec.status == ModelStatus.INVALID:
            lbl_status.setStyleSheet("color: #FF5555; font-weight: bold;")
        form.addRow("Model Status:", lbl_status)

        if self.spec.error_message:
            lbl_err = QLabel(self.spec.error_message)
            lbl_err.setWordWrap(True)
            lbl_err.setStyleSheet("color: #ff6b6b; font-size: 11px;")
            form.addRow("Validation Message:", lbl_err)

        caps = ", ".join(self.spec.capabilities) if self.spec.capabilities else "None"
        form.addRow("Capabilities:", QLabel(caps))
        form.addRow("Min / Rec VRAM:", QLabel(f"{self.spec.min_vram_gb} GB / {self.spec.recommended_vram_gb} GB"))
        form.addRow("Model Size:", QLabel(f"{self.spec.model_size_gb} GB"))
        form.addRow("Default Resolution:", QLabel(f"{self.spec.default_width} × {self.spec.default_height}"))
        form.addRow("Default Steps / Guidance:", QLabel(f"{self.spec.steps_default} steps / {self.spec.guidance_default} CFG"))

        # Hardware compatibility check
        hw = self._service.hardware
        compat = self._service.model_selection.evaluate(hw, [self.spec]).evaluations.get(self.spec.model_id)

        if compat:
            lbl_compat = QLabel()
            lbl_compat.setWordWrap(True)
            if compat.is_compatible:
                lbl_compat.setText("✓ Compatible: " + " ".join(compat.reasons))
                lbl_compat.setStyleSheet("color: #4DCC88;")
            else:
                lbl_compat.setText("✗ Incompatible: " + " ".join(compat.reasons))
                lbl_compat.setStyleSheet("color: #FF5555;")
            form.addRow("Hardware Compatibility:", lbl_compat)

        layout.addLayout(form)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        btn_rescan = QPushButton("Validate & Re-scan")
        btn_rescan.clicked.connect(self._on_rescan_clicked)
        btn_layout.addWidget(btn_rescan)

        btn_active = QPushButton("Set as Active Model")
        btn_active.setObjectName("PrimaryButton")
        btn_active.clicked.connect(self._on_active_clicked)
        btn_layout.addWidget(btn_active)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

    def _on_rescan_clicked(self) -> None:
        self._service.model_service.rescan_model(self.spec.model_id)
        self.accept()

    def _on_active_clicked(self) -> None:
        self._service.model_service.select_active_model(self.spec.model_id)
        self.accept()


# ---------------------------------------------------------------------------
# Dialog: Remove Model Confirmation
# ---------------------------------------------------------------------------

class RemoveModelDialog(QDialog):
    """Modal dialog for removing a model from NOVA with explicit file deletion confirmation."""

    def __init__(self, spec: ModelSpec, app_service: ApplicationService, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.spec = spec
        self._service = app_service
        self.setWindowTitle(f"Remove Model — {spec.display_name}")
        self.setMinimumWidth(500)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        lbl_warning = QLabel(f"<b>Remove '{self.spec.display_name}' from NOVA?</b>")
        lbl_warning.setStyleSheet("font-size: 14px;")
        layout.addWidget(lbl_warning)

        lbl_info = QLabel("Choose how you want to remove this model:")
        layout.addWidget(lbl_info)

        # Options
        self.rad_keep_files = QRadioButton("Remove from NOVA catalog (Keep model files on disk)")
        self.rad_keep_files.setChecked(True)
        self.rad_keep_files.toggled.connect(self._on_option_changed)

        self.rad_delete_files = QRadioButton("Remove from NOVA AND permanently delete model files from disk")
        self.rad_delete_files.toggled.connect(self._on_option_changed)

        layout.addWidget(self.rad_keep_files)
        layout.addWidget(self.rad_delete_files)

        # Path display & confirmation check
        model_path = self._service.model_store.model_path_for_spec(self.spec)
        self.lbl_path = QLabel(f"Path: {model_path}")
        self.lbl_path.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        self.lbl_path.setWordWrap(True)
        layout.addWidget(self.lbl_path)

        self.chk_confirm = QCheckBox(
            "I understand this action will permanently delete all model files from disk."
        )
        self.chk_confirm.setStyleSheet("color: #ff6b6b; font-weight: bold;")
        self.chk_confirm.hide()
        self.chk_confirm.toggled.connect(self._update_button_state)
        layout.addWidget(self.chk_confirm)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_remove = QPushButton("Remove Model")
        self.btn_remove.setStyleSheet("background-color: #c0392b; color: white; padding: 6px 16px; border-radius: 4px;")
        self.btn_remove.setCursor(Qt.PointingHandCursor)
        self.btn_remove.clicked.connect(self._on_confirm_remove)
        btn_layout.addWidget(self.btn_remove)

        layout.addLayout(btn_layout)

    def _on_option_changed(self) -> None:
        is_delete = self.rad_delete_files.isChecked()
        self.chk_confirm.setVisible(is_delete)
        if not is_delete:
            self.chk_confirm.setChecked(False)
        self._update_button_state()

    def _update_button_state(self) -> None:
        if self.rad_delete_files.isChecked():
            self.btn_remove.setEnabled(self.chk_confirm.isChecked())
        else:
            self.btn_remove.setEnabled(True)

    def _on_confirm_remove(self) -> None:
        delete_files = self.rad_delete_files.isChecked()
        success, msg = self._service.model_service.remove_model(self.spec.model_id, delete_files=delete_files)
        if success:
            self.accept()
        else:
            QMessageBox.critical(self, "Remove Model Failed", msg)


# ---------------------------------------------------------------------------
# ModelsView Screen
# ---------------------------------------------------------------------------

class ModelsView(QWidget):
    def __init__(self, app_service: ApplicationService) -> None:
        super().__init__()
        self._service = app_service
        self._model_service = app_service.model_service
        self._recommendation: Optional[ModelRecommendation] = None

        self._setup_ui()

        # Service Signals
        self._model_service.model_updated.connect(self._on_model_event)
        self._model_service.model_removed.connect(self._on_model_event)
        self._model_service.registry_refreshed.connect(self._refresh_data)

        self._refresh_data()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._refresh_data()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 20, 20, 20)
        root_layout.setSpacing(16)

        # Header Bar
        header_layout = QHBoxLayout()
        title = QLabel("Hardware & Models")
        title.setObjectName("ViewTitle")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        btn_rescan_all = QPushButton("Re-scan All")
        btn_rescan_all.setCursor(Qt.PointingHandCursor)
        btn_rescan_all.clicked.connect(self._on_rescan_all_clicked)
        header_layout.addWidget(btn_rescan_all)

        self.btn_add_custom = QPushButton("Add Custom Model…")
        self.btn_add_custom.setObjectName("PrimaryButton")
        self.btn_add_custom.setCursor(Qt.PointingHandCursor)
        self.btn_add_custom.clicked.connect(self._on_add_custom_model_clicked)
        header_layout.addWidget(self.btn_add_custom)

        root_layout.addLayout(header_layout)

        # Status / Feedback Banner
        self.lbl_status = QLabel("")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setWordWrap(True)
        self.lbl_status.hide()
        root_layout.addWidget(self.lbl_status)

        # Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        content_widget = QWidget()
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setContentsMargins(0, 0, 16, 0)
        self.content_layout.setSpacing(16)

        # Hardware Section
        hw_label = QLabel("Detected Hardware")
        hw_label.setObjectName("SectionTitle")
        self.content_layout.addWidget(hw_label)

        self.hw_container = QWidget()
        self.hw_container.setObjectName("Card")
        hw_layout = QVBoxLayout(self.hw_container)

        self.lbl_cpu = QLabel()
        self.lbl_ram = QLabel()
        self.lbl_gpu = QLabel()

        hw_layout.addWidget(self.lbl_cpu)
        hw_layout.addWidget(self.lbl_ram)
        hw_layout.addWidget(self.lbl_gpu)

        self.content_layout.addWidget(self.hw_container)

        # Recommendation Section
        rec_label = QLabel("Recommendation")
        rec_label.setObjectName("SectionTitle")
        self.content_layout.addWidget(rec_label)

        self.rec_container = QWidget()
        self.rec_container.setObjectName("RecommendationCard")
        rec_layout = QVBoxLayout(self.rec_container)
        self.lbl_recommendation = QLabel()
        self.lbl_recommendation.setWordWrap(True)
        rec_layout.addWidget(self.lbl_recommendation)
        self.content_layout.addWidget(self.rec_container)

        # Models List
        models_label = QLabel("Available Local Models")
        models_label.setObjectName("SectionTitle")
        self.content_layout.addWidget(models_label)

        self.models_list_layout = QVBoxLayout()
        self.models_list_layout.setSpacing(12)
        self.content_layout.addLayout(self.models_list_layout)

        self.content_layout.addStretch()

        scroll.setWidget(content_widget)
        root_layout.addWidget(scroll)

    def _refresh_data(self) -> None:
        hw = self._service.hardware
        self.lbl_cpu.setText(f"CPU: {hw.cpu_name} ({hw.cpu_cores} cores)")
        self.lbl_ram.setText(f"RAM: {hw.ram_gb:.1f} GB")

        if hw.has_gpu:
            gpu_texts = []
            for g in hw.gpus:
                vram_str = f"{g.vram_gb:.1f} GB VRAM" if g.vram_gb else "VRAM unknown"
                gpu_texts.append(f"{g.name} ({g.vendor}) — {vram_str}")
            self.lbl_gpu.setText("GPU:\n" + "\n".join(gpu_texts))
        else:
            self.lbl_gpu.setText("GPU: None detected")

        # Evaluate models
        specs = self._model_service.get_all_models()
        rec = self._service.model_selection.evaluate(hw, specs)
        self._recommendation = rec

        if rec.recommended_model_id:
            spec = self._service.model_registry.get_or_none(rec.recommended_model_id)
            disp_name = spec.display_name if spec else rec.recommended_model_id
            self.lbl_recommendation.setText(
                f"<b>⭐ Recommended Model:</b> {disp_name}<br><br>"
                f"{rec.recommendation_reason}"
            )
            self.rec_container.setProperty("recState", "good")
        else:
            self.lbl_recommendation.setText(
                "<b>No compatible models found.</b><br><br>"
                f"{rec.recommendation_reason}"
            )
            self.rec_container.setProperty("recState", "bad")

        self.rec_container.style().unpolish(self.rec_container)
        self.rec_container.style().polish(self.rec_container)

        # Clear existing cards
        while self.models_list_layout.count():
            item = self.models_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        active_model_id = self._service.settings.default_model_id

        for spec in specs:
            eval_result = rec.evaluations.get(spec.model_id)
            is_active = (spec.model_id == active_model_id)
            is_recommended = (spec.model_id == rec.recommended_model_id)
            card = self._create_model_card(spec, eval_result, is_active=is_active, is_recommended=is_recommended)
            self.models_list_layout.addWidget(card)

    def _create_model_card(
        self,
        spec: ModelSpec,
        compat: Optional[ModelCompatibility],
        is_active: bool = False,
        is_recommended: bool = False,
    ) -> QWidget:
        card = QWidget()
        card.setObjectName("ModelCard")
        layout = QVBoxLayout(card)
        layout.setSpacing(8)

        # Header (Name + Badges + Status)
        header_layout = QHBoxLayout()

        name_text = f"<b>{spec.display_name}</b>"
        if is_recommended:
            name_text += " <span style='color: #f39c12; font-size: 11px;'>[⭐ Recommended]</span>"
        if spec.is_custom:
            name_text += " <span style='color: #9b59b6; font-size: 11px;'>[Custom Model]</span>"

        name_lbl = QLabel(name_text)
        name_lbl.setObjectName("ModelCardTitle")
        header_layout.addWidget(name_lbl)

        header_layout.addStretch()

        status_lbl = QLabel()
        status_lbl.setObjectName("ModelCardStatus")
        status_name = spec.status.name
        if spec.status in (ModelStatus.READY, ModelStatus.INSTALLED):
            status_lbl.setText("Ready / Installed")
            status_lbl.setProperty("statusState", "ready")
        elif spec.status == ModelStatus.INVALID:
            status_lbl.setText("Invalid")
            status_lbl.setProperty("statusState", "missing")
        elif spec.status == ModelStatus.NOT_INSTALLED:
            status_lbl.setText("Not Installed")
            status_lbl.setProperty("statusState", "missing")
        else:
            status_lbl.setText(status_name)
            status_lbl.setProperty("statusState", "ready")

        header_layout.addWidget(status_lbl)
        layout.addLayout(header_layout)

        # Specs info & local path
        model_path = self._service.model_store.model_path_for_spec(spec)
        path_str = f"<b>Path:</b> {model_path}"
        path_lbl = QLabel(path_str)
        path_lbl.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        path_lbl.setWordWrap(True)
        layout.addWidget(path_lbl)

        caps_str = ", ".join(spec.capabilities) if spec.capabilities else "text-to-image"
        details_str = (
            f"<b>Architecture:</b> {spec.architecture.upper()} | "
            f"<b>Runtime:</b> {spec.runtime} | "
            f"<b>Min VRAM:</b> {spec.min_vram_gb} GB | "
            f"<b>Size:</b> {spec.model_size_gb} GB | "
            f"<b>Capabilities:</b> {caps_str}"
        )
        details_lbl = QLabel(details_str)
        details_lbl.setWordWrap(True)
        layout.addWidget(details_lbl)

        if spec.error_message:
            err_lbl = QLabel(f"⚠️ Validation Issue: {spec.error_message}")
            err_lbl.setStyleSheet("color: #ff6b6b; font-size: 11px; font-weight: bold;")
            err_lbl.setWordWrap(True)
            layout.addWidget(err_lbl)

        # Compatibility feedback
        if compat:
            compat_lbl = QLabel()
            compat_lbl.setWordWrap(True)
            if compat.is_compatible:
                compat_lbl.setText("✓ Compatible: " + " ".join(compat.reasons))
                compat_lbl.setStyleSheet("color: #4DCC88;")
            else:
                compat_lbl.setText("✗ Incompatible: " + " ".join(compat.reasons))
                compat_lbl.setStyleSheet("color: #FF5555;")
            layout.addWidget(compat_lbl)

        # Action bar
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)

        btn_details = QPushButton("Details…")
        btn_details.setCursor(Qt.PointingHandCursor)
        btn_details.clicked.connect(lambda checked=False, s=spec: self._on_show_details(s))
        actions_layout.addWidget(btn_details)

        btn_rescan = QPushButton("Re-scan")
        btn_rescan.setCursor(Qt.PointingHandCursor)
        btn_rescan.clicked.connect(lambda checked=False, m_id=spec.model_id: self._on_rescan_model(m_id))
        actions_layout.addWidget(btn_rescan)

        btn_remove = QPushButton("Remove")
        btn_remove.setStyleSheet("background-color: #8b2626; color: white; border-radius: 4px; padding: 4px 10px;")
        btn_remove.setCursor(Qt.PointingHandCursor)
        btn_remove.clicked.connect(lambda checked=False, s=spec: self._on_remove_model(s))
        actions_layout.addWidget(btn_remove)

        actions_layout.addStretch()

        if is_active:
            btn_active = QPushButton("✓ Active Generation Model")
            btn_active.setEnabled(False)
            btn_active.setStyleSheet("background-color: #27ae60; color: white; border-radius: 4px; padding: 4px 12px;")
            actions_layout.addWidget(btn_active)
        else:
            btn_select = QPushButton("Use for Generation")
            btn_select.setCursor(Qt.PointingHandCursor)
            btn_select.clicked.connect(lambda checked=False, m_id=spec.model_id: self._on_select_model(m_id))
            actions_layout.addWidget(btn_select)

        layout.addLayout(actions_layout)
        return card

    # ---------------------------------------------------------------------- #
    # Slots                                                                    #
    # ---------------------------------------------------------------------- #

    @Slot()
    def _on_rescan_all_clicked(self) -> None:
        self._model_service.rescan_all()
        self._show_status("Re-scanned all local models.", error=False)
        self._refresh_data()

    @Slot()
    def _on_add_custom_model_clicked(self) -> None:
        target_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Local Custom Model Directory",
            self._service.settings.models_dir,
        )
        if not target_dir:
            return

        spec, errors = self._model_service.register_custom_model(target_dir)
        if errors or spec is None:
            err_msg = " · ".join(errors) if errors else "Failed to detect custom model."
            logger.warning("Custom model registration failed for %s: %s", target_dir, err_msg)
            self._show_status(err_msg, error=True)
            return

        self._show_status(f"Successfully registered custom model '{spec.display_name}'.", error=False)
        self._refresh_data()

    def _on_show_details(self, spec: ModelSpec) -> None:
        dialog = ModelDetailDialog(spec, self._service, parent=self)
        dialog.exec()
        self._refresh_data()

    def _on_rescan_model(self, model_id: str) -> None:
        status, problems = self._model_service.rescan_model(model_id)
        if problems:
            self._show_status(f"Re-scanned '{model_id}': {status.name} — {' · '.join(problems)}", error=True)
        else:
            self._show_status(f"Re-scanned '{model_id}': Status is {status.name}.", error=False)
        self._refresh_data()

    def _on_remove_model(self, spec: ModelSpec) -> None:
        dialog = RemoveModelDialog(spec, self._service, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self._show_status(f"Removed '{spec.display_name}' from NOVA.", error=False)
            self._refresh_data()

    def _on_select_model(self, model_id: str) -> None:
        success = self._model_service.select_active_model(model_id)
        if success:
            self._show_status(f"Selected model '{model_id}' for generation.", error=False)
            self._refresh_data()
        else:
            self._show_status(f"Failed to select model '{model_id}'.", error=True)

    @Slot(object)
    def _on_model_event(self, arg) -> None:
        self._refresh_data()

    def _show_status(self, message: str, error: bool) -> None:
        self.lbl_status.setText(message)
        if error:
            self.lbl_status.setStyleSheet(
                "background-color: #3b1b1b; color: #ff6b6b; border: 1px solid #a83232; "
                "border-radius: 6px; padding: 8px; font-weight: bold;"
            )
        else:
            self.lbl_status.setStyleSheet(
                "background-color: #1b3b24; color: #51cf66; border: 1px solid #2b7a41; "
                "border-radius: 6px; padding: 8px; font-weight: bold;"
            )
        self.lbl_status.show()
