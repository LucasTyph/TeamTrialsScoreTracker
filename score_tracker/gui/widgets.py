"""Small reusable widgets."""

from __future__ import annotations

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

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
