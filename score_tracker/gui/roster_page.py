"""Roster: your five teams of three, plus weekly and capture settings."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..characters import KNOWN_CHARACTERS, best_name
from ..config import DISTANCES, TEAM_SIZE, Settings
from .widgets import card, distance_badge, label

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class RosterPage(QWidget):
    settings_saved = Signal(object)  # Settings
    detect_requested = Signal()  # capture the game and read names from it

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        self._settings: Settings | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(16)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label("Roster", "h1"))
        titles.addWidget(label("Your five teams of three. Names must match the game.", "muted"))
        header.addLayout(titles)
        header.addStretch(1)
        self.detect_btn = QPushButton("Fill from game screen")
        self.detect_btn.setToolTip("Open a race's Score Info in the game, then click this. "
                                   "Do it again after scrolling down to get everyone.")
        self.detect_btn.clicked.connect(self.detect_requested)
        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("primary")
        self.save_btn.clicked.connect(self._save)
        header.addWidget(self.detect_btn)
        header.addWidget(self.save_btn)
        lay.addLayout(header)
        self.status = label("", "muted", wrap=True)
        lay.addWidget(self.status)

        teams_card, teams_lay = card()
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        self.slots: dict[str, list[QLineEdit]] = {}
        for col, d in enumerate(DISTANCES):
            head = QHBoxLayout()
            head.addWidget(distance_badge(d))
            head.addStretch(1)
            grid.addLayout(head, 0, col)
            self.slots[d] = []
            for r in range(TEAM_SIZE):
                edit = QLineEdit()
                edit.setPlaceholderText(f"Racer {r + 1}")
                grid.addWidget(edit, r + 1, col)
                self.slots[d].append(edit)
            grid.setColumnStretch(col, 1)
        teams_lay.addLayout(grid)
        teams_lay.addWidget(label("Not on a team (kept for old matches)", "faint"))
        self.unassigned = QLineEdit()
        self.unassigned.setPlaceholderText("Comma-separated names")
        teams_lay.addWidget(self.unassigned)
        lay.addWidget(teams_card)

        prefs_card, prefs_lay = card()
        prefs_lay.addWidget(label("Weekly goal and capture", "h2"))
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        self.per_week = QSpinBox()
        self.per_week.setRange(1, 200)
        self.reset_day = QComboBox()
        self.reset_day.addItems(WEEKDAYS)
        self.reset_hour = QSpinBox()
        self.reset_hour.setRange(0, 23)
        self.reset_hour.setSuffix(":00 UTC")
        reset = QHBoxLayout()
        reset.addWidget(self.reset_day)
        reset.addWidget(self.reset_hour)
        reset.addStretch(1)
        self.hotkey = QLineEdit()
        self.hotkey.setPlaceholderText("ctrl+alt+s")
        self.process = QLineEdit()
        for field in (self.per_week, self.hotkey, self.process):
            field.setMaximumWidth(260)
        form.addRow("Matches per week", self.per_week)
        form.addRow("Week resets", reset)
        form.addRow("Capture hotkey", self.hotkey)
        form.addRow("Game process", self.process)
        prefs_lay.addLayout(form)
        prefs_lay.addWidget(label("The hotkey works from anywhere and captures the game window, "
                                  "even if it's behind other windows. Changes apply after saving.", "faint"))
        lay.addWidget(prefs_card)
        lay.addStretch(1)

    # ------------------------------------------------------------------

    def load(self, settings: Settings, extra_names=()):
        self._settings = settings
        names = sorted(set(KNOWN_CHARACTERS) | set(settings.roster) | set(extra_names))
        for d in DISTANCES:
            members = settings.team_members(d)
            for i, edit in enumerate(self.slots[d]):
                completer = QCompleter(names, edit)
                completer.setCaseSensitivity(Qt.CaseInsensitive)
                completer.setFilterMode(Qt.MatchContains)
                edit.setCompleter(completer)
                edit.setText(members[i] if i < len(members) else "")
        self.unassigned.setText(", ".join(n for n in settings.roster if n not in settings.teams))
        self.per_week.setValue(settings.matches_per_week)
        self.reset_day.setCurrentIndex(settings.week_reset_weekday)
        self.reset_hour.setValue(settings.week_reset_hour_utc)
        self.hotkey.setText(settings.capture_hotkey)
        self.process.setText(settings.game_process)
        self.status.setText("")

    def apply_detected(self, detected):
        """Fill empty slots with (name, distance) pairs read from a screenshot."""
        known = [e.text().strip() for d in DISTANCES for e in self.slots[d] if e.text().strip()]
        added = 0
        leftovers = []
        for raw, distance in detected:
            name = best_name(raw, extra=known)
            if name in known:
                continue
            target = next((e for e in self.slots.get(distance, []) if not e.text().strip()), None)
            if target is None:
                leftovers.append(name)
                continue
            target.setText(name)
            known.append(name)
            added += 1
        # Placed names leave the "not on a team" list; unplaced ones join it
        placed = {e.text().strip() for d in DISTANCES for e in self.slots[d]}
        current = [n.strip() for n in self.unassigned.text().split(",") if n.strip()]
        self.unassigned.setText(", ".join(n for n in dict.fromkeys(current + leftovers) if n not in placed))
        self.status.setText(
            f"Filled {added} slot(s) from the game screen."
            + (f" Couldn't place: {', '.join(leftovers)}." if leftovers else "")
            + " Check the names, then Save."
        )

    def _save(self):
        if self._settings is None:
            return
        roster, teams = [], {}
        for d in DISTANCES:
            for e in self.slots[d]:
                name = e.text().strip()
                if name:
                    roster.append(name)
                    teams[name] = d
        roster += [n.strip() for n in self.unassigned.text().split(",") if n.strip()]
        dupes = sorted({n for n in roster if roster.count(n) > 1})
        if dupes:
            self.status.setText(f"Each name can only appear once: {', '.join(dupes)}")
            return
        hotkey = self.hotkey.text().strip().lower() or "ctrl+alt+s"
        settings = replace(
            self._settings.with_roster(roster, teams),
            matches_per_week=self.per_week.value(),
            week_reset_weekday=self.reset_day.currentIndex(),
            week_reset_hour_utc=self.reset_hour.value(),
            capture_hotkey=hotkey,
            game_process=self.process.text().strip() or self._settings.game_process,
        )
        self.settings_saved.emit(settings)
        self.status.setText("Saved.")
