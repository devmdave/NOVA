from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Qt, Signal

class Sidebar(QWidget):
    """Sidebar navigation widget."""
    
    navigation_requested = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.setObjectName("Sidebar")
        self.setFixedWidth(220)
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 20, 15, 20)
        layout.setSpacing(10)
        
        # Branding
        brand_label = QLabel("NOVA")
        brand_label.setObjectName("SidebarBrand")
        brand_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(brand_label)
        
        layout.addSpacing(30)
        
        # Navigation Buttons
        self.btn_generate = self._create_nav_button("Generate", "generate")
        self.btn_trends = self._create_nav_button("Trends", "trends")
        self.btn_history = self._create_nav_button("History", "history")
        self.btn_models = self._create_nav_button("Models", "models")
        self.btn_settings = self._create_nav_button("Settings", "settings")

        layout.addWidget(self.btn_generate)
        layout.addWidget(self.btn_trends)
        layout.addWidget(self.btn_history)
        layout.addWidget(self.btn_models)
        layout.addWidget(self.btn_settings)

        # Spacer to push everything up
        layout.addStretch()

        # Set default active
        self._set_active_button(self.btn_generate)

    def _create_nav_button(self, text: str, page_id: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("NavButton")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda: self._handle_nav(btn, page_id))
        return btn

    def _handle_nav(self, button: QPushButton, page_id: str):
        self._set_active_button(button)
        self.navigation_requested.emit(page_id)

    def set_active_page(self, page_id: str) -> None:
        """Programmatically switch active navigation button."""
        mapping = {
            "generate": self.btn_generate,
            "trends": self.btn_trends,
            "history": self.btn_history,
            "models": self.btn_models,
            "settings": self.btn_settings,
        }
        btn = mapping.get(page_id)
        if btn:
            self._set_active_button(btn)

    def _set_active_button(self, active_btn: QPushButton):
        for btn in [self.btn_generate, self.btn_trends, self.btn_history, self.btn_models, self.btn_settings]:
            btn.setProperty("active", btn is active_btn)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
