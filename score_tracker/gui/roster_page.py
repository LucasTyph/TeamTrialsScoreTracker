"""Roster: lineups (named versions of your five teams), each racer's rating and
aptitudes, plus capture settings."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..characters import KNOWN_CHARACTERS, best_name
from ..config import DISTANCES, TEAM_SIZE, Settings
from ..lineups import DEFAULT_GRADE, GRADES, STYLES, Build, Lineup, Roster
from ..ratings import effective_rating, lineup_rating
from . import theme
from .widgets import card, distance_badge, label

# The user never runs anything below A, so S and A come first
GRADE_CHOICES = ("S", "A") + tuple(g for g in GRADES if g not in ("S", "A"))


def _surface(distance) -> str:
    return "Dirt" if distance == "Dirt" else "Turf"


def _race_distance(distance) -> str:
    return "Mile" if distance == "Dirt" else distance


def _k(value) -> str:
    return "—" if value is None else f"{value / 1000:.1f}k"


def _grade_box(tip) -> QComboBox:
    box = QComboBox()
    box.addItems(GRADE_CHOICES)
    box.setToolTip(tip)
    box.setFixedWidth(58)
    return box


class _Slot:
    """The widgets of one team slot and the build they edit."""

    def __init__(self, page: "RosterPage", distance: str, index: int):
        self.page, self.distance, self.index = page, distance, index
        self.build_id: str | None = None
        self.new_version = False
        self.name = QLineEdit()
        self.name.setPlaceholderText(f"Racer {index + 1}")
        self.name.setMinimumWidth(150)
        self.version = label("", "faint")
        self.version.setMinimumWidth(56)
        self.rating = QLineEdit()
        self.rating.setPlaceholderText("Rating")
        self.rating.setValidator(QIntValidator(0, 999_999))
        self.rating.setFixedWidth(76)
        self.rating.setToolTip("Base rating, before S aptitude boosts (optional)")
        self.surface = _grade_box(f"{_surface(distance)} aptitude")
        self.dist = _grade_box(f"{_race_distance(distance)} aptitude")
        self.style = QComboBox()
        self.style.addItems(("", *STYLES))
        self.style.setToolTip("Racing style they run")
        self.style.setFixedWidth(76)
        self.style_grade = _grade_box("Aptitude for that racing style")
        self.effective = label("—", "muted")
        self.effective.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.effective.setMinimumWidth(56)
        self.new_btn = QPushButton("New version")
        self.new_btn.setObjectName("iconButton")
        self.new_btn.setToolTip("A re-trained copy of this racer: a new rating or aptitudes. "
                                "Past matches keep the old version.")
        self.new_btn.clicked.connect(self._new_version)
        self.name.editingFinished.connect(self._name_changed)
        for w in (self.rating,):
            w.textChanged.connect(self._changed)
        for box in (self.surface, self.dist, self.style, self.style_grade):
            box.currentIndexChanged.connect(self._changed)
        self.name.textChanged.connect(lambda _: page.mark_dirty())

    # --- state ---------------------------------------------------------------

    def widgets(self):
        return (self.name, self.version, self.rating, self.surface, self.dist, self.style,
                self.style_grade, self.effective, self.new_btn)

    def show_build(self, build: Build | None, new_version=False):
        self.build_id = build.id if build else None
        self.new_version = new_version
        page = self.page
        page.loading += 1
        try:
            if build is not None:
                self.name.setText(build.character)
            self.rating.setText("" if build is None or build.rating is None else str(build.rating))
            self.surface.setCurrentText(build.surface_grade if build else DEFAULT_GRADE)
            self.dist.setCurrentText(build.distance_grade if build else DEFAULT_GRADE)
            self.style.setCurrentText(build.style if build else "")
            self.style_grade.setCurrentText(build.style_grade if build else DEFAULT_GRADE)
        finally:
            page.loading -= 1
        self._update_version()
        self.update_effective()

    def _update_version(self):
        roster = self.page.roster
        build = roster.builds.get(self.build_id) if roster and self.build_id else None
        if not self.name.text().strip():
            self.version.setText("")
        elif self.new_version:
            n = len(roster.builds_of(self.name.text().strip())) + 1 if roster else 2
            self.version.setText(f"v{n} (new)")
            self.version.setStyleSheet(f"color: {theme.ACCENT};")
        else:
            self.version.setText(build.label if build else "new")
            self.version.setStyleSheet("")
        self.new_btn.setEnabled(bool(self.name.text().strip()))

    def stats(self) -> dict:
        text = self.rating.text().strip()
        return {
            "rating": int(text) if text else None,
            "surface_grade": self.surface.currentText(),
            "distance_grade": self.dist.currentText(),
            "style": self.style.currentText(),
            "style_grade": self.style_grade.currentText(),
        }

    def preview_build(self) -> Build | None:
        name = self.name.text().strip()
        return Build(id="preview", character=name, **self.stats()) if name else None

    def update_effective(self):
        b = self.preview_build()
        eff = effective_rating(b, self.page.s_bonus) if b else None
        text = _k(eff)
        tip = "Effective rating: the rating with +{:.0%} per S aptitude".format(self.page.s_bonus)
        if b is not None and b.below_a:
            text += "*"
            tip += "\nGrades below A are stored but treated as A (not modelled)"
        self.effective.setText(text)
        self.effective.setToolTip(tip)

    # --- events --------------------------------------------------------------

    def _changed(self, *_):
        if self.page.loading:
            return
        self.update_effective()
        self.page.mark_dirty()
        self.page.update_totals()

    def _name_changed(self):
        roster = self.page.roster
        name = self.name.text().strip()
        current = roster.builds.get(self.build_id) if roster and self.build_id else None
        if current is not None and current.character == name:
            return
        self.show_build(roster.latest_build(name) if roster and name else None)
        if not name:
            self.build_id = None
        self.page.mark_dirty()
        self.page.update_totals()

    def _new_version(self):
        if not self.name.text().strip():
            return
        self.new_version = True
        self._update_version()
        self.page.mark_dirty()
        self.rating.setFocus()
        self.rating.selectAll()


class RosterPage(QWidget):
    saved = Signal(object, object)  # (Settings, Roster)
    detect_requested = Signal()  # capture the game and read names from it

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        self._settings: Settings | None = None
        self.roster: Roster | None = None
        self.match_counts: dict = {}
        self.viewed: str = ""
        self.loading = 0
        self.dirty = False
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
        titles.addWidget(label("Your lineups: five teams of three, with each racer's rating and aptitudes. "
                               "Names must match the game.", "muted", wrap=True))
        header.addLayout(titles, 1)
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

        # Lineup bar
        bar_card, bar_lay = card()
        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(label("Lineup", "h2"))
        self.lineup_box = QComboBox()
        self.lineup_box.setMinimumWidth(240)
        self.lineup_box.activated.connect(self._lineup_picked)
        bar.addWidget(self.lineup_box)
        self.new_lineup_btn = QPushButton("New lineup")
        self.new_lineup_btn.setToolTip("Save what's on this page as a new lineup (a copy) and make it active")
        self.new_lineup_btn.clicked.connect(self._new_lineup)
        self.rename_btn = QPushButton("Rename")
        self.rename_btn.clicked.connect(self._rename)
        self.activate_btn = QPushButton("Set active")
        self.activate_btn.setToolTip("Matches you capture are saved to the active lineup")
        self.activate_btn.clicked.connect(self._activate)
        for b in (self.new_lineup_btn, self.rename_btn, self.activate_btn):
            bar.addWidget(b)
        bar.addStretch(1)
        bar_lay.addLayout(bar)
        rating_row = QHBoxLayout()
        rating_row.addWidget(label("Displayed team rating", "muted"))
        self.displayed = QLineEdit()
        self.displayed.setPlaceholderText("optional, e.g. 330000")
        self.displayed.setValidator(QIntValidator(0, 99_999_999))
        self.displayed.setFixedWidth(150)
        self.displayed.setToolTip("The team rating the game shows. Used for the rating bonus when entered; "
                                  "otherwise the sum of effective ratings is used.")
        self.displayed.textChanged.connect(lambda _: (self.mark_dirty(), self.update_totals()))
        rating_row.addWidget(self.displayed)
        self.totals = label("", "faint", wrap=True)
        rating_row.addWidget(self.totals, 1)
        bar_lay.addLayout(rating_row)
        lay.addWidget(bar_card)

        # Teams
        teams_card, teams_lay = card()
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        heads = ["Character", "Version", "Rating", "Surface", "Distance", "Style", "Grade", "Effective", ""]
        for col, h in enumerate(heads):
            grid.addWidget(label(h, "statLabel"), 0, col)
        self.slots: dict[str, list[_Slot]] = {}
        self.team_labels: dict[str, object] = {}
        row = 1
        for d in DISTANCES:
            head = QHBoxLayout()
            head.addWidget(distance_badge(d))
            head.addWidget(label(f"{_surface(d)} · {_race_distance(d)}", "faint"))
            head.addStretch(1)
            team_eff = label("", "muted")
            self.team_labels[d] = team_eff
            head.addWidget(team_eff)
            grid.addLayout(head, row, 0, 1, len(heads))
            row += 1
            self.slots[d] = []
            for i in range(TEAM_SIZE):
                slot = _Slot(self, d, i)
                for col, w in enumerate(slot.widgets()):
                    grid.addWidget(w, row, col)
                self.slots[d].append(slot)
                row += 1
        grid.setColumnStretch(0, 1)
        teams_lay.addLayout(grid)
        teams_lay.addWidget(label(
            "Ratings are optional: racers without one count as the lineup's average. Each S aptitude "
            "instead of A adds 2% to the rating. To record a re-trained racer, use New version "
            "rather than editing their rating, so old matches keep the old one.", "faint", wrap=True))
        teams_lay.addWidget(label("Not on a team (kept for old matches)", "faint"))
        self.unassigned = QLineEdit()
        self.unassigned.setPlaceholderText("Comma-separated names")
        teams_lay.addWidget(self.unassigned)
        lay.addWidget(teams_card)

        prefs_card, prefs_lay = card()
        prefs_lay.addWidget(label("Capture", "h2"))
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        self.hotkey = QLineEdit()
        self.hotkey.setPlaceholderText("ctrl+alt+s")
        self.process = QLineEdit()
        for field in (self.hotkey, self.process):
            field.setFixedWidth(280)
        form.addRow("Capture hotkey", self.hotkey)
        form.addRow("Game process", self.process)
        prefs_lay.addLayout(form)
        prefs_lay.addWidget(label("The hotkey works from anywhere and captures the game window, "
                                  "even if it's behind other windows. Changes apply after saving.", "faint",
                                  wrap=True))
        prefs_card.setMaximumWidth(560)
        prefs_row = QHBoxLayout()
        prefs_row.addWidget(prefs_card, 1)
        prefs_row.addStretch(1)
        lay.addLayout(prefs_row)
        lay.addStretch(1)

    @property
    def s_bonus(self) -> float:
        return self._settings.s_aptitude_bonus if self._settings else 0.02

    def mark_dirty(self):
        if not self.loading:
            self.dirty = True

    # ------------------------------------------------------------------

    def load(self, settings: Settings, roster: Roster, extra_names=(), match_counts=None, viewed=None):
        self._settings = settings
        self.roster = roster.copy()
        self.match_counts = dict(match_counts or {})
        names = sorted(set(KNOWN_CHARACTERS) | set(settings.roster) | set(extra_names)
                       | {b.character for b in roster.builds.values()})
        for d in DISTANCES:
            for slot in self.slots[d]:
                completer = QCompleter(names, slot.name)
                completer.setCaseSensitivity(Qt.CaseInsensitive)
                completer.setFilterMode(Qt.MatchContains)
                slot.name.setCompleter(completer)
        keep = viewed or (self.viewed if self.roster.lineup(self.viewed) else None)
        self.viewed = keep or (self.roster.active_lineup.id if self.roster.active_lineup else "")
        self.unassigned.setText(", ".join(n for n in settings.roster if n not in settings.teams))
        self.hotkey.setText(settings.capture_hotkey)
        self.process.setText(settings.game_process)
        self.status.setText("")
        self._show_lineup()

    def _fill_lineup_box(self):
        self.lineup_box.blockSignals(True)
        self.lineup_box.clear()
        for l in self.roster.lineups:
            n = self.match_counts.get(l.id, 0)
            tags = [f"{n} match{'es' if n != 1 else ''}"]
            if l.id == self.roster.active:
                tags.insert(0, "active")
            self.lineup_box.addItem(f"{l.name}  ·  {' · '.join(tags)}", l.id)
        i = self.lineup_box.findData(self.viewed)
        self.lineup_box.setCurrentIndex(max(i, 0))
        self.lineup_box.blockSignals(False)

    def _show_lineup(self):
        self._fill_lineup_box()
        lineup = self.roster.lineup(self.viewed)
        self.loading += 1
        try:
            for d in DISTANCES:
                ids = lineup.slots.get(d, []) if lineup else []
                for i, slot in enumerate(self.slots[d]):
                    build = self.roster.builds.get(ids[i]) if i < len(ids) else None
                    if build is None:
                        slot.name.setText("")
                    slot.show_build(build)
            self.displayed.setText(str(lineup.displayed_rating) if lineup and lineup.displayed_rating else "")
        finally:
            self.loading -= 1
        is_active = lineup is not None and lineup.id == self.roster.active
        self.activate_btn.setEnabled(not is_active)
        self.activate_btn.setText("Active" if is_active else "Set active")
        self.dirty = False
        self.update_totals()

    def update_totals(self):
        if self.roster is None:
            return
        preview = Roster()
        lineup = Lineup(id="preview", name="preview")
        for d in DISTANCES:
            for slot in self.slots[d]:
                b = slot.preview_build()
                if b is not None:
                    b.id = f"p{len(preview.builds)}"
                    preview.builds[b.id] = b
                    lineup.slots[d].append(b.id)
        text = self.displayed.text().strip()
        lineup.displayed_rating = int(text) if text else None
        lr = lineup_rating(preview, lineup, self.s_bonus)
        for d in DISTANCES:
            eff = lr.team_eff.get(d)
            self.team_labels[d].setText(f"Team rating {eff:,.0f}" if eff else "")
        if lr.computed is None:
            computed = "No ratings entered yet"
        else:
            computed = f"Computed total {lr.computed:,.0f} ({lr.rated}/{lr.members} rated"
            computed += "; the rest count as the average)" if lr.rated < lr.members else ")"
        if lr.displayed and lr.computed:
            diff = lr.displayed - lr.computed
            computed += f" · displayed is {'+' if diff >= 0 else '−'}{abs(diff):,.0f} vs computed"
        self.totals.setText(computed)

    # --- lineup actions ------------------------------------------------------------

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        answer = QMessageBox.question(self, "Unsaved changes",
                                      "Discard the changes you made to this lineup?",
                                      QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel)
        return answer == QMessageBox.Discard

    def _lineup_picked(self, index):
        lineup_id = self.lineup_box.itemData(index)
        if lineup_id == self.viewed:
            return
        if not self._confirm_discard():
            self._fill_lineup_box()
            return
        self.viewed = lineup_id
        self.status.setText("")
        self._show_lineup()

    def _new_lineup(self):
        result = self._collect()
        if isinstance(result, str):
            self.status.setText(result)
            return
        roster, settings, _ = result
        name, ok = QInputDialog.getText(self, "New lineup", "Name for the new lineup:",
                                        text=roster.unique_name(f"Lineup {len(roster.lineups) + 1}"))
        if not ok or not name.strip():
            return
        self._save_as_new(roster, settings, name.strip())

    def _save_as_new(self, roster: Roster, settings, name):
        """Put the page's slots in a new lineup and keep the viewed one as it was."""
        edited = roster.lineup(self.viewed)
        original = self.roster.lineup(self.viewed)
        new = roster.new_lineup(roster.unique_name(name), source=edited)
        if edited is not None and original is not None:
            edited.slots = {d: list(original.slots.get(d, [])) for d in DISTANCES}
            edited.displayed_rating = original.displayed_rating
        roster.active = new.id
        self.viewed = new.id
        self.status.setText(f"Saved as the new lineup “{new.name}”, now active.")
        self.dirty = False
        self.saved.emit(settings, roster)

    def _rename(self):
        lineup = self.roster.lineup(self.viewed) if self.roster else None
        if lineup is None:
            return
        name, ok = QInputDialog.getText(self, "Rename lineup", "Name:", text=lineup.name)
        if not ok or not name.strip() or name.strip() == lineup.name:
            return
        if name.strip() in {l.name for l in self.roster.lineups}:
            self.status.setText(f"There's already a lineup called “{name.strip()}”.")
            return
        self._save(rename=name.strip())

    def _activate(self):
        self._save(activate=True)

    # --- saving --------------------------------------------------------------------

    def _collect(self):
        """(roster, settings, slots_changed) from the page, or an error message."""
        if self._settings is None or self.roster is None:
            return "Nothing to save yet."
        roster = self.roster.copy()
        lineup = roster.lineup(self.viewed)
        if lineup is None:
            lineup = roster.new_lineup("Original")
            roster.active = roster.legacy_lineup = lineup.id
            self.viewed = lineup.id
        names = []
        new_slots = {d: [] for d in DISTANCES}
        for d in DISTANCES:
            for slot in self.slots[d]:
                name = slot.name.text().strip()
                if not name:
                    continue
                names.append(name)
                stats = slot.stats()
                build = roster.builds.get(slot.build_id) if slot.build_id else None
                if build is not None and build.character == name and slot.new_version:
                    build = roster.new_version(build)
                    for k, v in stats.items():
                        setattr(build, k, v)
                elif build is not None and build.character == name:
                    for k, v in stats.items():  # typo fixes edit in place
                        setattr(build, k, v)
                else:
                    latest = roster.latest_build(name)
                    probe = Build(id="", character=name, **stats)
                    if latest is not None and latest.same_stats(probe) and not slot.new_version:
                        build = latest
                    else:
                        label_ = f"v{len(roster.builds_of(name)) + 1}"
                        build = roster.new_build(name, label=label_, **stats)
                new_slots[d].append(build.id)
        unassigned = [n.strip() for n in self.unassigned.text().split(",") if n.strip()]
        everyone = names + [n for n in unassigned if n not in names]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            return f"Each racer can only be in one slot: {', '.join(dupes)}"
        changed = any(new_slots[d] != lineup.slots.get(d, []) for d in DISTANCES)
        lineup.slots = new_slots
        text = self.displayed.text().strip()
        lineup.displayed_rating = int(text) if text else None
        hotkey = self.hotkey.text().strip().lower() or "ctrl+alt+s"
        settings = replace(
            self._settings.with_roster([n for n in everyone if n not in names], {}),
            capture_hotkey=hotkey,
            game_process=self.process.text().strip() or self._settings.game_process,
        )
        return roster, settings, changed

    def _save(self, rename=None, activate=False):
        result = self._collect()
        if isinstance(result, str):
            self.status.setText(result)
            return
        roster, settings, changed = result
        lineup = roster.lineup(self.viewed)
        if changed and self.match_counts.get(self.viewed, 0):
            box = QMessageBox(self)
            box.setWindowTitle("Lineup has matches")
            n = self.match_counts[self.viewed]
            box.setText(f"“{lineup.name}” already has {n} recorded match{'es' if n != 1 else ''}. "
                        "Changing who's in it would rewrite their history.")
            box.setInformativeText("Save these teams as a new lineup instead? (Recommended)")
            as_new = box.addButton("Save as new lineup", QMessageBox.AcceptRole)
            in_place = box.addButton("Change this lineup", QMessageBox.DestructiveRole)
            box.addButton(QMessageBox.Cancel)
            box.setDefaultButton(as_new)
            box.exec()
            clicked = box.clickedButton()
            if clicked is as_new:
                name, ok = QInputDialog.getText(self, "New lineup", "Name for the new lineup:",
                                                text=roster.unique_name(f"Lineup {len(roster.lineups) + 1}"))
                if ok and name.strip():
                    self._save_as_new(roster, settings, name.strip())
                return
            if clicked is not in_place:
                return
        if rename:
            lineup.name = rename
        if activate:
            roster.active = lineup.id
        self.dirty = False
        self.status.setText("Saved." + (f" “{lineup.name}” is now the active lineup." if activate else ""))
        self.saved.emit(settings, roster)

    # --- filling from the game -----------------------------------------------------

    def apply_detected(self, detected):
        """Fill empty slots with (name, distance) pairs read from a screenshot."""
        known = [s.name.text().strip() for d in DISTANCES for s in self.slots[d] if s.name.text().strip()]
        added = 0
        leftovers = []
        for raw, distance in detected:
            name = best_name(raw, extra=known)
            if name in known:
                continue
            target = next((s for s in self.slots.get(distance, []) if not s.name.text().strip()), None)
            if target is None:
                leftovers.append(name)
                continue
            target.name.setText(name)
            target._name_changed()
            known.append(name)
            added += 1
        # Placed names leave the "not on a team" list; unplaced ones join it
        placed = {s.name.text().strip() for d in DISTANCES for s in self.slots[d]}
        current = [n.strip() for n in self.unassigned.text().split(",") if n.strip()]
        self.unassigned.setText(", ".join(n for n in dict.fromkeys(current + leftovers) if n not in placed))
        self.status.setText(
            f"Filled {added} slot(s) from the game screen."
            + (f" Couldn't place: {', '.join(leftovers)}." if leftovers else "")
            + " Check the names, then Save."
        )
