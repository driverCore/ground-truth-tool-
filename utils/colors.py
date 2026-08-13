"""Color management for the Kabaddi GT Track Editor."""
from PySide6.QtGui import QColor

# ── Track ID colour palette ────────────────────────────────────────────────
_PALETTE = [
    "#FF5733", "#33A0FF", "#FFCC33", "#57D68C",
    "#FF66CC", "#00CCCC", "#B266FF", "#FF9900",
    "#33FFCC", "#FF3366", "#7EC8E3", "#F4A261",
    "#E76F51", "#2A9D8F", "#E9C46A", "#264653",
]

# ── Status indicator colours ───────────────────────────────────────────────
STATUS_COLORS: dict[str, QColor] = {
    "unreviewed": QColor("#8b949e"),   # grey
    "edited":     QColor("#d29922"),   # amber
    "verified":   QColor("#3fb950"),   # green
}

BBOX_ALPHA = 220  # transparency for bbox fill overlays

# ── Timeline marker colours ────────────────────────────────────────────────
TIMELINE_COLORS: dict[str, QColor] = {
    "switch":   QColor(248, 81,  73,  200),
    "edited":   QColor(210, 153, 34,  200),
    "verified": QColor(63,  185, 80,  200),
    "current":  QColor(255, 255, 255, 255),
    "default":  QColor(60,  60,  80,  200),
}

# ── Dark-theme palette constants ───────────────────────────────────────────
BG_BASE    = "#0d1117"
BG_SURFACE = "#161b22"
BG_PANEL   = "#21262d"
BG_WIDGET  = "#2d333b"
ACCENT     = "#388bfd"
ACCENT_ALT = "#3fb950"
WARNING    = "#d29922"
DANGER     = "#f85149"
TEXT_PRI   = "#c9d1d9"
TEXT_SEC   = "#8b949e"
BORDER     = "#30363d"
BORDER_HL  = "#388bfd"


def track_color(track_id: int) -> QColor:
    """Return a stable, vibrant QColor for a given track ID."""
    return QColor(_PALETTE[abs(track_id) % len(_PALETTE)])


def bbox_border_color(track_id: int, status: str) -> QColor:
    """Bbox outline colour: status overrides track colour when verified/edited."""
    if status == "verified":
        return QColor(ACCENT_ALT)
    if status == "edited":
        return QColor(WARNING)
    return track_color(track_id)


def label_bg_color(track_id: int, status: str) -> QColor:
    """Label background colour (slightly dimmed version of border colour)."""
    c = bbox_border_color(track_id, status)
    c.setAlpha(200)
    return c


# ── Application stylesheet ─────────────────────────────────────────────────
APP_STYLESHEET = f"""
QMainWindow, QDialog, QWidget {{
    background-color: {BG_BASE};
    color: {TEXT_PRI};
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 12px;
}}
QMenuBar {{
    background-color: {BG_SURFACE};
    color: {TEXT_PRI};
    border-bottom: 1px solid {BORDER};
}}
QMenuBar::item:selected {{
    background-color: {BG_PANEL};
}}
QMenu {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
}}
QMenu::item:selected {{
    background-color: {ACCENT};
    color: white;
}}
QSplitter::handle {{
    background-color: {BORDER};
    width: 2px;
    height: 2px;
}}
QPushButton {{
    background-color: {BG_WIDGET};
    color: {TEXT_PRI};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 5px 14px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {BG_PANEL};
    border-color: {BORDER_HL};
}}
QPushButton:pressed {{
    background-color: {ACCENT};
    color: white;
}}
QPushButton:disabled {{
    color: {TEXT_SEC};
    border-color: {BORDER};
}}
QPushButton#btn_primary {{
    background-color: {ACCENT};
    color: white;
    border-color: {ACCENT};
    font-weight: 600;
}}
QPushButton#btn_primary:hover {{
    background-color: #1f6feb;
}}
QPushButton#btn_danger {{
    background-color: {BG_WIDGET};
    color: {DANGER};
    border-color: {DANGER};
}}
QPushButton#btn_danger:hover {{
    background-color: {DANGER};
    color: white;
}}
QPushButton#btn_success {{
    background-color: {BG_WIDGET};
    color: {ACCENT_ALT};
    border-color: {ACCENT_ALT};
}}
QPushButton#btn_success:hover {{
    background-color: {ACCENT_ALT};
    color: {BG_BASE};
}}
QLabel {{
    color: {TEXT_PRI};
}}
QLabel#label_secondary {{
    color: {TEXT_SEC};
    font-size: 11px;
}}
QLabel#label_stat_value {{
    color: {ACCENT};
    font-size: 14px;
    font-weight: bold;
}}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {BG_WIDGET};
    color: {TEXT_PRI};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 3px 6px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border-color: {BORDER_HL};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background-color: {BG_PANEL};
    border: none;
    width: 16px;
}}
QComboBox::drop-down {{
    background-color: {BG_PANEL};
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
}}
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 8px;
    font-weight: 600;
    color: {TEXT_SEC};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}}
QScrollBar:vertical {{
    background: {BG_SURFACE};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {BG_WIDGET};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{
    background: {TEXT_SEC};
}}
QScrollBar:horizontal {{
    background: {BG_SURFACE};
    height: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: {BG_WIDGET};
    border-radius: 4px;
    min-width: 20px;
}}
QListWidget {{
    background-color: {BG_SURFACE};
    border: 1px solid {BORDER};
    border-radius: 4px;
}}
QListWidget::item {{
    padding: 4px 6px;
    border-bottom: 1px solid {BG_WIDGET};
}}
QListWidget::item:selected {{
    background-color: {ACCENT};
    color: white;
}}
QListWidget::item:hover {{
    background-color: {BG_PANEL};
}}
QStatusBar {{
    background-color: {BG_SURFACE};
    border-top: 1px solid {BORDER};
    color: {TEXT_SEC};
    font-size: 11px;
}}
QToolTip {{
    background-color: {BG_PANEL};
    color: {TEXT_PRI};
    border: 1px solid {BORDER};
    padding: 4px;
    border-radius: 3px;
}}
QRadioButton {{
    color: {TEXT_PRI};
    spacing: 6px;
}}
QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border-radius: 7px;
    border: 2px solid {BORDER};
    background: {BG_WIDGET};
}}
QRadioButton::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: {BG_WIDGET};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}
QSplitter::handle:horizontal {{
    background-color: {BORDER};
    width: 3px;
}}
QSplitter::handle:vertical {{
    background-color: {BORDER};
    height: 3px;
}}
QFrame[frameShape="4"] {{
    color: {BORDER};
}}
QFrame[frameShape="5"] {{
    color: {BORDER};
}}
"""
