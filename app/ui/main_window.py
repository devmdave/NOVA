from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QStackedWidget
from PySide6.QtCore import Qt

from app.core.app_service import ApplicationService
from app.ui.components.sidebar import Sidebar
from app.ui.views.generate_view import GenerateView
from app.ui.views.history_view import HistoryView
from app.ui.views.models_view import ModelsView
from app.ui.views.settings_view import SettingsView
from app.ui.views.trends_view import TrendsView


class MainWindow(QMainWindow):
    """The main application window for NOVA."""

    def __init__(self, app_service: ApplicationService) -> None:
        super().__init__()
        self._app_service = app_service
        self.setWindowTitle("NOVA — AI Image Generation")
        self.resize(1100, 750)
        self.setMinimumSize(800, 600)
        self._setup_ui()

    def _setup_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QHBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Sidebar
        self.sidebar = Sidebar()
        self.sidebar.navigation_requested.connect(self._handle_navigation)
        layout.addWidget(self.sidebar)

        # Stacked content area
        self.stacked_widget = QStackedWidget()
        layout.addWidget(self.stacked_widget)

        # Views
        self.trends_view = TrendsView(self._app_service)
        self.trends_view.use_trend_requested.connect(self._on_use_trend)

        self.history_view = HistoryView(self._app_service)
        self.history_view.reuse_requested.connect(self._on_reuse_history)
        self.settings_view = SettingsView(self._app_service)

        self.views = {
            "generate": GenerateView(self._app_service),
            "trends":   self.trends_view,
            "history":  self.history_view,
            "models":   ModelsView(self._app_service),
            "settings": self.settings_view,
        }
        for view in self.views.values():
            self.stacked_widget.addWidget(view)

        self._handle_navigation("generate")

    def _handle_navigation(self, page_id: str) -> None:
        if page_id in self.views:
            self.stacked_widget.setCurrentWidget(self.views[page_id])

    def _on_use_trend(self, trend) -> None:
        """Handle prompt/settings transfer from Trends view to Generate view."""
        generate_view = self.views.get("generate")
        if generate_view and hasattr(generate_view, "apply_trend"):
            generate_view.apply_trend(trend)
        self.sidebar.set_active_page("generate")
        self._handle_navigation("generate")

    def _on_reuse_history(self, record) -> None:
        """Handle parameter reuse from history view."""
        generate_view = self.views.get("generate")
        if generate_view and hasattr(generate_view, "apply_history_record"):
            generate_view.apply_history_record(record)
        self.sidebar.set_active_page("generate")
        self._handle_navigation("generate")

    def closeEvent(self, event) -> None:  # noqa: N802
        """Gracefully shut down services when the window is closed."""
        self._app_service.shutdown()
        super().closeEvent(event)
