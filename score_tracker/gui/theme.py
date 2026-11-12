"""Colours and the application stylesheet."""

BG = "#14161b"
SURFACE = "#1c1f26"
SURFACE_2 = "#242833"
SURFACE_3 = "#2c3140"
BORDER = "#2f3442"
TEXT = "#e8eaf0"
MUTED = "#9aa3b2"
FAINT = "#6b7385"
ACCENT = "#7c9cff"
ACCENT_HOVER = "#93adff"
SUCCESS = "#4cc38a"
WARNING = "#f2b84b"
DANGER = "#ef6461"

DISTANCE_COLORS = {
    "Sprint": "#ff8a5b",
    "Mile": "#4fb3ff",
    "Medium": "#5fd39a",
    "Long": "#b48cff",
    "Dirt": "#d6a25e",
    "": FAINT,
}


def distance_color(distance) -> str:
    return DISTANCE_COLORS.get(distance or "", FAINT)


def rgba(hex_color, alpha) -> str:
    """CSS rgba() for a #rrggbb colour (Qt reads #rrggbbaa as #aarrggbb)."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"


STYLESHEET = f"""
* {{
    font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif;
    font-size: 10pt;
    color: {TEXT};
}}
QMainWindow, QWidget#page, QScrollArea, QScrollArea > QWidget > QWidget {{
    background: {BG};
}}
QWidget#sidebar {{
    background: {SURFACE};
    border-right: 1px solid {BORDER};
}}
QLabel#appTitle {{ font-size: 13pt; font-weight: 600; }}
QLabel#appSubtitle {{ color: {MUTED}; font-size: 9pt; }}
QPushButton#navButton {{
    text-align: left;
    padding: 9px 14px;
    border: none;
    border-radius: 8px;
    background: transparent;
    color: {MUTED};
    font-size: 10.5pt;
}}
QPushButton#navButton:hover {{ background: {SURFACE_2}; color: {TEXT}; }}
QPushButton#navButton:checked {{ background: {SURFACE_3}; color: {TEXT}; font-weight: 600; }}

QLabel#h1 {{ font-size: 18pt; font-weight: 600; }}
QLabel#h2 {{ font-size: 12.5pt; font-weight: 600; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#faint {{ color: {FAINT}; font-size: 9pt; }}
QLabel#statValue {{ font-size: 20pt; font-weight: 600; }}
QLabel#statLabel {{ color: {MUTED}; font-size: 9pt; }}
QLabel#badge {{
    border-radius: 9px; padding: 2px 9px; font-size: 8.5pt; font-weight: 600;
}}

QFrame#card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QFrame#slot {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QFrame#slotMissing {{
    background: rgba(242, 184, 75, 0.10);
    border: 1px dashed {WARNING};
    border-radius: 8px;
}}
QFrame#reviewRow {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}

QPushButton {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 7px 14px;
}}
QPushButton:hover {{ background: {SURFACE_3}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: {FAINT}; }}
QPushButton#primary {{
    background: {ACCENT}; border: none; color: #0f1320; font-weight: 600;
}}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#danger {{ color: {DANGER}; }}
QPushButton#iconButton {{ padding: 4px 8px; background: transparent; border: none; color: {MUTED}; }}
QPushButton#iconButton:hover {{ color: {DANGER}; }}

QLineEdit, QSpinBox, QComboBox {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 6px 9px;
    selection-background-color: {ACCENT};
    selection-color: #0f1320;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView, QListView {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    selection-background-color: {SURFACE_3};
    outline: none;
}}

QTableWidget {{
    background: {SURFACE};
    border: none;
    gridline-color: transparent;
    alternate-background-color: {SURFACE_2};
    selection-background-color: {SURFACE_3};
}}
QTableWidget::item {{ padding: 4px 8px; }}
QHeaderView::section {{
    background: {SURFACE};
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px 8px;
    font-size: 9pt;
}}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {SURFACE_3}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {SURFACE_3}; border-radius: 4px; min-width: 30px; }}
QFrame#toast {{
    background: {SURFACE_3};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QLabel#toastTitle {{ font-weight: 600; }}
QLabel#chip {{
    border-radius: 9px; padding: 2px 9px; font-size: 8.5pt; font-weight: 600;
    background: {SURFACE_3}; color: {MUTED};
}}
QLabel#bigValue {{ font-size: 17pt; font-weight: 600; }}
QFrame#teamCard {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QCheckBox {{ spacing: 8px; color: {MUTED}; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid {BORDER}; background: {BG};
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QTableWidget::item:selected {{ background: {SURFACE_3}; }}
QTableWidget#compactTable {{ font-size: 9pt; }}
QTableWidget#compactTable::item {{ padding: 4px 3px; }}
QTableWidget#compactTable QHeaderView::section {{ padding: 4px 3px; font-size: 8.5pt; }}
QHeaderView::section:hover {{ color: {TEXT}; }}
QToolTip {{ background: {SURFACE_3}; color: {TEXT}; border: 1px solid {BORDER}; padding: 5px; }}
QMenu {{ background: {SURFACE_2}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 5px; }}
QMenu::item:selected {{ background: {SURFACE_3}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}
"""
