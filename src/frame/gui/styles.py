"""
FRAME Workstation GUI Theme & Stylesheet (Legacy / Clean Terminal Aesthetic)
No flashy icons, no unnecessary text. Crisp, high-contrast, institutional quant desk.
"""

QSS_STYLE = """
/* Global Window & Fonts */
QMainWindow, QDialog, QWidget {
    background-color: #0c0f17;
    color: #c9d1d9;
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Roboto", sans-serif;
    font-size: 12px;
}

/* ToolBar & MenuBar */
QMenuBar {
    background-color: #090c13;
    color: #8b949e;
    border-bottom: 1px solid #1b2130;
    padding: 2px;
}
QMenuBar::item:selected {
    background-color: #161c28;
    color: #f0f6fc;
}
QMenu {
    background-color: #0d111a;
    border: 1px solid #252d3d;
}
QMenu::item:selected {
    background-color: #1c2436;
    color: #f0f6fc;
}

/* Splitter & Separators */
QSplitter::handle {
    background-color: #161c28;
}

/* Frame & Panels */
QFrame.panel {
    background-color: #10141e;
    border: 1px solid #1c2333;
    border-radius: 4px;
}
QFrame.panel-card {
    background-color: #141926;
    border: 1px solid #212a3d;
    border-radius: 3px;
    padding: 8px;
}

/* Labels */
QLabel {
    color: #c9d1d9;
}
QLabel.section-header {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
    color: #8b949e;
    text-transform: uppercase;
}
QLabel.stat-value {
    font-size: 18px;
    font-weight: 700;
    font-family: "Consolas", "Courier New", monospace;
    color: #f0f6fc;
}
QLabel.stat-label {
    font-size: 10px;
    color: #6e7681;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* Buttons */
QPushButton {
    background-color: #161e2e;
    border: 1px solid #27334a;
    color: #c9d1d9;
    padding: 6px 14px;
    border-radius: 3px;
    font-weight: 600;
    font-size: 11px;
}
QPushButton:hover {
    background-color: #1c263b;
    border-color: #3b4c6e;
    color: #f0f6fc;
}
QPushButton:pressed {
    background-color: #121824;
}
QPushButton.primary-btn {
    background-color: #004d40;
    border: 1px solid #00bfa5;
    color: #e0f2f1;
}
QPushButton.primary-btn:hover {
    background-color: #00695c;
    border-color: #1de9b6;
    color: #ffffff;
}
QPushButton:disabled {
    background-color: #0e121a;
    border-color: #181f2b;
    color: #484f58;
}

/* ComboBox & Inputs */
QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #121722;
    border: 1px solid #222b3d;
    border-radius: 3px;
    color: #c9d1d9;
    padding: 5px 10px;
    font-size: 11px;
}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {
    border-color: #313f59;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox QAbstractItemView {
    background-color: #0d111a;
    border: 1px solid #252d3d;
    selection-background-color: #1c2436;
    selection-color: #f0f6fc;
    color: #c9d1d9;
    outline: none;
}
QComboBox QAbstractItemView::item {
    min-height: 24px;
    padding: 3px 8px;
}
QComboBox QAbstractItemView QScrollBar:vertical {
    width: 8px;
    min-width: 8px;
    max-width: 8px;
    background-color: #0a0d14;
}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QSpinBox::up-button, QSpinBox::down-button {
    background-color: #161e2e;
    border: 1px solid #222b3d;
    width: 16px;
}
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover,
QSpinBox::up-button:hover, QSpinBox::down-button:hover {
    background-color: #27354d;
}

/* Tab Widget */
QTabWidget::pane {
    border: 1px solid #1c2333;
    background-color: #10141e;
    top: -1px;
}
QTabBar::tab {
    background-color: #0c0f17;
    border: 1px solid #1c2333;
    border-bottom: none;
    color: #8b949e;
    padding: 7px 16px;
    margin-right: 2px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
}
QTabBar::tab:selected {
    background-color: #10141e;
    color: #d4af37;
    border-top: 2px solid #d4af37;
}
QTabBar::tab:hover:!selected {
    background-color: #141926;
    color: #c9d1d9;
}

/* Tables */
QTableWidget, QTableView {
    background-color: #0e121a;
    border: 1px solid #1c2333;
    gridline-color: #18202e;
    color: #c9d1d9;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 11px;
    selection-background-color: #1b263b;
    selection-color: #f0f6fc;
}
QHeaderView::section {
    background-color: #141926;
    color: #8b949e;
    padding: 4px;
    border: 1px solid #1c2333;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
}

/* Terminal / Log Output */
QPlainTextEdit.terminal {
    background-color: #080a0f;
    border: 1px solid #181f2b;
    color: #8b949e;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 11px;
    padding: 6px;
    line-height: 1.4;
}

/* ScrollBars */
QScrollBar:vertical {
    border: none;
    background-color: #0a0d14;
    width: 8px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background-color: #212a3d;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background-color: #313f59;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
    background: none;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: #0a0d14;
}
QScrollBar:horizontal {
    border: none;
    background-color: #0a0d14;
    height: 8px;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background-color: #212a3d;
    min-width: 20px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover {
    background-color: #313f59;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
    background: none;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: #0a0d14;
}
"""
