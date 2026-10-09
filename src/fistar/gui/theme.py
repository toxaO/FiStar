"""Shared visual styling for FiStar windows."""
from pathlib import Path

STYLE = """
QWidget { color: #253b49; font-size: 13px; }
QMainWindow, QDialog { background: #f3f6f8; }
#analysisPanel { background: #f3f6f8; }
QTabWidget::pane { border: 0; }
QTabBar::tab { background: #e5edf2; padding: 8px 20px; border: 0; }
QTabBar::tab:selected { background: #f3f6f8; color: #087b87; font-weight: 600; }
QGroupBox { background: #ffffff; border: 1px solid #dce5eb; border-radius: 7px;
            margin-top: 11px; padding: 14px 10px 10px; font-weight: 600; }
QFrame#stableImageTools { background: #ffffff; border: 1px solid #dce5eb; border-radius: 5px; }
QGroupBox#analysisFrame QGroupBox { padding: 7px 7px 5px; margin-top: 9px; }
QGroupBox#resolutionSettings { padding: 6px 4px 4px; margin-top: 10px; }
QGroupBox#analysisFrame { padding: 5px 2px 2px; margin-top: 10px; }
QGroupBox#imageFile { padding: 5px 6px 4px; margin-top: 10px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
QLineEdit, QComboBox, QDoubleSpinBox { background: #ffffff; border: 1px solid #cbd8e0;
                                     border-radius: 4px; min-height: 24px; padding: 3px 6px; }
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus { border: 1px solid #0794a3; }
QLineEdit:disabled { background: #eef2f5; color: #7b8e9a; border-color: #dce5eb; }
QComboBox { padding-right: 28px; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right;
                      border: 0; border-left: 1px solid #dce5eb; width: 24px; background: #eef4f7;
                      border-top-right-radius: 4px; border-bottom-right-radius: 4px; }
QComboBox::down-arrow { image: url("@DOWN_ARROW@"); width: 12px; height: 8px; }
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { border: 0; width: 18px; }
QPushButton { background: #eef4f7; border: 1px solid #cbd8e0; border-radius: 5px;
              padding: 7px 10px; min-height: 20px; }
QPushButton[laserSelection="true"] { border-width: 2px; }
QPushButton[laserSelection="true"]:checked { background: #087f8c; color: #ffffff; border: 2px solid #055e68; font-weight: 600; }
QPushButton:hover { background: #e3eef3; border-color: #91b9c5; }
QPushButton[primary="true"] { background: #087f8c; border-color: #087f8c; color: #ffffff; font-weight: 600; }
QPushButton[primary="true"]:hover { background: #066c78; }
QPushButton:disabled { background: #e9eef1; border-color: #dce5eb; color: #85949e; }
QToolButton { border: 1px solid transparent; border-radius: 4px; padding: 3px; }
QToolButton:hover, QToolButton:checked { background: #e1eff2; border-color: #a8ced6; }
QToolButton[imageTool="true"] { background: #ffffff; border: 1px solid #b9cbd5; }
QToolButton[imageTool="true"]:hover, QToolButton[imageTool="true"]:checked { background: #e1eff2; border-color: #78b4c1; }
QToolButton[imageTool="true"]:disabled { background: #f1f4f6; border-color: #dce5eb; }
QScrollArea { border: 0; background: transparent; }
QListWidget, QTableWidget { background: #ffffff; alternate-background-color: #f3f7fa;
                           border: 1px solid #dce5eb; border-radius: 4px; selection-background-color: #d6edf1; selection-color: #253b49; }
QHeaderView::section { background: #eaf1f5; padding: 5px; border: 0; border-bottom: 1px solid #dce5eb; }
QCheckBox { spacing: 5px; }
QLabel[muted="true"] { color: #516978; font-size: 12px; }
QLabel:disabled { color: #85949e; }
QFrame[displayOptions="true"] { background: #ffffff; border: 1px solid #dce5eb; border-radius: 5px; }
QStatusBar { background: #eaf0f4; color: #647b89; }
QToolTip { background: #253b49; color: #ffffff; border: 0; padding: 5px; }
""".replace("@DOWN_ARROW@", (Path(__file__).parent/"assets/icons/chevron_down.svg").as_posix())
