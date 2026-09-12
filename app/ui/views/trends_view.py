"""
TrendsView — gallery and prompt template inspection view for AI Trends.
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QSize, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.app_service import ApplicationService
from app.trends.models import Trend

logger = logging.getLogger("nova.ui.trends_view")


class TrendsView(QWidget):
    """View for discovering AI image generation trends and prompt templates."""

    use_trend_requested = Signal(object)  # Emits Trend object when user clicks "Use in Generate"

    def __init__(self, app_service: ApplicationService) -> None:
        super().__init__()
        self._service = app_service
        self._trends_service = app_service.trends_service
        self._selected_trend: Optional[Trend] = None
        self._all_trends: list[Trend] = []

        self._setup_ui()
        self.reload_trends()

    # ---------------------------------------------------------------------- #
    # UI Setup                                                                 #
    # ---------------------------------------------------------------------- #

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # Header bar
        header_layout = QHBoxLayout()
        lbl_title = QLabel("AI Trends & Prompts")
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(lbl_title)

        header_layout.addStretch()

        # Category filter
        lbl_cat = QLabel("Category:")
        self.cmb_category = QComboBox()
        self.cmb_category.setMinimumWidth(160)
        self.cmb_category.currentIndexChanged.connect(self._on_filter_changed)
        header_layout.addWidget(lbl_cat)
        header_layout.addWidget(self.cmb_category)

        # Search bar
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Search trends, prompts, tags…")
        self.txt_search.setClearButtonEnabled(True)
        self.txt_search.setFixedWidth(240)
        self.txt_search.textChanged.connect(self._on_filter_changed)
        header_layout.addWidget(self.txt_search)

        root.addLayout(header_layout)

        # Main Splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ---- Left Pane: Trend Cards List --------------------------------- #
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 10, 0)
        left_layout.setSpacing(8)

        self.lbl_count = QLabel("0 trend(s) available")
        self.lbl_count.setStyleSheet("color: #888888; font-size: 12px;")
        left_layout.addWidget(self.lbl_count)

        self.list_trends = QListWidget()
        self.list_trends.setObjectName("TrendsList")
        self.list_trends.setStyleSheet(
            "QListWidget::item { padding: 10px; border-radius: 6px; background-color: #1e1e24; margin-bottom: 6px; }"
            "QListWidget::item:selected { background-color: #2b3a55; border: 1px solid #4a7bb0; }"
        )
        self.list_trends.currentItemChanged.connect(self._on_item_selected)
        left_layout.addWidget(self.list_trends)

        self.lbl_empty = QLabel("No matching AI trends found.")
        self.lbl_empty.setAlignment(Qt.AlignCenter)
        self.lbl_empty.setStyleSheet("color: #777; font-size: 14px; margin: 40px;")
        left_layout.addWidget(self.lbl_empty)

        # ---- Right Pane: Trend Inspection Detail ------------------------- #
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 0, 0, 0)
        right_layout.setSpacing(12)

        # Header Title & Category Badge
        title_box = QVBoxLayout()
        self.lbl_detail_category = QLabel("CATEGORY")
        self.lbl_detail_category.setStyleSheet(
            "background-color: #2c3e50; color: #3498db; font-size: 10px; font-weight: bold; "
            "padding: 2px 8px; border-radius: 4px; max-width: 140px;"
        )
        self.lbl_detail_title = QLabel("Select a trend to view details")
        self.lbl_detail_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.lbl_detail_title.setWordWrap(True)

        title_box.addWidget(self.lbl_detail_category)
        title_box.addWidget(self.lbl_detail_title)
        right_layout.addLayout(title_box)

        # Action bar
        actions_layout = QHBoxLayout()
        self.btn_use_generate = QPushButton("Use in Generate")
        self.btn_use_generate.setObjectName("PrimaryButton")
        self.btn_use_generate.setCursor(Qt.PointingHandCursor)
        self.btn_use_generate.setEnabled(False)
        self.btn_use_generate.clicked.connect(self._on_use_clicked)
        actions_layout.addWidget(self.btn_use_generate)

        self.btn_open_source = QPushButton("Open Reference Link")
        self.btn_open_source.setCursor(Qt.PointingHandCursor)
        self.btn_open_source.setEnabled(False)
        self.btn_open_source.clicked.connect(self._on_open_source_clicked)
        actions_layout.addWidget(self.btn_open_source)

        actions_layout.addStretch()
        right_layout.addLayout(actions_layout)

        # Description
        desc_group = QGroupBox("Overview & Style")
        desc_layout = QVBoxLayout(desc_group)
        self.lbl_desc_val = QLabel("Select a trend template from the list on the left.")
        self.lbl_desc_val.setWordWrap(True)
        self.lbl_desc_val.setStyleSheet("color: #cccccc;")
        desc_layout.addWidget(self.lbl_desc_val)
        right_layout.addWidget(desc_group)

        # Prompt & Negative Prompt
        prompt_group = QGroupBox("Prompt Template")
        prompt_layout = QVBoxLayout(prompt_group)
        self.txt_prompt_val = QTextEdit()
        self.txt_prompt_val.setReadOnly(True)
        self.txt_prompt_val.setMaximumHeight(100)
        prompt_layout.addWidget(self.txt_prompt_val)
        right_layout.addWidget(prompt_group)

        neg_group = QGroupBox("Negative Prompt")
        neg_layout = QVBoxLayout(neg_group)
        self.txt_neg_val = QTextEdit()
        self.txt_neg_val.setReadOnly(True)
        self.txt_neg_val.setMaximumHeight(65)
        neg_layout.addWidget(self.txt_neg_val)
        right_layout.addWidget(neg_group)

        # Recommended Settings
        settings_group = QGroupBox("Recommended Settings")
        form_settings = QFormLayout(settings_group)
        form_settings.setSpacing(8)

        self.lbl_rec_dim = QLabel("—")
        self.lbl_rec_steps = QLabel("—")
        self.lbl_rec_guidance = QLabel("—")
        self.lbl_rec_mode = QLabel("—")

        form_settings.addRow("Recommended Dimensions:", self.lbl_rec_dim)
        form_settings.addRow("Recommended Steps:", self.lbl_rec_steps)
        form_settings.addRow("Recommended Guidance / CFG:", self.lbl_rec_guidance)
        form_settings.addRow("Recommended Mode:", self.lbl_rec_mode)

        right_layout.addWidget(settings_group)

        right_layout.addStretch()
        right_scroll.setWidget(right_widget)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_scroll)
        splitter.setSizes([420, 580])

        root.addWidget(splitter)

    # ---------------------------------------------------------------------- #
    # Data Population                                                          #
    # ---------------------------------------------------------------------- #

    def reload_trends(self) -> None:
        """Reload categories and trend list from service."""
        categories = self._trends_service.get_categories()
        self.cmb_category.blockSignals(True)
        self.cmb_category.clear()
        for cat in categories:
            self.cmb_category.addItem(cat)
        self.cmb_category.blockSignals(False)

        self._filter_and_populate()

    def _filter_and_populate(self) -> None:
        """Filter trends and update list widget."""
        query = self.txt_search.text().strip()
        cat = self.cmb_category.currentText() or "All"

        records = self._trends_service.search_trends(query=query, category=cat)
        self.list_trends.clear()

        for trend in records:
            item = QListWidgetItem()

            # Custom text formatting for trend card
            title_str = f"[{trend.category}] {trend.title}"
            desc_str = trend.description[:70] + "…" if len(trend.description) > 70 else trend.description
            item.setText(f"{title_str}\n{desc_str}")
            item.setToolTip(f"{trend.title}\n{trend.prompt}")
            item.setData(Qt.UserRole, trend)

            self.list_trends.addItem(item)

        self.lbl_count.setText(f"{len(records)} trend(s) available")

        if len(records) == 0:
            self.list_trends.hide()
            self.lbl_empty.show()
            self._clear_details()
        else:
            self.list_trends.show()
            self.lbl_empty.hide()
            if self.list_trends.count() > 0:
                self.list_trends.setCurrentRow(0)

    def _clear_details(self) -> None:
        self._selected_trend = None
        self.lbl_detail_category.setText("CATEGORY")
        self.lbl_detail_title.setText("Select a trend to view details")
        self.lbl_desc_val.setText("No trend selected.")
        self.txt_prompt_val.setPlainText("")
        self.txt_neg_val.setPlainText("")
        self.lbl_rec_dim.setText("—")
        self.lbl_rec_steps.setText("—")
        self.lbl_rec_guidance.setText("—")
        self.lbl_rec_mode.setText("—")

        self.btn_use_generate.setEnabled(False)
        self.btn_open_source.setEnabled(False)

    def _show_details(self, trend: Trend) -> None:
        self._selected_trend = trend

        self.lbl_detail_category.setText(trend.category.upper())
        self.lbl_detail_title.setText(trend.title)
        self.lbl_desc_val.setText(trend.description)

        self.txt_prompt_val.setPlainText(trend.prompt)
        self.txt_neg_val.setPlainText(trend.negative_prompt or "None")

        rec = trend.recommended_settings or {}
        w = rec.get("width", 1024)
        h = rec.get("height", 1024)
        steps = rec.get("steps", 20)
        guidance = rec.get("guidance", 7.5)
        mode = rec.get("mode", "text-to-image")

        self.lbl_rec_dim.setText(f"{w} × {h}")
        self.lbl_rec_steps.setText(str(steps))
        self.lbl_rec_guidance.setText(f"{guidance:.1f}")
        self.lbl_rec_mode.setText(mode)

        self.btn_use_generate.setEnabled(True)
        self.btn_open_source.setEnabled(bool(trend.source_url))

    # ---------------------------------------------------------------------- #
    # Slots                                                                    #
    # ---------------------------------------------------------------------- #

    @Slot(QListWidgetItem, QListWidgetItem)
    def _on_item_selected(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        if current is None:
            self._clear_details()
            return
        trend: Trend = current.data(Qt.UserRole)
        if trend:
            self._show_details(trend)

    @Slot()
    def _on_filter_changed(self) -> None:
        self._filter_and_populate()

    @Slot()
    def _on_use_clicked(self) -> None:
        if self._selected_trend:
            logger.info("User selected trend %s ('%s') to use in Generate", self._selected_trend.id, self._selected_trend.title)
            self.use_trend_requested.emit(self._selected_trend)

    @Slot()
    def _on_open_source_clicked(self) -> None:
        if self._selected_trend and self._selected_trend.source_url:
            QDesktopServices.openUrl(QUrl(self._selected_trend.source_url))
