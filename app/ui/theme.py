from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QPalette, QColor

def apply_theme(app: QApplication):
    """Apply global stylesheet/theme to the application."""
    
    # Set default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    
    # Modern dark theme
    stylesheet = """
        /* Main background */
        QMainWindow, QWidget#Sidebar, QWidget#ImagePreviewContainer {
            background-color: #121212;
            color: #E0E0E0;
        }
        
        /* Sidebar Styling */
        QWidget#Sidebar {
            background-color: #1A1A1A;
            border-right: 1px solid #2C2C2C;
        }
        QLabel#SidebarBrand {
            font-size: 28px;
            font-weight: 800;
            color: #FFFFFF;
            letter-spacing: 2px;
            margin-bottom: 20px;
        }
        QPushButton#NavButton {
            background-color: transparent;
            color: #A0A0A0;
            border: none;
            text-align: left;
            padding: 12px 20px;
            font-size: 14px;
            font-weight: 600;
            border-radius: 6px;
        }
        QPushButton#NavButton:hover {
            background-color: #252525;
            color: #FFFFFF;
        }
        QPushButton#NavButton[active="true"] {
            background-color: #2D2D2D;
            color: #4DA6FF;
        }
        
        /* Content Area */
        QGroupBox {
            border: 1px solid #2C2C2C;
            border-radius: 8px;
            margin-top: 15px;
            font-weight: bold;
            padding: 15px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 5px;
            color: #A0A0A0;
        }
        
        /* Inputs & Controls */
        QTextEdit, QSpinBox {
            background-color: #1E1E1E;
            border: 1px solid #333333;
            border-radius: 6px;
            padding: 8px;
            color: #E0E0E0;
            selection-background-color: #4DA6FF;
        }
        QTextEdit:focus, QSpinBox:focus {
            border: 1px solid #4DA6FF;
        }
        
        /* Primary Button */
        QPushButton#PrimaryButton {
            background-color: #4DA6FF;
            color: #121212;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: bold;
        }
        QPushButton#PrimaryButton:hover {
            background-color: #66B2FF;
        }
        QPushButton#PrimaryButton:pressed {
            background-color: #3399FF;
        }
        QPushButton#PrimaryButton:disabled {
            background-color: #333333;
            color: #666666;
        }
        
        /* Field labels above inputs */
        QLabel#FieldLabel {
            color: #A0A0A0;
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }

        /* Secondary / Cancel button */
        QPushButton#SecondaryButton {
            background-color: #2A2A2A;
            color: #A0A0A0;
            border: 1px solid #3A3A3A;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
        }
        QPushButton#SecondaryButton:hover {
            background-color: #333333;
            color: #FFFFFF;
        }
        QPushButton#SecondaryButton:disabled {
            background-color: #1E1E1E;
            color: #444444;
            border-color: #2A2A2A;
        }

        /* Progress bar */
        QProgressBar#GenerationProgress {
            background-color: #1E1E1E;
            border: none;
            border-radius: 3px;
            height: 6px;
        }
        QProgressBar#GenerationProgress::chunk {
            background-color: #4DA6FF;
            border-radius: 3px;
        }
        
        QLabel#ProgressStatusLabel {
            color: #A0A0A0;
            font-size: 11px;
            font-weight: 600;
        }

        /* Image Preview Area */
        QWidget#ImagePreviewContainer {
            background-color: #1A1A1A;
            border: 2px dashed #333333;
            border-radius: 12px;
        }
        QLabel#ImagePreviewLabel {
            font-size: 18px;
            color: #888888;
        }
        QLabel#ImagePreviewLabel[previewState="generating"] {
            color: #4DA6FF;
        }
        QLabel#ImagePreviewLabel[previewState="completed"] {
            color: #4DCC88;
            font-size: 20px;
            font-weight: bold;
        }
        QLabel#ImagePreviewLabel[previewState="error"] {
            color: #FF5555;
        }
        QLabel#ImagePreviewMeta {
            color: #666666;
            font-size: 11px;
        }
        
        /* Model Status Bar */
        QLabel#ModelStatusLabel {
            font-size: 11px;
            font-weight: bold;
            padding: 8px 12px;
            border-radius: 6px;
            background-color: #1A1A1A;
            border: 1px solid #2C2C2C;
            color: #A0A0A0;
        }
        QLabel#ModelStatusLabel[modelStatus="ready"] {
            color: #4DCC88;
            border-color: #2A4030;
            background-color: #14221A;
        }
        QLabel#ModelStatusLabel[modelStatus="warning"] {
            color: #FFB84D;
            border-color: #40301A;
            background-color: #221A0F;
        }
        QLabel#ModelStatusLabel[modelStatus="error"] {
            color: #FF5555;
            border-color: #401A1A;
            background-color: #220F0F;
        }
        
        /* Sliders */
        QSlider::groove:horizontal {
            border: 1px solid #333;
            height: 6px;
            background: #1E1E1E;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: #4DA6FF;
            border: 1px solid #4DA6FF;
            width: 14px;
            margin-top: -4px;
            margin-bottom: -4px;
            border-radius: 7px;
        }
        
        /* Models View Styles */
        QLabel#ViewTitle {
            font-size: 24px;
            font-weight: bold;
            color: #FFFFFF;
        }
        QLabel#SectionTitle {
            font-size: 16px;
            font-weight: bold;
            color: #E0E0E0;
            margin-top: 10px;
        }
        QWidget#Card, QWidget#ModelCard, QWidget#RecommendationCard {
            background-color: #1A1A1A;
            border: 1px solid #2C2C2C;
            border-radius: 8px;
            padding: 16px;
        }
        QWidget#RecommendationCard[recState="good"] {
            border-left: 4px solid #4DCC88;
        }
        QWidget#RecommendationCard[recState="bad"] {
            border-left: 4px solid #FF5555;
        }
        QLabel#ModelCardTitle {
            font-size: 16px;
            color: #FFFFFF;
        }
        QLabel#ModelCardStatus {
            font-size: 12px;
            font-weight: bold;
            padding: 4px 8px;
            border-radius: 4px;
        }
        QLabel#ModelCardStatus[statusState="ready"] {
            background-color: #14221A;
            color: #4DCC88;
        }
        QLabel#ModelCardStatus[statusState="missing"] {
            background-color: #220F0F;
            color: #FF5555;
        }
        QLabel#ModelCardDetails {
            font-size: 12px;
            color: #A0A0A0;
        }
        QLabel#ModelCardDesc {
            font-size: 13px;
            color: #CCCCCC;
            margin-top: 4px;
        }

        /* Splitter */
        QSplitter::handle {
            background-color: #2C2C2C;
            width: 2px;
        }
    """
    app.setStyleSheet(stylesheet)
