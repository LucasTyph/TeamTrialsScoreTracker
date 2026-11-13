"""Analysis: average-based stats for your matches, teams and characters."""

from __future__ import annotations

from PySide6.QtCharts import QCategoryAxis, QChart, QChartView, QLineSeries, QScatterSeries, QValueAxis
from PySide6.QtCore import QEvent, QMargins, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..analysis import RECENT, Analysis, CharacterStats, Form, TeamStats, rolling_mean
from ..profiles import Profile, profiles, strongest, weakest
from ..ratings import compare_lineups, effective_rating
from . import theme
from .widgets import SortItem, StatTile, card, clear_layout, distance_badge, label


# --- formatting -------------------------------------------------------------------

def _k(value) -> str:
    """1,129,370 -> 1.129M; 86,501 -> 86.5k."""
    if value is None:
        return "—"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.3f}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.1f}k"
    return f"{value:.0f}"


def _int(value) -> str:
    return "—" if value is None else f"{value:,.0f}"


def _signed(value) -> str:
    return f"{'+' if value >= 0 else '−'}{abs(value):,.0f}"


def _pct(value, digits=1) -> str:
    return "—" if value is None else f"{value * 100:.{digits}f}%"


def _signed_pct(value) -> str:
    return f"{'+' if value >= 0 else '−'}{abs(value) * 100:.1f}%"


def _form_color(f: Form | None, threshold=0.01):
    if f is None or abs(f.pct) < threshold:
        return theme.MUTED
    return theme.SUCCESS if f.delta > 0 else theme.DANGER


def _form_text(f: Form | None, compact=False) -> str:
    if f is None:
        return f"Needs more than {RECENT} matches"
    if compact:
        return _signed_pct(f.pct)
    return f"{_signed(f.delta)} ({_signed_pct(f.pct)})"


def _when(dt) -> str:
    return f"{dt:%a %b %d, %H:%M}"


def _rank_text(rank, count) -> str:
    if count > 1 and rank == 1:
        return "#1 · Strongest"
    if count > 1 and rank == count:
        return f"#{rank} · Weakest"
    return f"#{rank}"


def _tag(text, color) -> QWidget:
    tag = label(text, "badge")
    tag.setStyleSheet(f"background: {theme.rgba(color, 0.18)}; color: {color};")
    tag.setAlignment(Qt.AlignCenter)
    tag.setFixedHeight(20)
    return tag


def _bar(fraction, color, height=6) -> QProgressBar:
    bar = QProgressBar()
    bar.setRange(0, 1000)
    bar.setValue(int(1000 * max(0.0, min(1.0, fraction))))
    bar.setTextVisible(False)
    bar.setFixedHeight(height)
    bar.setStyleSheet(f"QProgressBar {{ background: {theme.BG}; border: none; border-radius: {height // 2}px; }}"
                      f"QProgressBar::chunk {{ background: {color}; border-radius: {height // 2}px; }}")
    return bar


# --- charts -------------------------------------------------------------------------

def _axis_style(axis):
    axis.setLabelsColor(QColor(theme.MUTED))
    axis.setGridLineColor(QColor(theme.BORDER))
    axis.setLinePenColor(QColor(theme.BORDER))
    font = QFont()
    font.setPointSizeF(8.5)
    axis.setLabelsFont(font)


