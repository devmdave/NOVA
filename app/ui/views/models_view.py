"""
Models View — hardware detection, model selection, and compatibility display.
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.app_service import ApplicationService
from app.models.selection import ModelCompatibility, ModelRecommendation
from app.models.spec import ModelSpec, ModelStatus

logger = logging.getLogger("nova.ui.models_view")


class ModelsView(QWidget):
    def __init__(self, app_service: ApplicationService) -> None:
        super().__init__()
        self._service = app_service
        self._recommendation: Optional[ModelRecommendation] = None
        
        self._setup_ui()
        self._refresh_data()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 20, 20, 20)
        root_layout.setSpacing(20)

        title = QLabel("Hardware & Models")
        title.setObjectName("ViewTitle")
        root_layout.addWidget(title)

        # Scroll area for the content
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
        models_label = QLabel("Available Models")
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
        specs = self._service.model_registry.list_all()
        rec = self._service.model_selection.evaluate(hw, specs)
        self._recommendation = rec
        
        if rec.recommended_model_id:
            spec = self._service.model_registry.get(rec.recommended_model_id)
            self.lbl_recommendation.setText(
                f"<b>Recommended Model:</b> {spec.display_name}<br><br>"
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

        # Render models list
        # Clear existing
        while self.models_list_layout.count():
            item = self.models_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        for spec in specs:
            eval_result = rec.evaluations.get(spec.model_id)
            card = self._create_model_card(spec, eval_result)
            self.models_list_layout.addWidget(card)

    def _create_model_card(self, spec: ModelSpec, compat: Optional[ModelCompatibility]) -> QWidget:
        card = QWidget()
        card.setObjectName("ModelCard")
        layout = QVBoxLayout(card)
        layout.setSpacing(8)
        
        # Header (Name + Status)
        header_layout = QHBoxLayout()
        name_lbl = QLabel(f"<b>{spec.display_name}</b>")
        name_lbl.setObjectName("ModelCardTitle")
        
        status_lbl = QLabel()
        status_lbl.setObjectName("ModelCardStatus")
        if spec.status == ModelStatus.NOT_INSTALLED:
            status_lbl.setText("Not Installed")
            status_lbl.setProperty("statusState", "missing")
        elif spec.status == ModelStatus.INSTALLED:
            status_lbl.setText("Installed")
            status_lbl.setProperty("statusState", "ready")
        else:
            status_lbl.setText(spec.status.name)
            status_lbl.setProperty("statusState", "ready")
            
        header_layout.addWidget(name_lbl)
        header_layout.addStretch()
        header_layout.addWidget(status_lbl)
        layout.addLayout(header_layout)
        
        # Details
        details_str = f"Min VRAM: {spec.min_vram_gb} GB | Size: {spec.model_size_gb} GB | Precision: {spec.precision}"
        details_lbl = QLabel(details_str)
        details_lbl.setObjectName("ModelCardDetails")
        layout.addWidget(details_lbl)
        
        desc_lbl = QLabel(spec.description)
        desc_lbl.setWordWrap(True)
        desc_lbl.setObjectName("ModelCardDesc")
        layout.addWidget(desc_lbl)
        
        # Compatibility
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
            
        return card
