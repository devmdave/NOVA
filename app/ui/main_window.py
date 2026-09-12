from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QStackedWidget
from PySide6.QtCore import Qt

from app.core.app_service import ApplicationService
from app.ui.components.sidebar import Sidebar
from app.ui.views.generate_view import GenerateView
from app.ui.views.models_view import ModelsView
from app.ui.views.placeholder_view import PlaceholderView


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

        # Views — only GenerateView receives the service
        self.views = {
            "generate": GenerateView(self._app_service),
            "history":  PlaceholderView("History"),
            "models":   ModelsView(self._app_service),
            "settings": PlaceholderView("Settings"),
        }
        for view in self.views.values():
            self.stacked_widget.addWidget(view)

        self._handle_navigation("generate")

    def _handle_navigation(self, page_id: str) -> None:
        if page_id in self.views:
            self.stacked_widget.setCurrentWidget(self.views[page_id])

    def closeEvent(self, event) -> None:  # noqa: N802
        """Gracefully shut down services when the window is closed."""
        self._app_service.shutdown()
        super().closeEvent(event)
