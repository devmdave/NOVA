from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

class PlaceholderView(QWidget):
    """A generic placeholder view for unimplemented navigation destinations."""
    
    def __init__(self, title: str):
        super().__init__()
        layout = QVBoxLayout(self)
        
        lbl = QLabel(f"{title} (Coming Soon)")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("font-size: 24px; color: #666;")
        
        layout.addWidget(lbl)
