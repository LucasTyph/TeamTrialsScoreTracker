"""Small reusable widgets."""

from __future__ import annotations

from PIL import Image
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import theme


def label(text="", name=None, wrap=False) -> QLabel:
    w = QLabel(text)
    if name:
        w.setObjectName(name)
    w.setWordWrap(wrap)
    return w


def card(margins=(18, 16, 18, 16), spacing=10) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return frame, layout


def distance_badge(distance) -> QLabel:
    text = distance or "No team"
    color = theme.distance_color(distance)
    badge = label(text, "badge")
    badge.setStyleSheet(f"background: {theme.rgba(color, 0.18)}; color: {color};")
    badge.setAlignment(Qt.AlignCenter)
    badge.setFixedHeight(20)
    return badge


class StatTile(QFrame):
    """Big number with a caption, inside a card."""

    def __init__(self, caption):
        super().__init__()
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(2)
        self.caption = label(caption, "statLabel")
        self.value = label("—", "statValue")
        self.detail = label("", "faint", wrap=True)
        lay.addWidget(self.caption)
        lay.addWidget(self.value)
        lay.addWidget(self.detail)

    def set(self, value, detail="", color=None):
        self.value.setText(value)
        self.value.setStyleSheet(f"color: {color};" if color else "")
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))


def pil_to_pixmap(img: Image.Image) -> QPixmap:
    img = img.convert("RGB")
    data = img.tobytes("raw", "RGB")
    qimg = QImage(data, img.width, img.height, img.width * 3, QImage.Format_RGB888)
    return QPixmap.fromImage(qimg.copy())


def qimage_to_pil(qimg: QImage) -> Image.Image:
    qimg = qimg.convertToFormat(QImage.Format_RGB888)
    width, height, bpl = qimg.width(), qimg.height(), qimg.bytesPerLine()
    buf = bytes(qimg.constBits())[: bpl * height]
    img = Image.frombuffer("RGB", (width, height), buf, "raw", "RGB", bpl, 1)
    return img.copy()


def hline() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {theme.BORDER};")
    return line


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())


def row(*widgets, spacing=8, stretch_last=False) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(spacing)
    for x in widgets:
        if x is None:
            lay.addStretch(1)
        else:
            lay.addWidget(x)
    if stretch_last:
        lay.addStretch(1)
    return w


class SortItem(QTableWidgetItem):
    """Table item that sorts by a value instead of its text."""

    def __init__(self, text, key=None, align=Qt.AlignRight | Qt.AlignVCenter):
        super().__init__(text)
        self.key = key
        self.setTextAlignment(align)

    def __lt__(self, other):
        a, b = self.key, getattr(other, "key", None)
        if a is None or b is None:
            # Missing values sort last in ascending order
            return a is not None and b is None
        return a < b


class Toast(QFrame):
    """A message banner that slides in at the bottom right of a window."""

    KINDS = {"info": theme.ACCENT, "success": theme.SUCCESS, "warning": theme.WARNING, "error": theme.DANGER}

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 10, 0)
        lay.setSpacing(12)
        self.stripe = QFrame()
        self.stripe.setFixedWidth(4)
        lay.addWidget(self.stripe)
        text = QVBoxLayout()
        text.setContentsMargins(0, 10, 0, 10)
        text.setSpacing(2)
        self.title = label("", "toastTitle")
        self.message = label("", "muted", wrap=True)
        text.addWidget(self.title)
        text.addWidget(self.message)
        lay.addLayout(text, 1)
        close = QPushButton("✕")
        close.setObjectName("iconButton")
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.hide)
        lay.addWidget(close, 0, Qt.AlignTop)
        self.setFixedWidth(360)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)
        self.hide()

    def show_message(self, title, message="", kind="info", msecs=5000):
        color = self.KINDS.get(kind, theme.ACCENT)
        self.stripe.setStyleSheet(f"background: {color}; border-top-left-radius: 10px;"
                                  "border-bottom-left-radius: 10px;")
        self.title.setText(title)
        self.message.setText(message)
        self.message.setVisible(bool(message))
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self.timer.start(msecs)

    def reposition(self):
        parent = self.parentWidget()
        if parent is not None:
            self.adjustSize()
            self.move(parent.width() - self.width() - 20, parent.height() - self.height() - 20)
