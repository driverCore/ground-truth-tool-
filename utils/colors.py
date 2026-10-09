"""Color management for the Kabaddi GT Track Editor (supports Dark and Light themes)."""
from __future__ import annotations
from PySide6.QtGui import QColor

# ── Track ID colour palette ────────────────────────────────────────────────
_PALETTE = [
    "#FF5733", "#33A0FF", "#FFCC33", "#57D68C",
    "#FF66CC", "#00CCCC", "#B266FF", "#FF9900",
    "#33FFCC", "#FF3366", "#7EC8E3", "#F4A261",
    "#E76F51", "#2A9D8F", "#E9C46A", "#264653",
]

BBOX_ALPHA = 220  # transparency for bbox fill overlays

# ── Theme Palettes ─────────────────────────────────────────────────────────
PALETTES: dict[str, dict[str, str]] = {
    "dark": {
        "BG_BASE":      "#0d1117",
        "BG_SURFACE":   "#161b22",
        "BG_PANEL":     "#21262d",
        "BG_WIDGET":    "#2d333b",
        "ACCENT":       "#388bfd",
        "ACCENT_HOVER": "#1f6feb",
        "ACCENT_ALT":   "#3fb950",
        "WARNING":      "#d29922",
        "DANGER":       "#f85149",
        "TEXT_PRI":     "#c9d1d9",
        "TEXT_SEC":     "#8b949e",
        "BORDER":       "#30363d",
        "BORDER_HL":    "#388bfd",
    },
    "light": {
        "BG_BASE":      "#f6f8fa",
        "BG_SURFACE":   "#ffffff",
        "BG_PANEL":     "#eaeef2",
        "BG_WIDGET":    "#f0f3f6",
        "ACCENT":       "#0969da",
        "ACCENT_HOVER": "#0860ca",
        "ACCENT_ALT":   "#1a7f37",
        "WARNING":      "#9a6700",
        "DANGER":       "#cf222e",
        "TEXT_PRI":     "#1f2328",
        "TEXT_SEC":     "#57606a",
        "BORDER":       "#d0d7de",
        "BORDER_HL":    "#0969da",
    },
}

# ── Status indicator colours ───────────────────────────────────────────────
STATUS_COLORS_BY_THEME: dict[str, dict[str, QColor]] = {
    "dark": {
        "unreviewed": QColor("#8b949e"),   # grey
        "edited":     QColor("#d29922"),   # amber
        "verified":   QColor("#3fb950"),   # green
    },
    "light": {
        "unreviewed": QColor("#57606a"),   # slate grey
        "edited":     QColor("#9a6700"),   # dark amber
        "verified":   QColor("#1a7f37"),   # dark green
    },
}

# ── Timeline marker colours ────────────────────────────────────────────────
TIMELINE_COLORS_BY_THEME: dict[str, dict[str, QColor]] = {
    "dark": {
        "switch":   QColor(248, 81,  73,  200),
        "edited":   QColor(210, 153, 34,  200),
        "verified": QColor(63,  185, 80,  200),
        "current":  QColor(255, 255, 255, 255),
        "default":  QColor(60,  60,  80,  200),
    },
    "light": {
        "switch":   QColor(207, 34,  46,  220),
        "edited":   QColor(154, 103, 0,   220),
        "verified": QColor(26,  127, 55,  220),
        "current":  QColor(31,  35,  40,  255),
        "default":  QColor(208, 215, 222, 200),
    },
}


def get_theme_colors(theme: str = "dark") -> dict[str, str]:
    """Return dictionary of hex color strings for given theme ('dark' or 'light')."""
    return PALETTES.get(theme, PALETTES["dark"])


def get_status_color(status: str, theme: str = "dark") -> QColor:
    """Return status QColor for given theme."""
    cmap = STATUS_COLORS_BY_THEME.get(theme, STATUS_COLORS_BY_THEME["dark"])
    return cmap.get(status, cmap["unreviewed"])


def get_timeline_colors(theme: str = "dark") -> dict[str, QColor]:
    """Return timeline QColors dictionary for given theme."""
    return TIMELINE_COLORS_BY_THEME.get(theme, TIMELINE_COLORS_BY_THEME["dark"])


def track_color(track_id: int) -> QColor:
    """Return a stable, vibrant QColor for a given track ID."""
    return QColor(_PALETTE[abs(track_id) % len(_PALETTE)])


