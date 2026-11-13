"""Entry point: show a splash screen right away, then load the app.

Importing the app (pandas, OCR) takes a couple of seconds, so only Qt is
imported before the splash screen is up.
"""

from __future__ import annotations

import sys
from pathlib import Path

ICON = Path(__file__).resolve().parent / "assets" / "icon.png"


def main() -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
    from PySide6.QtWidgets import QApplication, QSplashScreen

    app = QApplication.instance() or QApplication(sys.argv)
    canvas = QPixmap(360, 160)
    canvas.fill(QColor("#16181d"))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing)
    icon = QPixmap(str(ICON))
    if not icon.isNull():
        painter.drawPixmap(28, 44, icon.scaledToHeight(72, Qt.SmoothTransformation))
    font = QFont()
    font.setPointSize(15)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#e8eaf0"))
    painter.drawText(118, 76, "Score Tracker")
    font.setPointSize(9)
    font.setBold(False)
    painter.setFont(font)
    painter.setPen(QColor("#8b91a1"))
    painter.drawText(118, 100, "Team Trials · loading…")
    painter.end()
    splash = QSplashScreen(canvas)
    splash.show()
    app.processEvents()

    from .gui.app import run

    return run(splash)


if __name__ == "__main__":
    sys.exit(main())
