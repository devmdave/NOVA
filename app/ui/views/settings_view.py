"""
SettingsView — settings management view for NOVA.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.config.settings import AppSettings
from app.core.app_service import ApplicationService

logger = logging.getLogger("nova.ui.settings_view")


class SettingsView(QWidget):
    """View for configuring application settings, paths, defaults, and preferences."""

    def __init__(self, app_service: ApplicationService) -> None:
        super().__init__()
        self._service = app_service
        self._settings_service = app_service.settings_service
        self._initial_settings = self._settings_service.get_settings()

        self._setup_ui()
        self._load_from_settings(self._initial_settings)

        # Connect to settings service signals
        self._settings_service.settings_changed.connect(self._on_settings_changed_externally)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._load_from_settings(self._settings_service.get_settings())

    # ---------------------------------------------------------------------- #
    # UI Construction                                                          #
    # ---------------------------------------------------------------------- #

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # ---- Top Header Bar ---------------------------------------------- #
        header_layout = QHBoxLayout()
        lbl_title = QLabel("Application Settings")
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(lbl_title)
        header_layout.addStretch()

        self.btn_reset = QPushButton("Reset Defaults")
        self.btn_reset.setObjectName("SecondaryButton")
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.clicked.connect(self._on_reset_clicked)
        header_layout.addWidget(self.btn_reset)

        self.btn_save = QPushButton("Save Settings")
        self.btn_save.setObjectName("PrimaryButton")
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.setMinimumWidth(120)
        self.btn_save.clicked.connect(self._on_save_clicked)
        header_layout.addWidget(self.btn_save)

        root.addLayout(header_layout)

        # ---- Status / Banner Notifications ------------------------------- #
        self.lbl_status = QLabel("")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setWordWrap(True)
        self.lbl_status.hide()
        root.addWidget(self.lbl_status)

        self.lbl_restart_banner = QLabel(
            "⚠️ Restart Required: Changes to 'Start with Real Model' or 'Device Preference' "
            "will take effect when NOVA is restarted."
        )
        self.lbl_restart_banner.setAlignment(Qt.AlignCenter)
        self.lbl_restart_banner.setWordWrap(True)
        self.lbl_restart_banner.setStyleSheet(
            "background-color: #3d2e14; color: #f39c12; border: 1px solid #d35400; "
            "border-radius: 6px; padding: 8px; font-weight: bold;"
        )
        self.lbl_restart_banner.hide()
        root.addWidget(self.lbl_restart_banner)

        # ---- Main Scrollable Content Area --------------------------------- #
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 10, 0)
        content_layout.setSpacing(16)

        # ---- Section 1: Storage & Directories ---------------------------- #
        group_storage = QGroupBox("Storage & Directories")
        form_storage = QFormLayout(group_storage)
        form_storage.setSpacing(10)

        # Models Dir
        layout_models = QHBoxLayout()
        self.txt_models_dir = QLineEdit()
        btn_models_browse = QPushButton("Browse…")
        btn_models_browse.clicked.connect(self._on_browse_models_dir)
        layout_models.addWidget(self.txt_models_dir)
        layout_models.addWidget(btn_models_browse)
        form_storage.addRow("Model Storage Location:", layout_models)

        # History Dir
        layout_history = QHBoxLayout()
        self.txt_history_dir = QLineEdit()
        btn_history_browse = QPushButton("Browse…")
        btn_history_browse.clicked.connect(self._on_browse_history_dir)
        layout_history.addWidget(self.txt_history_dir)
        layout_history.addWidget(btn_history_browse)
        form_storage.addRow("History Storage Location:", layout_history)

        content_layout.addWidget(group_storage)

        # ---- Section 2: Generation Defaults ------------------------------ #
        group_defaults = QGroupBox("Generation Defaults")
        form_defaults = QFormLayout(group_defaults)
        form_defaults.setSpacing(10)

        # Default Model
        self.cmb_default_model = QComboBox()
        self._populate_model_combo()
        form_defaults.addRow("Default Model:", self.cmb_default_model)

        # Default Width & Height
        layout_dims = QHBoxLayout()
        self.spin_width = QSpinBox()
        self.spin_width.setRange(256, 2048)
        self.spin_width.setSingleStep(64)
        self.spin_height = QSpinBox()
        self.spin_height.setRange(256, 2048)
        self.spin_height.setSingleStep(64)
        layout_dims.addWidget(QLabel("Width:"))
        layout_dims.addWidget(self.spin_width)
        layout_dims.addSpacing(16)
        layout_dims.addWidget(QLabel("Height:"))
        layout_dims.addWidget(self.spin_height)
        layout_dims.addStretch()
        form_defaults.addRow("Default Dimensions:", layout_dims)

        # Default Steps
        self.spin_steps = QSpinBox()
        self.spin_steps.setRange(1, 200)
        form_defaults.addRow("Default Steps:", self.spin_steps)

        # Default Guidance
        self.spin_guidance = QDoubleSpinBox()
        self.spin_guidance.setRange(0.0, 30.0)
        self.spin_guidance.setSingleStep(0.5)
        self.spin_guidance.setDecimals(1)
        form_defaults.addRow("Default Guidance / CFG:", self.spin_guidance)

        # Default Seed
        layout_seed = QHBoxLayout()
        self.spin_seed = QSpinBox()
        self.spin_seed.setRange(-1, 2147483647)
        lbl_seed_hint = QLabel("(-1 = random seed per generation)")
        lbl_seed_hint.setStyleSheet("color: #888888; font-size: 11px;")
        layout_seed.addWidget(self.spin_seed)
        layout_seed.addWidget(lbl_seed_hint)
        layout_seed.addStretch()
        form_defaults.addRow("Default Seed:", layout_seed)

        content_layout.addWidget(group_defaults)

        # ---- Section 3: Backend & Hardware Acceleration ------------------ #
        group_backend = QGroupBox("Backend & Acceleration")
        form_backend = QFormLayout(group_backend)
        form_backend.setSpacing(10)

        # Real model vs Mock mode
        self.chk_real_model = QCheckBox("Start with real model backend (Diffusers FLUX) instead of Mock mode")
        self.chk_real_model.stateChanged.connect(self._check_restart_needed)
        form_backend.addRow("Inference Backend:", self.chk_real_model)

        # Hardware Preference
        self.cmb_device_pref = QComboBox()
        self.cmb_device_pref.addItem("Auto (Recommended)", "auto")
        self.cmb_device_pref.addItem("CUDA (NVIDIA GPU)", "cuda")
        self.cmb_device_pref.addItem("CPU (Slow)", "cpu")
        self.cmb_device_pref.currentIndexChanged.connect(self._check_restart_needed)
        form_backend.addRow("Device Acceleration:", self.cmb_device_pref)

        content_layout.addWidget(group_backend)

        content_layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)

    # ---------------------------------------------------------------------- #
    # Data Mapping                                                             #
    # ---------------------------------------------------------------------- #

    def _populate_model_combo(self) -> None:
        """Populate model dropdown from ModelRegistry."""
        self.cmb_default_model.clear()
        registry = self._service.model_registry
        for spec in registry.list_all():
            self.cmb_default_model.addItem(f"{spec.display_name} ({spec.model_id})", spec.model_id)

    def _load_from_settings(self, settings: AppSettings) -> None:
        """Populate form fields from AppSettings instance."""
        self.txt_models_dir.setText(settings.models_dir)
        self.txt_history_dir.setText(settings.history_dir)

        idx = self.cmb_default_model.findData(settings.default_model_id)
        if idx >= 0:
            self.cmb_default_model.setCurrentIndex(idx)

        self.spin_width.setValue(settings.default_width)
        self.spin_height.setValue(settings.default_height)
        self.spin_steps.setValue(settings.default_steps)
        self.spin_guidance.setValue(settings.default_guidance)
        self.spin_seed.setValue(settings.default_seed)

        self.chk_real_model.setChecked(settings.use_real_model)

        device_idx = self.cmb_device_pref.findData(settings.device_preference)
        if device_idx >= 0:
            self.cmb_device_pref.setCurrentIndex(device_idx)

        self._check_restart_needed()

    def _collect_settings(self) -> AppSettings:
        """Construct AppSettings from current form values."""
        current = self._settings_service.get_settings()

        selected_model_id = self.cmb_default_model.currentData() or current.default_model_id
        selected_device = self.cmb_device_pref.currentData() or current.device_preference

        return AppSettings(
            app_name=current.app_name,
            version=current.version,
            debug=current.debug,
            models_dir=self.txt_models_dir.text().strip(),
            history_dir=self.txt_history_dir.text().strip(),
            default_model_id=selected_model_id,
            default_width=self.spin_width.value(),
            default_height=self.spin_height.value(),
            default_steps=self.spin_steps.value(),
            default_guidance=self.spin_guidance.value(),
            default_seed=self.spin_seed.value(),
            use_real_model=self.chk_real_model.isChecked(),
            device_preference=selected_device,
        )

    def _check_restart_needed(self) -> None:
        """Show restart banner if backend or device settings differ from initial startup values."""
        current_chk = self.chk_real_model.isChecked()
        current_dev = self.cmb_device_pref.currentData()

        restart_needed = (
            current_chk != self._initial_settings.use_real_model
            or current_dev != self._initial_settings.device_preference
        )
        self.lbl_restart_banner.setVisible(restart_needed)

    # ---------------------------------------------------------------------- #
    # Slots                                                                    #
    # ---------------------------------------------------------------------- #

    @Slot()
    def _on_browse_models_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Models Directory", self.txt_models_dir.text())
        if path:
            self.txt_models_dir.setText(path)

    @Slot()
    def _on_browse_history_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select History Directory", self.txt_history_dir.text())
        if path:
            self.txt_history_dir.setText(path)

    @Slot()
    def _on_save_clicked(self) -> None:
        new_settings = self._collect_settings()
        errors = self._settings_service.save_settings(new_settings)

        if errors:
            self._show_status(" · ".join(errors), error=True)
        else:
            self._show_status("Settings saved successfully.", error=False)
            self._check_restart_needed()

    @Slot()
    def _on_reset_clicked(self) -> None:
        defaults = self._settings_service.reset_defaults()
        self._load_from_settings(defaults)
        self._show_status("Settings restored to defaults.", error=False)

    @Slot(AppSettings)
    def _on_settings_changed_externally(self, settings: AppSettings) -> None:
        self._load_from_settings(settings)

    def _show_status(self, message: str, error: bool) -> None:
        self.lbl_status.setText(message)
        if error:
            self.lbl_status.setStyleSheet(
                "background-color: #3b1b1b; color: #ff6b6b; border: 1px solid #a83232; "
                "border-radius: 6px; padding: 8px;"
            )
        else:
            self.lbl_status.setStyleSheet(
                "background-color: #1b3b24; color: #51cf66; border: 1px solid #2b7a41; "
                "border-radius: 6px; padding: 8px;"
            )
        self.lbl_status.show()
