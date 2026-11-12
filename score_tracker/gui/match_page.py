"""Current match: team slots, rows that need review, manual fixes."""

from __future__ import annotations

from difflib import SequenceMatcher

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..config import DISTANCES
from . import theme
from .widgets import card, clear_layout, distance_badge, label, pil_to_pixmap


def _score_input(value=None) -> QLineEdit:
    edit = QLineEdit("" if value is None else str(value))
    edit.setPlaceholderText("Score")
    edit.setValidator(QIntValidator(0, 9_999_999))
    edit.setMinimumWidth(60)
    edit.setMaximumWidth(96)
    return edit


class MatchPage(QWidget):
    capture_requested = Signal()
    save_requested = Signal()
    discard_requested = Signal()
    # (name, score, row or None)
    resolve_requested = Signal(str, int, object)
    ignore_row_requested = Signal(object)
    clipboard_toggled = Signal(bool)

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        self.layout_ = QVBoxLayout(body)
        self.layout_.setContentsMargins(28, 24, 28, 24)
        self.layout_.setSpacing(16)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label("Current match", "h1"))
        self.subtitle = label("", "muted")
        titles.addWidget(self.subtitle)
        header.addLayout(titles)
        header.addStretch(1)
        self.discard_btn = QPushButton("Discard")
        self.discard_btn.setObjectName("danger")
        self.save_btn = QPushButton("Save as partial")
        self.capture_btn = QPushButton("Capture game")
        self.capture_btn.setObjectName("primary")
        for b in (self.discard_btn, self.save_btn, self.capture_btn):
            header.addWidget(b)
        self.capture_btn.clicked.connect(self.capture_requested)
        self.save_btn.clicked.connect(self.save_requested)
        self.discard_btn.clicked.connect(self.discard_requested)
        self.layout_.addLayout(header)

        self.hint = label("", "muted", wrap=True)
        self.layout_.addWidget(self.hint)
        self.clipboard_box = QCheckBox("Watch the clipboard for Win+Shift+S snips")
        self.clipboard_box.setChecked(True)
        self.clipboard_box.setToolTip("Any image you copy is read as a Score Info screenshot while this is on")
        self.clipboard_box.toggled.connect(self.clipboard_toggled)
        self.layout_.addWidget(self.clipboard_box)

        self.grid_card, grid_lay = card()
        grid_lay.addWidget(label("Your teams", "h2"))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(8)
        grid_lay.addLayout(self.grid)
        self.layout_.addWidget(self.grid_card)

        self.review_card, review_lay = card()
        review_lay.addWidget(label("Rows to review", "h2"))
        review_lay.addWidget(label("The name on these rows couldn't be read. Check the picture, "
                                   "then pick who it is.", "muted", wrap=True))
        self.review_list = QVBoxLayout()
        self.review_list.setSpacing(8)
        review_lay.addLayout(self.review_list)
        self.layout_.addWidget(self.review_card)

        self.last_card, last_lay = card()
        self.last_title = label("", "h2")
        self.last_detail = label("", "muted", wrap=True)
        last_lay.addWidget(self.last_title)
        last_lay.addWidget(self.last_detail)
        self.layout_.addWidget(self.last_card)
        self.layout_.addStretch(1)

    # ------------------------------------------------------------------

    def refresh(self, settings, acc, busy=False, last_saved=None):
        """Redraw from the session's pending MatchAccumulator."""
        roster = settings.roster
        final = acc.final_scores()
        inferred = {n for n, _, _ in acc.inferred()}
        n_found, n_total = len(final), len(roster)
        hotkey = settings.capture_hotkey.upper()

        self.capture_btn.setEnabled(not busy)
        self.capture_btn.setText("Reading…" if busy else "Capture game")
        self.save_btn.setEnabled(bool(final))
        self.discard_btn.setEnabled(bool(final) or bool(acc.unnamed))

        if not roster:
            self.subtitle.setText("Set up your teams on the Roster page first")
        elif not settings.teams and not (final or acc.unnamed):
            self.subtitle.setText("Tip: assign your racers to their teams on the Roster page")
        elif final or acc.unnamed:
            self.subtitle.setText(f"{n_found} of {n_total} characters found")
        else:
            self.subtitle.setText("Waiting for the first screenshot")
        snips = " Win+Shift+S snips work too." if self.clipboard_box.isChecked() else ""
        self.hint.setText(
            f"In the game, open a race's Score Info and press {hotkey} (or Capture game). "
            f"Then drag the list to the bottom and press {hotkey} again.{snips} "
            "The match saves itself once all characters are found. Closing the app saves an "
            "unfinished match as partial."
        )

        in_progress = bool(final) or bool(acc.unnamed)
        # --- team grid ---
        clear_layout(self.grid)
        columns = [d for d in DISTANCES]
        if any(n not in settings.teams for n in roster):
            columns.append("")
        for col, distance in enumerate(columns):
            members = [n for n in roster if settings.teams.get(n, "") == distance]
            head = QHBoxLayout()
            head.addWidget(distance_badge(distance))
            head.addStretch(1)
            self.grid.addLayout(head, 0, col)
            for r, name in enumerate(members, start=1):
                self.grid.addWidget(self._slot(name, final.get(name), name in inferred, in_progress), r, col)
            if not members:
                self.grid.addWidget(label("No one assigned", "faint"), 1, col)
        for col in range(len(columns)):
            self.grid.setColumnStretch(col, 1)
        self.grid_card.setVisible(bool(roster))

        # --- review rows ---
        clear_layout(self.review_list)
        missing = acc.missing
        rows = acc.needs_review
        for row in rows:
            self.review_list.addWidget(self._review_row(row, missing, settings))
        self.review_card.setVisible(bool(rows))

        # --- last saved ---
        if last_saved is not None:
            total = sum(last_saved.scores.values())
            kind = "Match saved" if last_saved.complete else "Partial match saved"
            self.last_title.setText(kind)
            text = f"{len(last_saved.scores)} characters · total {total:,}"
            if last_saved.inferred:
                names = ", ".join(n for n, _ in last_saved.inferred)
                text += f" · matched by elimination: {names}"
            self.last_detail.setText(text)
        self.last_card.setVisible(last_saved is not None)

    def _slot(self, name, score, inferred, in_progress=True) -> QFrame:
        frame = QFrame()
        frame.setObjectName("slotMissing" if score is None and in_progress else "slot")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(2)
        lay.addWidget(label(name))
        if score is not None:
            text = f"{score:,}" + ("  · by elimination" if inferred else "")
            lay.addWidget(label(text, "muted"))
            return frame
        if not in_progress:
            lay.addWidget(label("—", "faint"))
            return frame
        line = QHBoxLayout()
        line.setSpacing(6)
        edit = _score_input()
        ok = QPushButton("Add")
        ok.setStyleSheet("padding: 6px 10px;")

        def submit():
            if edit.text():
                self.resolve_requested.emit(name, int(edit.text()), None)

        ok.clicked.connect(submit)
        edit.returnPressed.connect(submit)
        line.addWidget(edit)
        line.addWidget(ok)
        line.addStretch(1)
        lay.addLayout(line)
        return frame

    def _review_row(self, row, missing, settings) -> QFrame:
        frame = QFrame()
        frame.setObjectName("reviewRow")
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(10)

        picture = QLabel()
        if row.crop is not None:
            pix = pil_to_pixmap(row.crop)
            picture.setPixmap(pix.scaled(300, 46, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        picture.setStyleSheet(f"border-radius: 6px; background: {theme.BG};")
        lay.addWidget(picture, 1)

        info = QVBoxLayout()
        info.setSpacing(4)
        info.addWidget(distance_badge(row.distance))
        if row.read_text:
            info.addWidget(label(f"Read as “{row.read_text}”", "faint"))
        lay.addLayout(info)

        who = QComboBox()
        # Same team first, then the closest match to what OCR read
        def rank(name):
            same_team = bool(row.distance) and settings.teams.get(name) == row.distance
            similarity = SequenceMatcher(None, (row.read_text or "").lower(), name.lower()).ratio()
            return (not same_team, -similarity)

        who.addItems(sorted(missing, key=rank))
        who.setMinimumWidth(160)
        score = _score_input(row.score)
        assign = QPushButton("Assign")
        assign.setObjectName("primary")
        ignore = QPushButton("✕")
        ignore.setObjectName("iconButton")
        ignore.setToolTip("Not a character row: ignore it")

        def submit():
            if who.currentText() and score.text():
                self.resolve_requested.emit(who.currentText(), int(score.text()), row)

        assign.clicked.connect(submit)
        score.returnPressed.connect(submit)
        ignore.clicked.connect(lambda: self.ignore_row_requested.emit(row))
        assign.setEnabled(bool(missing))
        for w in (who, score, assign, ignore):
            lay.addWidget(w)
        return frame
