"""
SettingsPanel — image-generation parameter controls.

All parameters map 1-to-1 to GenerationRequest fields.
Defaults can be primed from a ModelSpec via apply_model_spec().
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from app.models.spec import ModelSpec


class SettingsPanel(QGroupBox):
    """Panel containing image generation settings."""

    def __init__(self) -> None:
        super().__init__("Settings")
        self.setObjectName("SettingsPanel")
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # -- Width & Height ------------------------------------------------- #
        size_layout = QHBoxLayout()
        self.spin_width = self._create_spinbox(256, 2048, 1024, 64)
        self.spin_height = self._create_spinbox(256, 2048, 1024, 64)
        size_layout.addWidget(QLabel("Width:"))
        size_layout.addWidget(self.spin_width)
        size_layout.addWidget(QLabel("Height:"))
        size_layout.addWidget(self.spin_height)
        layout.addLayout(size_layout)

        # -- Steps ---------------------------------------------------------- #
        steps_layout = QHBoxLayout()
        self.lbl_steps_val = QLabel("4")
        self.spin_steps = self._create_spinbox(1, 150, 4, 1)
        self.spin_steps.valueChanged.connect(
            lambda v: self.lbl_steps_val.setText(str(v))
        )
        steps_layout.addWidget(QLabel("Steps:"))
        steps_layout.addWidget(self.spin_steps)
        steps_layout.addWidget(self.lbl_steps_val)
        layout.addLayout(steps_layout)

        # -- Guidance / CFG ------------------------------------------------- #
        guidance_layout = QHBoxLayout()
        self.slider_guidance = QSlider(Qt.Horizontal)
        self.slider_guidance.setRange(0, 300)   # 0.0 – 30.0 in 0.1 increments
        self.slider_guidance.setValue(0)         # 0.0 (FLUX default)
        self.lbl_guidance_val = QLabel("0.0")
        self.slider_guidance.valueChanged.connect(
            lambda v: self.lbl_guidance_val.setText(f"{v / 10.0:.1f}")
        )
        guidance_layout.addWidget(QLabel("Guidance:"))
        guidance_layout.addWidget(self.slider_guidance)
        guidance_layout.addWidget(self.lbl_guidance_val)
        layout.addLayout(guidance_layout)

        # -- Seed ----------------------------------------------------------- #
        seed_layout = QHBoxLayout()
        self.spin_seed = self._create_spinbox(-1, 2_147_483_647, -1, 1)
        seed_layout.addWidget(QLabel("Seed (-1 = random):"))
        seed_layout.addWidget(self.spin_seed)
        layout.addLayout(seed_layout)

    # ---------------------------------------------------------------------- #
    # Model-aware defaults                                                     #
    # ---------------------------------------------------------------------- #

    def apply_model_spec(self, spec: "ModelSpec") -> None:
        """Prime the settings UI from a ModelSpec's recommended defaults."""
        self.spin_steps.setValue(spec.steps_default)
        self.spin_steps.setMinimum(spec.steps_min)
        self.spin_steps.setMaximum(spec.steps_max)

        guidance_int = int(round(spec.guidance_default * 10))
        self.slider_guidance.setValue(max(0, min(guidance_int, 300)))

        self.spin_width.setValue(spec.default_width)
        self.spin_height.setValue(spec.default_height)

    # ---------------------------------------------------------------------- #
    # Public API                                                               #
    # ---------------------------------------------------------------------- #

    def get_settings(self) -> dict:
        """Return current settings as a dictionary matching GenerationRequest fields."""
        return {
            "width":    self.spin_width.value(),
            "height":   self.spin_height.value(),
            "steps":    self.spin_steps.value(),
            "guidance": self.slider_guidance.value() / 10.0,
            "seed":     self.spin_seed.value(),
        }

    def set_enabled_all(self, enabled: bool) -> None:
        """Enable or disable all controls (called during generation)."""
        for widget in (
            self.spin_width,
            self.spin_height,
            self.spin_steps,
            self.slider_guidance,
            self.spin_seed,
        ):
            widget.setEnabled(enabled)

    # ---------------------------------------------------------------------- #
    # Helpers                                                                  #
    # ---------------------------------------------------------------------- #

    @staticmethod
    def _create_spinbox(
        min_val: int, max_val: int, default: int, step: int
    ) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(min_val, max_val)
        spin.setValue(default)
        spin.setSingleStep(step)
        spin.setButtonSymbols(QSpinBox.NoButtons)
        return spin