def history_chart(values, dates, color, average=None, window=RECENT) -> QChart:
    """Values in match order: dots, a rolling average and the overall average.

    The x axis is the match number (so evenings with several matches don't
    bunch up), labelled with the day each run of matches started.
    """
    chart = QChart()
    chart.setBackgroundVisible(False)
    chart.setPlotAreaBackgroundVisible(False)
    chart.legend().setLabelColor(QColor(theme.MUTED))
    chart.legend().setAlignment(Qt.AlignBottom)
    chart.setMargins(QMargins(0, 0, 0, 0))

    dots = QScatterSeries()
    dots.setName("Match")
    dots.setMarkerSize(7)
    dots.setColor(QColor(color))
    dots.setBorderColor(QColor(color))
    roll = QLineSeries()
    roll.setName(f"Rolling average ({window} matches)")
    roll.setPen(QPen(QColor(theme.TEXT), 2.0))
    for i, (v, r) in enumerate(zip(values, rolling_mean(values, window)), start=1):
        dots.append(i, v / 1000)
        roll.append(i, r / 1000)
    series = [dots, roll]
    n = len(values)
    if average is not None and n:
        avg = QLineSeries()
        avg.setName("Overall average")
        pen = QPen(QColor(theme.WARNING), 1.4)
        pen.setStyle(Qt.DashLine)
        avg.setPen(pen)
        avg.append(0.5, average / 1000)
        avg.append(n + 0.5, average / 1000)
        series.append(avg)
    for s in series:
        chart.addSeries(s)

    ax = QCategoryAxis()
    ax.setLabelsPosition(QCategoryAxis.AxisLabelsPositionOnValue)
    starts = []
    for i, d in enumerate(dates, start=1):
        if not starts or d.date() != starts[-1][1].date():
            starts.append((i, d))
    step = max(1, -(-len(starts) // 8))
    for i, d in starts[::step]:
        ax.append(f"{d:%b %d}", i)
    ax.setRange(0.5, max(n, 1) + 0.5)
    ay = QValueAxis()
    ay.setLabelFormat("%.0fk")
    if values:
        lo, hi = min(values) / 1000, max(values) / 1000
        span = max(hi - lo, 1)
        ay.setRange(lo - span * 0.12, hi + span * 0.12)
        ay.applyNiceNumbers()
    for axis in (ax, ay):
        _axis_style(axis)
    chart.addAxis(ax, Qt.AlignBottom)
    chart.addAxis(ay, Qt.AlignLeft)
    for s in series:
        s.attachAxis(ax)
        s.attachAxis(ay)
    return chart


def _chart_view(height) -> QChartView:
    view = QChartView()
    view.setRenderHint(QPainter.Antialiasing)
    view.setMinimumHeight(height)
    view.setStyleSheet("background: transparent;")
    return view


class RangeStrip(QWidget):
    """Worst-to-best range of a character's scores, with their average and the field's."""

    def __init__(self, p: Profile, lo, hi, field, color):
        super().__init__()
        self.p, self.lo, self.hi, self.field, self.color = p, lo, hi, field, color
        self.setMinimumHeight(40)
        self.setToolTip(f"Worst {p.worst:,.0f} · median {p.median:,.0f} · average {p.mean:,.0f} · "
                        f"best {p.best:,.0f}\nDashed line: the average racer ({field:,.0f})")

    def _x(self, v):
        span = (self.hi - self.lo) or 1
        return 6 + (self.width() - 12) * (v - self.lo) / span

    def paintEvent(self, event):
        p = self.p
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        y = 12
        painter.setPen(QPen(QColor(theme.BG), 6, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(int(self._x(self.lo)), y, int(self._x(self.hi)), y)
        painter.setPen(QPen(QColor(self.color), 6, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(int(self._x(p.worst)), y, int(self._x(p.best)), y)
        field_pen = QPen(QColor(theme.MUTED), 1.4)
        field_pen.setStyle(Qt.DashLine)
        painter.setPen(field_pen)
        fx = int(self._x(self.field))
        painter.drawLine(fx, y - 9, fx, y + 9)
        painter.setPen(QPen(QColor(theme.TEXT), 2.5))
        mx = int(self._x(p.mean))
        painter.drawLine(mx, y - 7, mx, y + 7)
        painter.setBrush(QColor(theme.TEXT))
        painter.drawEllipse(int(self._x(p.median)) - 2, y - 2, 4, 4)
        font = QFont()
        font.setPointSizeF(8)
        painter.setFont(font)
        painter.setPen(QColor(theme.FAINT))
        painter.drawText(int(self._x(p.worst)) - 2, y + 22, f"{p.worst / 1000:.1f}k")
        text = f"{p.best / 1000:.1f}k"
        painter.drawText(int(self._x(p.best)) - painter.fontMetrics().horizontalAdvance(text) + 2, y + 22, text)
        painter.setPen(QColor(theme.TEXT))
        avg = f"avg {p.mean / 1000:.1f}k"
        w = painter.fontMetrics().horizontalAdvance(avg)
        painter.drawText(max(0, min(self.width() - w, mx - w // 2)), y + 22, avg)
        painter.end()


# --- the page -----------------------------------------------------------------------

CHAR_COLUMNS = [
    ("Character", "Character name"),
    ("Team", "Their current team (or the last one they ran in)"),
    ("Match\ncount", "Matches they appear in"),
    ("Average", "Average score over all their matches"),
    ("Value", "Average score plus what their rating adds to everyone's bonus, compared with a racer "
              "at the lineup's average rating. Sort by it to see who to replace first."),
    ("Rating", "Base rating (before S boosts) in the lineup being analysed"),
    ("Eff.\nrating", "Effective rating: +2% per S aptitude"),
    ("Base\nscore", "Rating-neutral average: each score divided by (1 + rating bonus) of its lineup"),
    ("Median", "Middle score: half their matches are above it"),
    ("Best", "Best score"),
    ("Worst", "Worst score"),
    ("Std", "Standard deviation: how much their score swings"),
    ("CV", "Coefficient of variation: swing relative to their average"),
    ("Team\nshare", "Average share of their team's total"),
    ("Team\nrank", "Average rank among their teammates (1 = top of the team)"),
    ("Match\nrank", "Average rank among all 15 in complete matches"),
    ("Match\ntop", "How often they're the top scorer of the match"),
]


class AnalysisPage(QWidget):
    delete_match_requested = Signal(int)
    move_match_requested = Signal(int, str)  # match id, lineup id
    lineup_filter_changed = Signal(str)  # lineup id, "" = all
    use_fit_toggled = Signal(bool)

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        self._analysis: Analysis | None = None
        self._selected: str | None = None
        self._roster = None
        self._settings = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(self.scroll)
        body = QWidget()
        self.scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(16)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label("Analysis", "h1"))
        self.subtitle = label("", "muted", wrap=True)
        titles.addWidget(self.subtitle)
        head = QHBoxLayout()
        head.addLayout(titles, 1)
        self.filter_label = label("Lineup", "muted")
        self.filter_box = QComboBox()
        self.filter_box.setMinimumWidth(220)
        self.filter_box.activated.connect(
            lambda i: self.lineup_filter_changed.emit(self.filter_box.itemData(i) or ""))
        head.addWidget(self.filter_label, 0, Qt.AlignTop)
        head.addWidget(self.filter_box, 0, Qt.AlignTop)
        lay.addLayout(head)

        self.empty = label("No matches yet. Capture a match and it will show up here.", "muted")
        lay.addWidget(self.empty)

        # Overview tiles
        self.tiles = QWidget()
        tiles = QGridLayout(self.tiles)
        tiles.setContentsMargins(0, 0, 0, 0)
        tiles.setSpacing(12)
        self.t_matches = StatTile("Matches recorded")
        self.t_average = StatTile("Average match total")
        self.t_median = StatTile("Median match total")
        self.t_best = StatTile("Best match")
        self.t_worst = StatTile("Worst match")
        self.t_form = StatTile(f"Recent form (last {RECENT})")
        for i, t in enumerate((self.t_matches, self.t_average, self.t_median,
                               self.t_best, self.t_worst, self.t_form)):
            tiles.addWidget(t, i // 3, i % 3)
            tiles.setColumnStretch(i % 3, 1)
        lay.addWidget(self.tiles)

        # Team board
        self.teams_card, teams_lay = card()
        teams_lay.addWidget(label("Teams", "h2"))
        teams_lay.addWidget(label(
            "Average team total per match, over the matches where all three members were read. "
            "Teams are who actually ran where, so past matches stay with the team they were run in.",
            "muted", wrap=True))
        self.team_bars = QGridLayout()
        self.team_bars.setHorizontalSpacing(12)
        self.team_bars.setVerticalSpacing(8)
        teams_lay.addLayout(self.team_bars)
        teams_lay.addSpacing(4)
        self.teams_grid = QGridLayout()
        self.teams_grid.setHorizontalSpacing(12)
        self.teams_grid.setVerticalSpacing(12)
        teams_lay.addLayout(self.teams_grid)
        lay.addWidget(self.teams_card)

        # Ratings
        self.ratings_card, r_lay = card()
        r_lay.addWidget(label("Ratings", "h2"))
        self.ratings_note = label("", "muted", wrap=True)
        r_lay.addWidget(self.ratings_note)
        self.rating_tiles = QWidget()
        rt = QGridLayout(self.rating_tiles)
        rt.setContentsMargins(0, 0, 0, 0)
        rt.setSpacing(12)
        self.t_rating = StatTile("Team rating")
        self.t_bonus = StatTile("Rating bonus")
        self.t_marginal = StatTile("Value of 1k rating")
        self.t_fit = StatTile("Bonus fitted from your lineups")
        for i, t in enumerate((self.t_rating, self.t_bonus, self.t_marginal, self.t_fit)):
            rt.addWidget(t, 0, i)
            rt.setColumnStretch(i, 1)
        r_lay.addWidget(self.rating_tiles)
        fit_row = QHBoxLayout()
        self.fit_text = label("", "faint", wrap=True)
        fit_row.addWidget(self.fit_text, 1)
        self.fit_btn = QPushButton("Use fitted value")
        self.fit_btn.clicked.connect(self._toggle_fit)
        fit_row.addWidget(self.fit_btn)
        r_lay.addLayout(fit_row)
        lay.addWidget(self.ratings_card)

        # Replace first + what-if
        self.replace_card, rp_lay = card()
        rp_lay.addWidget(label("Replace first", "h2"))
        self.replace_note = label("", "muted", wrap=True)
        rp_lay.addWidget(self.replace_note)
        self.replace_list = QGridLayout()
        self.replace_list.setSpacing(12)
        rp_lay.addLayout(self.replace_list)
        lay.addWidget(self.replace_card)

        self.top_card, tp_lay = card()
        tp_lay.addWidget(label("Top performers", "h2"))
        self.top_note = label("", "muted", wrap=True)
        tp_lay.addWidget(self.top_note)
        self.top_list = QGridLayout()
        self.top_list.setSpacing(12)
        tp_lay.addLayout(self.top_list)
        lay.addWidget(self.top_card)

        # Compare lineups
        self.compare_card, c_lay = card()
        c_lay.addWidget(label("Compare lineups", "h2"))
        c_lay.addWidget(label(
            "Average difference between two lineups, with its 95% range. Rating-adjusted takes the rating "
            "bonus out, to show what changed apart from the rating.", "muted", wrap=True))
        c_row = QHBoxLayout()
        self.c_a = QComboBox()
        self.c_b = QComboBox()
        for box in (self.c_a, self.c_b):
            box.setMinimumWidth(200)
            box.currentIndexChanged.connect(self._update_compare)
        c_row.addWidget(self.c_a)
        c_row.addWidget(label("→", "muted"))
        c_row.addWidget(self.c_b)
        c_row.addStretch(1)
        c_lay.addLayout(c_row)
        self.c_summary = label("", None, wrap=True)
        c_lay.addWidget(self.c_summary)
        self.c_table = QTableWidget(0, 6)
        self.c_table.setHorizontalHeaderLabels(["", "Before", "After", "Difference", "95% range", ""])
        self.c_table.verticalHeader().setVisible(False)
        self.c_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.c_table.setSelectionMode(QTableWidget.NoSelection)
        self.c_table.setFocusPolicy(Qt.NoFocus)
        self.c_table.setAlternatingRowColors(True)
        self.c_table.setShowGrid(False)
        self.c_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.c_table.setObjectName("compactTable")
        self.c_table.setWordWrap(False)
        self.c_table.verticalHeader().setDefaultSectionSize(30)
        ch = self.c_table.horizontalHeader()
        ch.setSectionResizeMode(QHeaderView.ResizeToContents)
        ch.setSectionResizeMode(5, QHeaderView.Stretch)
        ch.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        c_lay.addWidget(self.c_table)
        lay.addWidget(self.compare_card)

        # Match totals over time
        self.chart_card, chart_lay = card()
        chart_lay.addWidget(label("Match totals", "h2"))
        chart_lay.addWidget(label("Complete matches in the order you played them.", "muted"))
        self.chart_view = _chart_view(280)
        chart_lay.addWidget(self.chart_view)
        lay.addWidget(self.chart_card)

        # Characters
        self.chars_card, chars_lay = card()
        chars_lay.addWidget(label("Characters", "h2"))
        chars_lay.addWidget(label(
            "Every match each character appears in. Click a column to sort, or a character "
            "for their history.", "muted", wrap=True))
        self.char_table = QTableWidget(0, len(CHAR_COLUMNS))
        for i, (name, tip) in enumerate(CHAR_COLUMNS):
            item = QTableWidgetItem(name)
            item.setToolTip(tip)
            if i < 2:
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.char_table.setHorizontalHeaderItem(i, item)
        self.char_table.verticalHeader().setVisible(False)
        self.char_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.char_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.char_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.char_table.setAlternatingRowColors(True)
        self.char_table.setShowGrid(False)
        self.char_table.setFocusPolicy(Qt.NoFocus)
        self.char_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.char_table.setSortingEnabled(True)
        self.char_table.setObjectName("compactTable")
        self.char_table.setWordWrap(False)
        self.char_table.verticalHeader().setDefaultSectionSize(30)
        hh = self.char_table.horizontalHeader()
        # Each column gets the width its text needs, and the rest is shared out
        # (see _fit_columns), so the table fits without scrolling or cut-off text
        hh.setSectionResizeMode(QHeaderView.Fixed)
        hh.setStretchLastSection(True)
        hh.setMinimumSectionSize(24)
        hh.sortIndicatorChanged.connect(lambda *_: self._fit_columns())
        self.char_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.char_table.installEventFilter(self)  # refit the columns when the table resizes
        hh.setDefaultAlignment(Qt.AlignRight | Qt.AlignVCenter)
        hh.setSortIndicatorShown(True)
        hh.setSortIndicator(3, Qt.DescendingOrder)  # highest average first
        self.char_table.setColumnHidden(4, True)  # shown once ratings exist
        self.char_table.itemSelectionChanged.connect(self._character_selected)
        chars_lay.addWidget(self.char_table)
        lay.addWidget(self.chars_card)

        self.detail_card, self.detail_lay = card()
        self.detail_card.setVisible(False)
        lay.addWidget(self.detail_card)

        # Recent matches
        self.matches_card, m_lay = card()
        m_lay.addWidget(label("Recent matches", "h2"))
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Played", "Lineup", "Total", "vs average", "Characters", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2, 3, 4):
            hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 170)
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.setMinimumHeight(260)
        m_lay.addWidget(self.table)
        lay.addWidget(self.matches_card)
        lay.addStretch(1)

    # ------------------------------------------------------------------

    def refresh(self, analysis: Analysis | None, roster=None, filter_id="", match_counts=None, settings=None):
        self._analysis = analysis
        self._roster = roster
        self._settings = settings
        self._fill_filter(roster, filter_id, match_counts or {})
        has = analysis is not None and bool(analysis.matches)
        self.empty.setVisible(not has)
        self.empty.setText("No matches in this lineup yet." if filter_id else
                           "No matches yet. Capture a match and it will show up here.")
        for w in (self.tiles, self.teams_card, self.chart_card, self.chars_card, self.matches_card,
                  self.ratings_card, self.replace_card, self.top_card, self.compare_card):
            w.setVisible(has)
        if not has:
            self.subtitle.setText("")
            self.detail_card.setVisible(False)
            return
        a = analysis
        o = a.overview
        scope = f"the {o.matches} matches of “{a.lineup.name}”" if a.lineup else f"all {o.matches} recorded matches"
        self.subtitle.setText(
            f"Averages over {scope}. Every score includes opponent and "
            "support bonuses, so single matches are noisy; averages even that out."
            + (" Still few matches: keep capturing for steadier numbers." if o.complete < 10 else "")
        )
        self._fill_ratings(a)
        self._fill_profiles(a)
        self._fill_compare(a, match_counts or {})
        self._fill_tiles(a)
        self._draw_teams(a)
        complete = a.complete_matches
        self.chart_card.setVisible(bool(complete))
        if complete:
            self.chart_view.setChart(history_chart([m.total for m in complete], [m.played_at for m in complete],
                                                   theme.ACCENT, o.totals.mean))
        self._fill_characters(a)
        self._fill_matches(a)

    def _fill_filter(self, roster, filter_id, counts):
        self.filter_box.blockSignals(True)
        self.filter_box.clear()
        self.filter_box.addItem("All lineups", "")
        for l in (roster.lineups if roster else []):
            n = counts.get(l.id, 0)
            self.filter_box.addItem(f"{l.name} ({n})", l.id)
        self.filter_box.setCurrentIndex(max(self.filter_box.findData(filter_id), 0))
        self.filter_box.blockSignals(False)
        many = roster is not None and len(roster.lineups) > 1
        self.filter_box.setVisible(many)
        self.filter_label.setVisible(many)

    # --- ratings ----------------------------------------------------------------

    def _fill_ratings(self, a: Analysis):
        ra = a.ratings
        if ra is None:
            self.ratings_card.setVisible(False)
            for col in (4, 5, 6, 7):
                self.char_table.setColumnHidden(col, True)
            return
        ref = ra.reference
        ready = ra.marginal is not None
        any_rating = self._roster is not None and any(b.rating for b in self._roster.builds.values())
        for col in (5, 6, 7):
            self.char_table.setColumnHidden(col, not any_rating)
        self.char_table.setColumnHidden(4, not ready)
        name = f"“{ref.lineup.name}”"
        if ref.rating is None:
            self.ratings_note.setText(
                f"Enter your racers' ratings (or the game's displayed team rating) for {name} on the Roster "
                "page to see how much rating is worth and who to replace first.")
        elif ra.match_total is None:
            self.ratings_note.setText(f"No complete match of {name} yet: capture one to see the value of rating.")
        else:
            self.ratings_note.setText(
                f"For {name}. Every score is base × (1 + bonus) and the bonus grows with your opponents' rating, "
                "which matchmaking keeps close to yours. So more rating raises all 15 scores a little.")
        self.rating_tiles.setVisible(ref.rating is not None)
        if ref.rating is not None:
            if ref.displayed:
                detail = "Displayed in the game"
                if ref.computed:
                    detail += f" · computed {ref.computed:,.0f}"
            else:
                detail = f"Sum of effective ratings · {ref.rated}/{ref.members} rated"
            self.t_rating.set(f"{ref.rating:,.0f}", detail)
            source = "fitted from your lineups" if ra.using_fit else "your estimate"
            self.t_bonus.set(f"+{ra.bonus:.0%}" if ra.bonus is not None else "—",
                             f"{ra.per_1k:.2f}% per 1k of rating ({source})")
            if ra.marginal is not None:
                self.t_marginal.set(f"+{ra.marginal_per_1k:,.0f}",
                                    f"Match points per 1k of team rating, spread over all 15 "
                                    f"(average match {ra.match_total:,.0f})")
            else:
                self.t_marginal.set("—", "Needs a complete match")
        fit = ra.fit
        if fit is None:
            self.t_fit.set("—", "Needs two lineups with different ratings and 3+ complete matches each")
            self.fit_text.setText(f"Using {ra.prior:.2f}% per 1k (rating_bonus_per_1k).")
            self.fit_btn.setVisible(False)
        else:
            self.t_fit.set(f"{fit.per_1k:.2f}% ± {1.96 * fit.se:.2f}",
                           f"per 1k · {fit.matches} matches over {fit.lineups} lineups")
            using = "the fitted value" if ra.using_fit else f"your estimate ({ra.prior:.2f}% per 1k)"
            self.fit_text.setText(f"Using {using}. The fit compares match totals between lineups with different "
                                  "ratings; it's noisy until each lineup has many matches.")
            self.fit_btn.setVisible(True)
            self.fit_btn.setText("Use my estimate" if ra.using_fit else "Use fitted value")

    def _toggle_fit(self):
        ra = self._analysis.ratings if self._analysis else None
        if ra is not None:
            self.use_fit_toggled.emit(not ra.using_fit)

    def _fill_profiles(self, a: Analysis):
        clear_layout(self.replace_list)
        clear_layout(self.top_list)
        items = profiles(a)
        show = len(items) >= 4
        self.replace_card.setVisible(show)
        self.top_card.setVisible(show)
        if not show:
            return
        by_value = any(p.value is not None for p in items)
        basis = ("Value (average score plus what their rating adds to all 15)" if by_value
                 else "average score (enter ratings on the Roster page to rank by Value)")
        self.replace_note.setText(f"The three lowest by {basis}, and what in their scores makes them weak. "
                                  "Compared with the other racers of the lineup; #1 is the best of them.")
        self.top_note.setText(f"The three highest by {basis.split(' (')[0]}, and what makes them strong.")
        lo = min(p.worst for p in items)
        hi = max(p.best for p in items)
        field = sum(m.total for m in a.matches) / max(1, sum(m.characters for m in a.matches))
        for col, p in enumerate(weakest(items)):
            self.replace_list.addWidget(self._profile_card(p, col + 1, lo, hi, field, -1), 0, col)
        for col, p in enumerate(strongest(items)):
            self.top_list.addWidget(self._profile_card(p, col + 1, lo, hi, field, +1), 0, col)
        for grid in (self.replace_list, self.top_list):
            for col in range(3):
                grid.setColumnStretch(col, 1)

    def _profile_card(self, p: Profile, rank, lo, hi, field, side) -> QFrame:
        frame = QFrame()
        frame.setObjectName("teamCard")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(14, 12, 14, 12)
        fl.setSpacing(6)
        head = QHBoxLayout()
        head.addWidget(label(f"{rank}. {p.name}", "h2"))
        head.addStretch(1)
        head.addWidget(distance_badge(p.team))
        fl.addLayout(head)
        color = theme.SUCCESS if side > 0 else theme.WARNING
        fl.addWidget(_tag(p.archetype, color), 0, Qt.AlignLeft)
        fl.addWidget(RangeStrip(p, lo, hi, field, theme.distance_color(p.team)))

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(3)
        n = p.peers
        rows = [
            ("Average", f"{_int(p.mean)} · #{p.rank_mean}/{n}"),
            ("vs match avg", f"{_signed(p.vs_field)} ± {1.96 * p.vs_field_se:,.0f}"),
            ("Beat match avg", f"{p.hits}/{p.matches} ({p.hit_rate:.0%})"),
            ("Ceiling (best)", f"{_k(p.best)} · #{p.rank_best}/{n}"),
            ("Floor (worst)", f"{_k(p.worst)} · #{p.rank_worst}/{n}"),
            ("Consistency", f"CV {_pct(p.cv)} · #{p.rank_cv}/{n}"),
            ("Average / best", _pct(p.of_best, 0)),
        ]
        if p.value is not None:
            rows.insert(1, ("Value", _int(p.value)))
        if p.rating_worth is not None:
            rows.append(("Rating effect", f"{_signed(p.rating_worth)} / match"))
        for r, (caption, value) in enumerate(rows):
            grid.addWidget(label(caption, "faint"), r, 0)
            v = label(value)
            v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(v, r, 1)
        grid.setColumnStretch(1, 1)
        fl.addLayout(grid)

        # Reasons that point the same way first
        reasons = sorted(p.reasons, key=lambda r: (r[1] != side, r[1] == 0))
        for text, sentiment in reasons[:4]:
            mark = "▲" if sentiment > 0 else "▼" if sentiment < 0 else "•"
            tone = theme.SUCCESS if sentiment > 0 else theme.DANGER if sentiment < 0 else theme.MUTED
            line = label(f"<span style='color:{tone}'>{mark}</span> {text}", None, wrap=True)
            line.setTextFormat(Qt.RichText)
            line.setStyleSheet(f"color: {theme.MUTED};")
            fl.addWidget(line)
        fl.addStretch(1)
        return frame

    # --- comparing lineups -----------------------------------------------------------

    def _fill_compare(self, a: Analysis, counts):
        roster = self._roster
        with_matches = [l for l in (roster.lineups if roster else []) if counts.get(l.id, 0)]
        show = a.ratings is not None and len(with_matches) >= 2
        self.compare_card.setVisible(show)
        if not show:
            return
        keep_a, keep_b = self.c_a.currentData(), self.c_b.currentData()
        for box in (self.c_a, self.c_b):
            box.blockSignals(True)
            box.clear()
            for l in with_matches:
                box.addItem(f"{l.name} ({counts[l.id]})", l.id)
        ids = [l.id for l in with_matches]
        default_b = roster.active if roster.active in ids else ids[-1]
        default_a = next((i for i in reversed(ids) if i != default_b), ids[0])
        self.c_a.setCurrentIndex(self.c_a.findData(keep_a if keep_a in ids else default_a))
        self.c_b.setCurrentIndex(self.c_b.findData(keep_b if keep_b in ids else default_b))
        for box in (self.c_a, self.c_b):
            box.blockSignals(False)
        self._update_compare()

    def _update_compare(self, *_):
        a = self._analysis
        roster = self._roster
        if a is None or a.ratings is None or roster is None:
            return
        la, lb = roster.lineup(self.c_a.currentData()), roster.lineup(self.c_b.currentData())
        table = self.c_table
        table.setRowCount(0)
        if la is None or lb is None or la.id == lb.id:
            self.c_summary.setText("Pick two different lineups.")
            table.setVisible(False)
            return
        table.setVisible(True)
        ra = a.ratings
        s_bonus = self._settings.s_aptitude_bonus if self._settings else 0.02
        cmp = compare_lineups(ra.frame, roster, la, lb, ra.per_1k, s_bonus, ra.match_size)
        rows = [("Match total", cmp.raw), ("Match total, rating-adjusted", cmp.adjusted)]
        rows += [(f"{d} team", dd) for d, dd in cmp.teams.items()]
        for d, i, ba, bb, dd in cmp.slots:
            before = f"{ba.character} {ba.label}" if ba else "empty"
            after = f"{bb.character} {bb.label}" if bb else "empty"
            same = ba is not None and bb is not None and ba.id == bb.id
            rows.append((f"{d} {i + 1}: {before}" + ("" if same else f" → {after}"), dd))
        main = cmp.raw
        if main is None:
            self.c_summary.setText("Both lineups need a complete match to compare totals.")
        else:
            self.c_summary.setText(f"“{lb.name}” vs “{la.name}”: {_signed(main.delta)} per match "
                                   f"({_signed_pct(main.pct)}), {self._verdict(main)}.")
        table.setRowCount(len(rows))
        for r, (caption, dd) in enumerate(rows):
            cells = [QTableWidgetItem(caption)]
            if dd is None:
                cells += [QTableWidgetItem("—") for _ in range(4)] + [QTableWidgetItem("Not enough matches")]
            else:
                cells += [QTableWidgetItem(_int(dd.a)), QTableWidgetItem(_int(dd.b)),
                          QTableWidgetItem(f"{_signed(dd.delta)} ({_signed_pct(dd.pct)})"),
                          QTableWidgetItem(f"{_signed(dd.low)} … {_signed(dd.high)}" if dd.se else "—"),
                          QTableWidgetItem(self._verdict(dd))]
                if dd.significant:
                    cells[3].setForeground(QColor(theme.SUCCESS if dd.delta > 0 else theme.DANGER))
            for c in cells[1:5]:
                c.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            cells[5].setForeground(QColor(theme.FAINT))
            for col, item in enumerate(cells):
                table.setItem(r, col, item)
        height = table.horizontalHeader().sizeHint().height() + 30 * table.rowCount()
        table.setFixedHeight(height + 4)

    @staticmethod
    def _verdict(dd) -> str:
        if dd.significant:
            return "significant"
        n = f"n = {dd.n_a} vs {dd.n_b}"
        need = dd.needed()
        if need and need > 500:
            return f"no real difference so far ({n})"
        if need and need > max(dd.n_a, dd.n_b):
            return f"not significant yet ({n}; ≈{need} matches each to tell)"
        return f"not significant ({n})"

    def _fill_tiles(self, a: Analysis):
        o = a.overview
        self.t_matches.set(f"{o.matches}", f"{o.complete} complete · {o.partial} partial")
        if not o.complete:
            for t in (self.t_average, self.t_median, self.t_best, self.t_worst):
                t.set("—", "No complete match yet")
            self.t_form.set("—", "No complete match yet")
            return
        self.t_average.set(_int(o.totals.mean), f"± {o.totals.std:,.0f} typical swing (std)")
        self.t_median.set(_int(o.totals.median), "Half your matches score above this")
        self.t_best.set(f"{o.best.total:,}", f"{_when(o.best.played_at)} · {_signed(o.best.total - o.totals.mean)}"
                        " vs avg", theme.SUCCESS)
        self.t_worst.set(f"{o.worst.total:,}", f"{_when(o.worst.played_at)} · "
                         f"{_signed(o.worst.total - o.totals.mean)} vs avg", theme.DANGER)
        f = o.form
        if f is None:
            self.t_form.set("—", f"Needs more than {RECENT} complete matches")
        else:
            self.t_form.set(_signed(f.delta), f"{_signed_pct(f.pct)} · last {RECENT} average "
                            f"{f.recent:,.0f}", _form_color(f))

    # --- teams --------------------------------------------------------------

    def _draw_teams(self, a: Analysis):
        clear_layout(self.team_bars)
        clear_layout(self.teams_grid)
        teams = a.teams
        self.teams_card.setVisible(bool(teams))
        if not teams:
            return
        top = max(t.totals.mean for t in teams) or 1
        mean_team = sum(t.totals.mean for t in teams) / len(teams)
        for row, t in enumerate(sorted(teams, key=lambda t: t.rank)):
            badge = distance_badge(t.distance)
            badge.setFixedWidth(72)
            self.team_bars.addWidget(badge, row, 0)
            self.team_bars.addWidget(_bar(t.totals.mean / top, theme.distance_color(t.distance), 14), row, 1)
            self.team_bars.addWidget(label(_int(t.totals.mean)), row, 2, Qt.AlignRight)
            diff = (t.totals.mean - mean_team) / mean_team if mean_team else 0
            vs = label(f"{_signed_pct(diff)} vs avg team", "faint")
            vs.setMinimumWidth(110)
            self.team_bars.addWidget(vs, row, 3, Qt.AlignRight)
        self.team_bars.setColumnStretch(1, 1)
        for i, t in enumerate(teams):
            self.teams_grid.addWidget(self._team_card(t, len(teams)), i // 3, i % 3)
        for col in range(3):
            self.teams_grid.setColumnStretch(col, 1)

    def _team_card(self, t: TeamStats, count) -> QFrame:
        frame = QFrame()
        frame.setObjectName("teamCard")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)
        head = QHBoxLayout()
        head.addWidget(distance_badge(t.distance))
        head.addStretch(1)
        color = theme.SUCCESS if t.rank == 1 and count > 1 else theme.DANGER if t.rank == count and count > 1 \
            else theme.MUTED
        head.addWidget(_tag(_rank_text(t.rank, count), color))
        lay.addLayout(head)

        lay.addWidget(label(_int(t.totals.mean), "bigValue"))
        lay.addWidget(label(f"{_pct(t.share_of_match)} of the match total · {t.totals.n} matches", "muted"))
        ra = self._analysis.ratings if self._analysis else None
        team_eff = ra.reference.team_eff.get(t.distance) if ra else None
        if team_eff:
            lay.addWidget(label(f"Team rating {team_eff:,.0f}", "faint"))
        stats = label(f"Best {_k(t.totals.best)} · Worst {_k(t.totals.worst)} · CV {_pct(t.totals.cv)}", "faint")
        stats.setToolTip(f"Spread (std): {t.totals.std:,.0f}\n"
                         f"The average itself is ± {1.96 * t.totals.se:,.0f} (95%) with this many matches")
        lay.addWidget(stats)
        form_line = label(f"Last {RECENT}: {_form_text(t.form)}" if t.form else _form_text(None), "faint")
        if t.form:
            form_line.setStyleSheet(f"color: {_form_color(t.form)};")
        lay.addWidget(form_line)
        lay.addSpacing(4)

        best_share = max((m.share for m in t.members), default=1) or 1
        for m in t.members:
            line = QHBoxLayout()
            name = label(m.name, None if m.current else "faint")
            line.addWidget(name)
            line.addStretch(1)
            if not m.current:
                line.addWidget(_tag("Former", theme.FAINT))
            lay.addLayout(line)
            bar_color = theme.distance_color(t.distance) if m.current else theme.FAINT
            lay.addWidget(_bar(m.share / best_share, bar_color))
            detail = f"avg {_int(m.mean)} · {_pct(m.share)} of team"
            if not m.current:
                detail += f" · {m.matches} matches"
            if m.current:
                detail += f" · {_signed(m.mean - t.per_member)} vs team avg"
            slot = ra.by_name.get(m.name) if ra and m.current else None
            if slot is not None and slot.value is not None and ra.marginal is not None:
                detail += f" · value {_k(slot.value)}"
            d = label(detail, "faint", wrap=True)
            d.setToolTip(f"{m.name}: {m.matches} matches in this team\nAverage {m.mean:,.0f}, "
                         f"{m.share:.1%} of the team total\nTeam per-member average: {t.per_member:,.0f}")
            lay.addWidget(d)
        lay.addStretch(1)
        return frame

    # --- characters ------------------------------------------------------------

    def _fill_characters(self, a: Analysis):
        table = self.char_table
        table.setSortingEnabled(False)
        table.blockSignals(True)
        table.clearContents()
        table.setRowCount(len(a.characters))
        ra = a.ratings
        roster = self._roster
        s_bonus = self._settings.s_aptitude_bonus if self._settings else 0.02
        for r, c in enumerate(a.characters):
            s = c.scores
            slot = ra.by_name.get(c.name) if ra else None
            build = slot.build if slot else (roster.latest_build(c.name) if roster else None)
            rating = build.rating if build else None
            eff = slot.eff if slot else effective_rating(build, s_bonus)
            base = ra.base_by_name.get(c.name) if ra else None
            val = slot.value if slot and ra.marginal is not None else None
            name = SortItem(c.name, c.name.lower(), Qt.AlignLeft | Qt.AlignVCenter)
            team = SortItem(c.team or "—", c.team or "~", Qt.AlignLeft | Qt.AlignVCenter)
            team.setForeground(QColor(theme.distance_color(c.team)))
            cells = [
                name, team,
                SortItem(f"{s.n}", s.n),
                SortItem(_k(s.mean), s.mean),
                SortItem(_k(val), val),
                SortItem(_k(rating), rating),
                SortItem(_k(eff) + ("*" if build is not None and build.below_a else ""), eff),
                SortItem(_k(base), base),
                SortItem(_k(s.median), s.median),
                SortItem(_k(s.best), s.best),
                SortItem(_k(s.worst), s.worst),
                SortItem(_k(s.std), s.std),
                SortItem(_pct(s.cv), s.cv),
                SortItem(_pct(c.share_of_team), c.share_of_team),
                SortItem("—" if c.rank_in_team is None else f"{c.rank_in_team:.2f}", c.rank_in_team),
                SortItem("—" if c.rank_in_match is None else f"{c.rank_in_match:.1f}", c.rank_in_match),
                SortItem(_pct(c.top_of_match, 0), c.top_of_match),
            ]
            if build is not None and build.below_a:
                cells[6].setToolTip("Grades below A are stored but treated as A (not modelled)")
            if slot is None and build is not None:
                cells[5].setToolTip(f"Not in this lineup: latest version ({build.label})")
            for col, item in enumerate(cells):
                item.setData(Qt.UserRole, c.name)
                table.setItem(r, col, item)
        table.setSortingEnabled(True)
        self._char_table_height = table.horizontalHeader().sizeHint().height() + 30 * table.rowCount() + 4
        table.blockSignals(False)
        self._fit_columns()
        names = {c.name for c in a.characters}
        if self._selected in names:
            self._select_row(self._selected)
            self._show_detail(self._selected)
        else:
            self._selected = None
            self.detail_card.setVisible(False)

    def _fit_columns(self):
        """Size the character table's columns to their text, then share out the spare width."""
        table = self.char_table
        hh = table.horizontalHeader()
        head_fm = hh.fontMetrics()
        pad, arrow = 8, 14
        visible = [c for c in range(table.columnCount()) if not table.isColumnHidden(c)]
        need = {}
        for c in visible:
            head = table.horizontalHeaderItem(c)
            width = max((head_fm.horizontalAdvance(line) for line in head.text().split("\n")), default=0) + pad
            if hh.sortIndicatorSection() == c:
                width += arrow
            # Qt's own hint for the cells includes the stylesheet's padding
            need[c] = max(width, table.sizeHintForColumn(c) + 2)
        available = table.width() - 2 * table.frameWidth()
        spare = available - sum(need.values())
        numbers = [c for c in visible if c > 1] or visible
        for c in visible:
            extra = spare // len(numbers) if c in numbers and spare > 0 else 0
            table.setColumnWidth(c, need[c] + extra)
        # Too narrow a window: scroll sideways rather than cut text off
        overflow = spare < 0
        hh.setStretchLastSection(not overflow)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn if overflow else Qt.ScrollBarAlwaysOff)
        bar = table.horizontalScrollBar().sizeHint().height() if overflow else 0
        table.setFixedHeight(getattr(self, "_char_table_height", 0) + bar)

    def eventFilter(self, obj, event):
        if obj is self.char_table and event.type() == QEvent.Resize:
            self._fit_columns()
        return super().eventFilter(obj, event)

    def _select_row(self, name):
        for r in range(self.char_table.rowCount()):
            item = self.char_table.item(r, 0)
            if item is not None and item.data(Qt.UserRole) == name:
                self.char_table.blockSignals(True)
                self.char_table.selectRow(r)
                self.char_table.blockSignals(False)
                return

    def _character_selected(self):
        items = self.char_table.selectedItems()
        if not items:
            return
        name = items[0].data(Qt.UserRole)
        self._selected = name
        self._show_detail(name)

    def close_detail(self):
        self._selected = None
        self.char_table.clearSelection()
        self.detail_card.setVisible(False)

    def show_character(self, name):
        """Select a character and open their detail panel."""
        self._select_row(name)
        self._selected = name
        self._show_detail(name)

    def _show_detail(self, name):
        a = self._analysis
        c = next((c for c in a.characters if c.name == name), None) if a else None
        if c is None:
            self.detail_card.setVisible(False)
            return
        clear_layout(self.detail_lay)
        head = QHBoxLayout()
        head.addWidget(label(c.name, "h2"))
        head.addWidget(distance_badge(c.team))
        head.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.close_detail)
        head.addWidget(close)
        self.detail_lay.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(18)
        view = _chart_view(260)
        values = [h[2] for h in c.history]
        view.setChart(history_chart(values, [h[1] for h in c.history], theme.distance_color(c.team), c.scores.mean))
        body.addWidget(view, 3)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(8)
        s = c.scores
        pairs = [
            ("Matches", f"{s.n}"),
            ("Average", f"{s.mean:,.0f} ± {1.96 * s.se:,.0f}" if s.n > 1 else _int(s.mean)),
            ("Median", _int(s.median)),
            ("Spread (std)", f"{_int(s.std)} · CV {_pct(s.cv)}"),
            ("Best", f"{s.best:,.0f} · {c.best_match[0]:%b %d}"),
            ("Worst", f"{s.worst:,.0f} · {c.worst_match[0]:%b %d}"),
            ("Share of team", _pct(c.share_of_team)),
            ("vs team per-member avg", _signed(c.above_team_avg) if c.above_team_avg is not None else "—"),
            ("Rank in team", "—" if c.rank_in_team is None else f"{c.rank_in_team:.2f} of 3"),
            ("Rank in match", "—" if c.rank_in_match is None else f"{c.rank_in_match:.1f} of {a.match_size}"),
            ("Team's top scorer", _pct(c.top_of_team, 0)),
            ("Match's top scorer", _pct(c.top_of_match, 0)),
            (f"Last {RECENT} vs overall", _form_text(c.form)),
        ]
        if len(c.by_team) > 1:
            pairs.append(("By team", " · ".join(f"{p.distance or 'No team'} {_k(p.mean)} ({p.matches})"
                                                for p in c.by_team)))
        for r, (caption, value) in enumerate(pairs):
            grid.addWidget(label(caption, "statLabel"), r, 0)
            v = label(value, wrap=True)
            v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if caption.startswith("Last") and c.form:
                v.setStyleSheet(f"color: {_form_color(c.form)};")
            grid.addWidget(v, r, 1)
        grid.setColumnStretch(1, 1)
        grid.setVerticalSpacing(6)
        side = QVBoxLayout()
        side.addLayout(grid)
        side.addWidget(label("Average ± is the 95% range of the average itself: it narrows as you "
                             "record more matches.", "faint", wrap=True))
        side.addStretch(1)
        body.addLayout(side, 2)
        view.setMinimumHeight(360)
        self.detail_lay.addLayout(body)
        self.detail_card.setVisible(True)

    # --- matches ------------------------------------------------------------------

    def _fill_matches(self, a: Analysis):
        roster = self._roster
        matches = list(reversed(a.matches))[:50]
        self.table.setRowCount(len(matches))
        o = a.overview
        best_id = o.best.match_id if o.best else None
        for i, m in enumerate(matches):
            when = QTableWidgetItem(_when(m.played_at))
            total = QTableWidgetItem(f"{m.total:,}")
            total.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if m.match_id == best_id:
                total.setForeground(QColor(theme.SUCCESS))
            if m.complete and o.complete:
                diff = m.total - o.totals.mean
                vs = QTableWidgetItem(_signed(diff))
                vs.setForeground(QColor(theme.SUCCESS if diff >= 0 else theme.DANGER))
            else:
                vs = QTableWidgetItem("—")
                vs.setForeground(QColor(theme.FAINT))
            vs.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            chars = QTableWidgetItem(f"{m.characters}" + ("" if m.complete else " (partial)"))
            if not m.complete:
                chars.setForeground(QColor(theme.WARNING))
            lineup = roster.lineup(m.lineup) if roster else None
            lineup_item = QTableWidgetItem(lineup.name if lineup else "—")
            lineup_item.setForeground(QColor(theme.MUTED))
            for col, item in enumerate((when, lineup_item, total, vs, chars)):
                self.table.setItem(i, col, item)
            actions = QWidget()
            al = QHBoxLayout(actions)
            al.setContentsMargins(0, 0, 0, 0)
            al.setSpacing(4)
            if roster is not None and len(roster.lineups) > 1:
                move = QPushButton("Move…")
                move.setObjectName("iconButton")
                move.setToolTip("Attribute this match to another lineup")
                menu = QMenu(move)
                for l in roster.lineups:
                    if l.id == m.lineup:
                        continue
                    act = menu.addAction(l.name)
                    act.triggered.connect(lambda _=False, mid=m.match_id, lid=l.id:
                                          self.move_match_requested.emit(mid, lid))
                move.setMenu(menu)
                al.addWidget(move)
            delete = QPushButton("Delete")
            delete.setObjectName("iconButton")
            delete.clicked.connect(lambda _=False, mid=m.match_id: self.delete_match_requested.emit(mid))
            al.addWidget(delete)
            self.table.setCellWidget(i, 5, actions)
        self.table.resizeRowsToContents()
