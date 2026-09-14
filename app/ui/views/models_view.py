"""
Models View — local model management, scanning, validation, removal, and acquisition store.
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
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.app_service import ApplicationService
from app.models.catalog import get_official_catalog
from app.models.hf_utils import inspect_hf_custom_model
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
# Dialog: Import Custom Hugging Face Model
# ---------------------------------------------------------------------------

class AddCustomHfModelDialog(QDialog):
    """Modal dialog for inspecting and acquiring a custom Hugging Face model repository."""

    def __init__(self, app_service: ApplicationService, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._service = app_service
        self._inspected_spec: Optional[ModelSpec] = None
        self.setWindowTitle("Import Hugging Face Model")
        self.setMinimumWidth(560)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        lbl_title = QLabel("Import Hugging Face Model")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(lbl_title)

        lbl_desc = QLabel(
            "Enter a Hugging Face model identifier (e.g. 'black-forest-labs/FLUX.1-schnell' or 'stabilityai/sdxl-turbo') "
            "or repository URL. NOVA verifies architecture compatibility before downloading."
        )
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

        input_layout = QHBoxLayout()
        self.txt_repo_id = QLineEdit()
        self.txt_repo_id.setPlaceholderText("owner/repository or https://huggingface.co/...")
        input_layout.addWidget(self.txt_repo_id)

        self.btn_inspect = QPushButton("Inspect & Verify")
        self.btn_inspect.clicked.connect(self._on_inspect_clicked)
        input_layout.addWidget(self.btn_inspect)
        layout.addLayout(input_layout)

        # Inspection Details Group Box
        self.group_details = QGroupBox("Model Metadata Inspection")
        self.group_details.hide()
        details_layout = QVBoxLayout(self.group_details)

        self.lbl_inspect_status = QLabel("")
        self.lbl_inspect_status.setWordWrap(True)
        details_layout.addWidget(self.lbl_inspect_status)

        self.form_details = QFormLayout()
        self.lbl_val_name = QLabel("")
        self.lbl_val_arch = QLabel("")
        self.lbl_val_runtime = QLabel("")
        self.lbl_val_vram = QLabel("")
        self.form_details.addRow("Detected Model:", self.lbl_val_name)
        self.form_details.addRow("Architecture:", self.lbl_val_arch)
        self.form_details.addRow("Runtime Adapter:", self.lbl_val_runtime)
        self.form_details.addRow("Min VRAM:", self.lbl_val_vram)
        details_layout.addLayout(self.form_details)

        layout.addWidget(self.group_details)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_download = QPushButton("Download & Register")
        self.btn_download.setObjectName("PrimaryButton")
        self.btn_download.setEnabled(False)
        self.btn_download.clicked.connect(self._on_download_clicked)
        btn_layout.addWidget(self.btn_download)

        layout.addLayout(btn_layout)

    def _on_inspect_clicked(self) -> None:
        raw_input = self.txt_repo_id.text().strip()
        if not raw_input:
            QMessageBox.warning(self, "Invalid Input", "Please enter a Hugging Face repository identifier or URL.")
            return

        spec, errors = inspect_hf_custom_model(raw_input)
        self.group_details.show()

        if errors or spec is None:
            self._inspected_spec = None
            err_msg = errors[0] if errors else "Unsupported model."
            self.lbl_inspect_status.setText(f"<b>✗ Compatibility Check Failed</b><br><span style='color: #ff6b6b;'>{err_msg}</span>")
            self.lbl_val_name.setText("—")
            self.lbl_val_arch.setText("—")
            self.lbl_val_runtime.setText("—")
            self.lbl_val_vram.setText("—")
            self.btn_download.setEnabled(False)
        else:
            self._inspected_spec = spec
            self.lbl_inspect_status.setText("<b>✓ Model Architecture Supported</b><br><span style='color: #4DCC88;'>NOVA supports this model pipeline. Ready for download.</span>")
            self.lbl_val_name.setText(spec.display_name)
            self.lbl_val_arch.setText(spec.architecture.upper())
            self.lbl_val_runtime.setText(spec.runtime)
            self.lbl_val_vram.setText(f"{spec.min_vram_gb} GB")
            self.btn_download.setEnabled(True)

    def _on_download_clicked(self) -> None:
        if not self._inspected_spec:
            return

        ok, msg = self._service.model_service.acquisition.download_custom_hf_model(self._inspected_spec.source)
        if not ok:
            QMessageBox.critical(self, "Download Failed", msg)
        else:
            QMessageBox.information(
                self,
                "Download Started",
                f"Started download for '{self._inspected_spec.display_name}'. Progress will update in Model Store."
            )
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
    """Primary UI screen for hardware evaluation, official model store, custom imports, and model management."""

    def __init__(self, app_service: ApplicationService) -> None:
        super().__init__()
        self._service = app_service
        self._model_service = app_service.model_service
        self._acquisition = app_service.model_service.acquisition
        self._recommendation: Optional[ModelRecommendation] = None
        self._download_progress_map: dict[str, tuple[float, str]] = {}

        self._setup_ui()

        # Service Signals
        self._model_service.model_updated.connect(self._on_model_event)
        self._model_service.model_removed.connect(self._on_model_event)
        self._model_service.registry_refreshed.connect(self._refresh_data)

        # Acquisition Signals
        self._acquisition.download_started.connect(self._on_download_started)
        self._acquisition.download_progress.connect(self._on_download_progress)
        self._acquisition.download_finished.connect(self._on_download_finished)
        self._acquisition.download_cancelled.connect(self._on_download_cancelled)

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

        self.btn_add_custom_folder = QPushButton("Add Local Model Folder…")
        self.btn_add_custom_folder.setCursor(Qt.PointingHandCursor)
        self.btn_add_custom_folder.clicked.connect(self._on_add_custom_folder_clicked)
        header_layout.addWidget(self.btn_add_custom_folder)

        self.btn_add_hf_model = QPushButton("Import Hugging Face Model…")
        self.btn_add_hf_model.setObjectName("PrimaryButton")
        self.btn_add_hf_model.setCursor(Qt.PointingHandCursor)
        self.btn_add_hf_model.clicked.connect(self._on_add_hf_model_clicked)
        header_layout.addWidget(self.btn_add_hf_model)

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

        # Official Model Store Section
        store_label = QLabel("Model Store — Download Official Models")
        store_label.setObjectName("SectionTitle")
        self.content_layout.addWidget(store_label)

        self.store_list_layout = QVBoxLayout()
        self.store_list_layout.setSpacing(12)
        self.content_layout.addLayout(self.store_list_layout)

        # Registered Installed Models Section
        models_label = QLabel("Registered Local Models")
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

        # Refresh Official Model Store cards
        while self.store_list_layout.count():
            item = self.store_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for catalog_spec in get_official_catalog():
            card = self._create_official_store_card(catalog_spec)
            self.store_list_layout.addWidget(card)

        # Refresh Installed Models cards
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

    def _create_official_store_card(self, spec: ModelSpec) -> QWidget:
        card = QWidget()
        card.setObjectName("ModelCard")
        layout = QVBoxLayout(card)
        layout.setSpacing(8)

        # Header
        header_layout = QHBoxLayout()
        name_lbl = QLabel(f"<b>{spec.display_name}</b> <span style='color: #888888;'>({spec.source})</span>")
        header_layout.addWidget(name_lbl)
        header_layout.addStretch()

        is_registered = spec.model_id in self._service.model_registry
        reg_spec = self._service.model_registry.get_or_none(spec.model_id)
        is_ready = is_registered and reg_spec and reg_spec.status in (ModelStatus.READY, ModelStatus.INSTALLED)
        is_downloading = self._acquisition.is_downloading(spec.model_id)

        if is_ready:
            lbl_st = QLabel("Installed / Ready")
            lbl_st.setStyleSheet("color: #4DCC88; font-weight: bold;")
            header_layout.addWidget(lbl_st)
        elif is_downloading:
            lbl_st = QLabel("Downloading…")
            lbl_st.setStyleSheet("color: #f39c12; font-weight: bold;")
            header_layout.addWidget(lbl_st)
        else:
            lbl_st = QLabel("Available for Download")
            lbl_st.setStyleSheet("color: #888888;")
            header_layout.addWidget(lbl_st)

        layout.addLayout(header_layout)

        # Details
        desc_lbl = QLabel(spec.description)
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        info_lbl = QLabel(
            f"Architecture: <b>{spec.architecture.upper()}</b>  ·  "
            f"Size: <b>{spec.model_size_gb} GB</b>  ·  "
            f"Min VRAM: <b>{spec.min_vram_gb} GB</b>  ·  "
            f"Capabilities: <b>{', '.join(spec.capabilities)}</b>"
        )
        info_lbl.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        layout.addWidget(info_lbl)

        # Download Progress Bar (shown if downloading)
        if is_downloading:
            p_bar = QProgressBar()
            p_bar.setRange(0, 100)
            frac, msg = self._download_progress_map.get(spec.model_id, (0.0, "Downloading…"))
            p_bar.setValue(int(frac * 100))
            layout.addWidget(p_bar)

            msg_lbl = QLabel(msg)
            msg_lbl.setStyleSheet("font-size: 11px; color: #f39c12;")
            layout.addWidget(msg_lbl)

        # Actions
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        if is_downloading:
            btn_cancel = QPushButton("Cancel Download")
            btn_cancel.clicked.connect(lambda: self._acquisition.cancel_download(spec.model_id))
            btn_layout.addWidget(btn_cancel)
        elif is_ready:
            btn_active = QPushButton("Select Active Model")
            btn_active.clicked.connect(lambda: self._service.model_service.select_active_model(spec.model_id))
            btn_layout.addWidget(btn_active)
        else:
            btn_dl = QPushButton("Download Model")
            btn_dl.setObjectName("PrimaryButton")
            btn_dl.clicked.connect(lambda _, mid=spec.model_id: self._on_download_official_clicked(mid))
            btn_layout.addWidget(btn_dl)

        layout.addLayout(btn_layout)
        return card

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
        if spec.status in (ModelStatus.READY, ModelStatus.INSTALLED):
            status_lbl.setText("Ready / Installed")
            status_lbl.setStyleSheet("color: #4DCC88; font-weight: bold;")
        elif spec.status == ModelStatus.INVALID:
            status_lbl.setText("Invalid")
            status_lbl.setStyleSheet("color: #FF5555; font-weight: bold;")
        else:
            status_lbl.setText(spec.status.name)
            status_lbl.setStyleSheet("color: #aaaaaa;")

        header_layout.addWidget(status_lbl)
        layout.addLayout(header_layout)

        # Metadata summary
        meta_text = (
            f"Architecture: <b>{spec.architecture.upper()}</b>  ·  "
            f"Runtime: <b>{spec.runtime}</b>  ·  "
            f"VRAM Req: <b>{spec.min_vram_gb} GB</b>  ·  "
            f"Capabilities: <b>{', '.join(spec.capabilities)}</b>"
        )
        meta_lbl = QLabel(meta_text)
        meta_lbl.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        layout.addWidget(meta_lbl)

        # Compatibility info line
        if compat:
            compat_lbl = QLabel()
            compat_lbl.setWordWrap(True)
            if compat.is_compatible:
                compat_lbl.setText("✓ " + " ".join(compat.reasons))
                compat_lbl.setStyleSheet("color: #4DCC88; font-size: 11px;")
            else:
                compat_lbl.setText("✗ " + " ".join(compat.reasons))
                compat_lbl.setStyleSheet("color: #FF5555; font-size: 11px;")
            layout.addWidget(compat_lbl)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        if is_active:
            lbl_active = QLabel("<b>✓ Active Target</b>")
            lbl_active.setStyleSheet("color: #4DCC88;")
            btn_layout.addWidget(lbl_active)

        btn_layout.addStretch()

        btn_details = QPushButton("View Details")
        btn_details.clicked.connect(lambda _, s=spec: self._show_model_details(s))
        btn_layout.addWidget(btn_details)

        if not is_active and spec.status in (ModelStatus.READY, ModelStatus.INSTALLED):
            btn_select = QPushButton("Select as Active")
            btn_select.setObjectName("PrimaryButton")
            btn_select.clicked.connect(lambda _, mid=spec.model_id: self._select_model(mid))
            btn_layout.addWidget(btn_select)

        btn_rescan = QPushButton("Re-scan")
        btn_rescan.clicked.connect(lambda _, mid=spec.model_id: self._rescan_model(mid))
        btn_layout.addWidget(btn_rescan)

        btn_remove = QPushButton("Remove")
        btn_remove.setStyleSheet("color: #ff6b6b;")
        btn_remove.clicked.connect(lambda _, s=spec: self._remove_model(s))
        btn_layout.addWidget(btn_remove)

        layout.addLayout(btn_layout)
        return card

    # ---------------------------------------------------------------------- #
    # Acquisition Slots                                                       #
    # ---------------------------------------------------------------------- #

    def _on_download_official_clicked(self, model_id: str) -> None:
        ok, msg = self._acquisition.download_official_model(model_id)
        if not ok:
            QMessageBox.warning(self, "Download Error", msg)
        else:
            self._show_status(f"Started downloading model '{model_id}'...", "info")

    def _on_download_started(self, model_id: str) -> None:
        self._download_progress_map[model_id] = (0.0, "Starting download...")
        self._refresh_data()

    def _on_download_progress(self, model_id: str, downloaded_mb: float, total_mb: float, frac: float, msg: str) -> None:
        self._download_progress_map[model_id] = (frac, msg)
        self._refresh_data()

    def _on_download_finished(self, model_id: str, success: bool, spec: Optional[ModelSpec], error_msg: str) -> None:
        self._download_progress_map.pop(model_id, None)
        self._refresh_data()
        if success and spec:
            self._show_status(f"Successfully downloaded and registered '{spec.display_name}'.", "good")
        elif not success and error_msg:
            QMessageBox.critical(self, "Download Failed", f"Failed to acquire model '{model_id}':\n\n{error_msg}")

    def _on_download_cancelled(self, model_id: str) -> None:
        self._download_progress_map.pop(model_id, None)
        self._refresh_data()
        self._show_status(f"Download cancelled for model '{model_id}'.", "warning")

    # ---------------------------------------------------------------------- #
    # General Actions                                                          #
    # ---------------------------------------------------------------------- #

    def _on_model_event(self, *args) -> None:
        self._refresh_data()

    def _show_model_details(self, spec: ModelSpec) -> None:
        dialog = ModelDetailDialog(spec, self._service, self)
        dialog.exec()
        self._refresh_data()

    def _on_select_model(self, model_id: str) -> None:
        """Alias for backward compatibility with tests."""
        self._select_model(model_id)

    def _select_model(self, model_id: str) -> None:
        if self._model_service.select_active_model(model_id):
            spec = self._model_service.get_model(model_id)
            disp = spec.display_name if spec else model_id
            self._show_status(f"Selected '{disp}' as active generation target.", "good")
            self._refresh_data()

    def _rescan_model(self, model_id: str) -> None:
        status, problems = self._model_service.rescan_model(model_id)
        if status in (ModelStatus.READY, ModelStatus.INSTALLED):
            self._show_status(f"Re-scan complete: model '{model_id}' is READY.", "good")
        else:
            reasons = f": {', '.join(problems)}" if problems else ""
            self._show_status(f"Re-scan complete: model '{model_id}' is {status.name}{reasons}.", "bad")
        self._refresh_data()

    def _remove_model(self, spec: ModelSpec) -> None:
        dialog = RemoveModelDialog(spec, self._service, self)
        if dialog.exec() == QDialog.Accepted:
            self._show_status(f"Removed model '{spec.display_name}' from catalog.", "warning")
            self._refresh_data()

    def _on_rescan_all_clicked(self) -> None:
        self._model_service.rescan_all()
        self._show_status("Re-scanned all registered models.", "info")
        self._refresh_data()

    def _on_add_custom_folder_clicked(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(self, "Select Local Custom Model Directory")
        if not dir_path:
            return

        spec, errors = self._model_service.register_custom_model(dir_path)
        if errors or spec is None:
            msg = "Could not register model:\n\n" + "\n".join(f"• {e}" for e in errors)
            QMessageBox.critical(self, "Registration Failed", msg)
        else:
            self._show_status(f"Successfully registered custom model '{spec.display_name}'.", "good")
            self._refresh_data()

    def _on_add_hf_model_clicked(self) -> None:
        dialog = AddCustomHfModelDialog(self._service, self)
        dialog.exec()

    def _show_status(self, text: str, state: str) -> None:
        self.lbl_status.setText(text)
        self.lbl_status.setProperty("statusState", state)
        self.lbl_status.style().unpolish(self.lbl_status)
        self.lbl_status.style().polish(self.lbl_status)
        self.lbl_status.show()