def bbox_border_color(track_id: int, status: str, theme: str = "dark") -> QColor:
    """Bbox outline colour: status overrides track colour when verified/edited."""
    palette = get_theme_colors(theme)
    if status == "verified":
        return QColor(palette["ACCENT_ALT"])
    if status == "edited":
        return QColor(palette["WARNING"])
    return track_color(track_id)


def label_bg_color(track_id: int, status: str, theme: str = "dark") -> QColor:
    """Label background colour (slightly dimmed version of border colour)."""
    c = bbox_border_color(track_id, status, theme)
    c.setAlpha(200)
    return c


# ── Application stylesheet generator ────────────────────────────────────────
def get_app_stylesheet(theme: str = "dark") -> str:
    """Generate dynamic QSS stylesheet for given theme ('dark' or 'light')."""
    p = get_theme_colors(theme)

    is_light = (theme == "light")
    btn_theme_bg = "#ffffff" if is_light else "#21262d"
    btn_theme_border = "#d0d7de" if is_light else "#30363d"
    btn_theme_hover = "#eaeef2" if is_light else "#30363d"
    item_hover_bg = "#f3f4f6" if is_light else p["BG_PANEL"]

    return f"""
QMainWindow, QDialog, QWidget {{
    background-color: {p["BG_BASE"]};
    color: {p["TEXT_PRI"]};
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 12px;
}}
QMenuBar {{
    background-color: {p["BG_SURFACE"]};
    color: {p["TEXT_PRI"]};
    border-bottom: 1px solid {p["BORDER"]};
}}
QMenuBar::item {{
    background: transparent;
    padding: 4px 8px;
}}
QMenuBar::item:selected {{
    background-color: {p["BG_PANEL"]};
    border-radius: 4px;
}}
QMenu {{
    background-color: {p["BG_SURFACE"]};
    color: {p["TEXT_PRI"]};
    border: 1px solid {p["BORDER"]};
    padding: 4px;
}}
QMenu::item {{
    padding: 5px 22px 5px 12px;
    border-radius: 3px;
}}
QMenu::item:selected {{
    background-color: {p["ACCENT"]};
    color: white;
}}
QMenu::separator {{
    height: 1px;
    background: {p["BORDER"]};
    margin: 4px 0;
}}
QSplitter::handle {{
    background-color: {p["BORDER"]};
    width: 2px;
    height: 2px;
}}
QPushButton {{
    background-color: {p["BG_WIDGET"]};
    color: {p["TEXT_PRI"]};
    border: 1px solid {p["BORDER"]};
    border-radius: 5px;
    padding: 5px 14px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {p["BG_PANEL"]};
    border-color: {p["BORDER_HL"]};
}}
QPushButton:pressed {{
    background-color: {p["ACCENT"]};
    color: white;
}}
QPushButton:disabled {{
    color: {p["TEXT_SEC"]};
    border-color: {p["BORDER"]};
}}
QPushButton#btn_primary {{
    background-color: {p["ACCENT"]};
    color: white;
    border-color: {p["ACCENT"]};
    font-weight: 600;
}}
QPushButton#btn_primary:hover {{
    background-color: {p["ACCENT_HOVER"]};
}}
QPushButton#btn_danger {{
    background-color: {p["BG_WIDGET"]};
    color: {p["DANGER"]};
    border-color: {p["DANGER"]};
}}
QPushButton#btn_danger:hover {{
    background-color: {p["DANGER"]};
    color: white;
}}
QPushButton#btn_success {{
    background-color: {p["BG_WIDGET"]};
    color: {p["ACCENT_ALT"]};
    border-color: {p["ACCENT_ALT"]};
}}
QPushButton#btn_success:hover {{
    background-color: {p["ACCENT_ALT"]};
    color: white;
}}
QPushButton#btn_theme_toggle {{
    background-color: {btn_theme_bg};
    color: {p["TEXT_PRI"]};
    border: 1px solid {btn_theme_border};
    border-radius: 5px;
    padding: 3px 10px;
    font-weight: 600;
    font-size: 11px;
}}
QPushButton#btn_theme_toggle:hover {{
    background-color: {btn_theme_hover};
    border-color: {p["ACCENT"]};
}}
QLabel {{
    color: {p["TEXT_PRI"]};
}}
QLabel#label_secondary {{
    color: {p["TEXT_SEC"]};
    font-size: 11px;
}}
QLabel#label_stat_value {{
    color: {p["ACCENT"]};
    font-size: 14px;
    font-weight: bold;
}}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {p["BG_WIDGET"]};
    color: {p["TEXT_PRI"]};
    border: 1px solid {p["BORDER"]};
    border-radius: 4px;
    padding: 3px 6px;
    selection-background-color: {p["ACCENT"]};
    selection-color: white;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border-color: {p["BORDER_HL"]};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background-color: {p["BG_PANEL"]};
    border: none;
    width: 16px;
}}
QComboBox::drop-down {{
    background-color: {p["BG_PANEL"]};
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: {p["BG_SURFACE"]};
    color: {p["TEXT_PRI"]};
    border: 1px solid {p["BORDER"]};
    selection-background-color: {p["ACCENT"]};
    selection-color: white;
}}
QGroupBox {{
    border: 1px solid {p["BORDER"]};
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 8px;
    font-weight: 600;
    color: {p["TEXT_SEC"]};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}}
QScrollBar:vertical {{
    background: {p["BG_SURFACE"]};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {p["BG_WIDGET"]};
    border: 1px solid {p["BORDER"]};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{
    background: {p["TEXT_SEC"]};
}}
QScrollBar:horizontal {{
    background: {p["BG_SURFACE"]};
    height: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: {p["BG_WIDGET"]};
    border: 1px solid {p["BORDER"]};
    border-radius: 4px;
    min-width: 20px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {p["TEXT_SEC"]};
}}
QListWidget {{
    background-color: {p["BG_SURFACE"]};
    color: {p["TEXT_PRI"]};
    border: 1px solid {p["BORDER"]};
    border-radius: 4px;
}}
QListWidget::item {{
    padding: 4px 6px;
    border-bottom: 1px solid {p["BG_WIDGET"]};
}}
QListWidget::item:selected {{
    background-color: {p["ACCENT"]};
    color: white;
}}
QListWidget::item:hover {{
    background-color: {item_hover_bg};
}}
QStatusBar {{
    background-color: {p["BG_SURFACE"]};
    border-top: 1px solid {p["BORDER"]};
    color: {p["TEXT_SEC"]};
    font-size: 11px;
}}
QToolTip {{
    background-color: {p["BG_PANEL"]};
    color: {p["TEXT_PRI"]};
    border: 1px solid {p["BORDER"]};
    padding: 4px;
    border-radius: 3px;
}}
QRadioButton {{
    color: {p["TEXT_PRI"]};
    spacing: 6px;
}}
QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border-radius: 7px;
    border: 2px solid {p["BORDER"]};
    background: {p["BG_WIDGET"]};
}}
QRadioButton::indicator:checked {{
    background: {p["ACCENT"]};
    border-color: {p["ACCENT"]};
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: {p["BG_WIDGET"]};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {p["ACCENT"]};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{
    background: {p["ACCENT"]};
    border-radius: 2px;
}}
QSplitter::handle:horizontal {{
    background-color: {p["BORDER"]};
    width: 3px;
}}
QSplitter::handle:vertical {{
    background-color: {p["BORDER"]};
    height: 3px;
}}
QFrame[frameShape="4"] {{
    color: {p["BORDER"]};
}}
QFrame[frameShape="5"] {{
    color: {p["BORDER"]};
}}
"""


# ── Backward Compatibility Constants (Dark Default) ────────────────────────
BG_BASE    = PALETTES["dark"]["BG_BASE"]
BG_SURFACE = PALETTES["dark"]["BG_SURFACE"]
BG_PANEL   = PALETTES["dark"]["BG_PANEL"]
BG_WIDGET  = PALETTES["dark"]["BG_WIDGET"]
ACCENT     = PALETTES["dark"]["ACCENT"]
ACCENT_ALT = PALETTES["dark"]["ACCENT_ALT"]
WARNING    = PALETTES["dark"]["WARNING"]
DANGER     = PALETTES["dark"]["DANGER"]
TEXT_PRI   = PALETTES["dark"]["TEXT_PRI"]
TEXT_SEC   = PALETTES["dark"]["TEXT_SEC"]
BORDER     = PALETTES["dark"]["BORDER"]
BORDER_HL  = PALETTES["dark"]["BORDER_HL"]

STATUS_COLORS: dict[str, QColor] = STATUS_COLORS_BY_THEME["dark"]
TIMELINE_COLORS: dict[str, QColor] = TIMELINE_COLORS_BY_THEME["dark"]
APP_STYLESHEET: str = get_app_stylesheet("dark")
