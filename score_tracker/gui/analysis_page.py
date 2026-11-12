"""Analysis: average-based stats for your matches, teams and characters."""

from __future__ import annotations

from PySide6.QtCharts import QCategoryAxis, QChart, QChartView, QLineSeries, QScatterSeries, QValueAxis
from PySide6.QtCore import QMargins, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..analysis import RECENT, Analysis, CharacterStats, Form, TeamStats, rolling_mean
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


# --- the page -----------------------------------------------------------------------

CHAR_COLUMNS = [
    ("Character", "Character name"),
    ("Team", "Their current team (or the last one they ran in)"),
    ("Matches", "Matches they appear in"),
    ("Average", "Average score over all their matches"),
    ("Median", "Middle score: half their matches are above it"),
    ("Best", "Best score"),
    ("Worst", "Worst score"),
    ("Std", "Standard deviation: how much their score swings"),
    ("CV", "Coefficient of variation: swing relative to their average"),
    ("Team\nshare", "Average share of their team's total"),
    ("Team\nrank", "Average rank among their teammates (1 = top of the team)"),
    ("Match\nrank", "Average rank among all 15 in complete matches"),
    ("Team\ntop", "How often they're their team's top scorer"),
    ("Match\ntop", "How often they're the top scorer of the match"),
    ("Form", f"Average of their last {RECENT} matches vs. their overall average"),
]


class AnalysisPage(QWidget):
    delete_match_requested = Signal(int)

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        self._analysis: Analysis | None = None
        self._selected: str | None = None
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
        lay.addLayout(titles)

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
        hh = self.char_table.horizontalHeader()
        # Numbers share the width left after the names, so the table fits without scrolling
        hh.setSectionResizeMode(QHeaderView.Stretch)
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setMinimumSectionSize(36)
        self.char_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        hh.setDefaultAlignment(Qt.AlignRight | Qt.AlignVCenter)
        hh.setSortIndicatorShown(True)
        hh.setSortIndicator(3, Qt.DescendingOrder)  # highest average first
        self.char_table.itemSelectionChanged.connect(self._character_selected)
        chars_lay.addWidget(self.char_table)
        lay.addWidget(self.chars_card)

        self.detail_card, self.detail_lay = card()
        self.detail_card.setVisible(False)
        lay.addWidget(self.detail_card)

        # Recent matches
        self.matches_card, m_lay = card()
        m_lay.addWidget(label("Recent matches", "h2"))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Played", "Total", "vs average", "Characters", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2, 3):
            hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(4, 90)
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.setMinimumHeight(260)
        m_lay.addWidget(self.table)
        lay.addWidget(self.matches_card)
        lay.addStretch(1)

    # ------------------------------------------------------------------

    def refresh(self, analysis: Analysis | None):
        self._analysis = analysis
        has = analysis is not None and bool(analysis.matches)
        self.empty.setVisible(not has)
        for w in (self.tiles, self.teams_card, self.chart_card, self.chars_card, self.matches_card):
            w.setVisible(has)
        if not has:
            self.subtitle.setText("")
            self.detail_card.setVisible(False)
            return
        a = analysis
        o = a.overview
        self.subtitle.setText(
            f"Averages over all {o.matches} recorded matches. Every score includes opponent and "
            "support bonuses, so single matches are noisy; averages even that out."
            + (" Still few matches: keep capturing for steadier numbers." if o.complete < 10 else "")
        )
        self._fill_tiles(a)
        self._draw_teams(a)
        complete = a.complete_matches
        self.chart_card.setVisible(bool(complete))
        if complete:
            self.chart_view.setChart(history_chart([m.total for m in complete], [m.played_at for m in complete],
                                                   theme.ACCENT, o.totals.mean))
        self._fill_characters(a)
        self._fill_matches(a)

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
            is_top, is_weak = m is t.top, m is t.weakest
            if is_top:
                line.addWidget(_tag("Top", theme.SUCCESS))
            elif is_weak:
                line.addWidget(_tag("Weakest", theme.WARNING))
            elif not m.current:
                line.addWidget(_tag("Former", theme.FAINT))
            lay.addLayout(line)
            bar_color = theme.WARNING if is_weak else theme.distance_color(t.distance) if m.current else theme.FAINT
            lay.addWidget(_bar(m.share / best_share, bar_color))
            detail = f"avg {_int(m.mean)} · {_pct(m.share)} of team"
            if not m.current:
                detail += f" · {m.matches} matches"
            if is_weak:
                detail += f" · {_signed(t.weakest_gap)} vs per-member avg"
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
        for r, c in enumerate(a.characters):
            s = c.scores
            name = SortItem(c.name, c.name.lower(), Qt.AlignLeft | Qt.AlignVCenter)
            team = SortItem(c.team or "—", c.team or "~", Qt.AlignLeft | Qt.AlignVCenter)
            team.setForeground(QColor(theme.distance_color(c.team)))
            cells = [
                name, team,
                SortItem(f"{s.n}", s.n),
                SortItem(_int(s.mean), s.mean),
                SortItem(_k(s.median), s.median),
                SortItem(_k(s.best), s.best),
                SortItem(_k(s.worst), s.worst),
                SortItem(_k(s.std), s.std),
                SortItem(_pct(s.cv), s.cv),
                SortItem(_pct(c.share_of_team), c.share_of_team),
                SortItem("—" if c.rank_in_team is None else f"{c.rank_in_team:.2f}", c.rank_in_team),
                SortItem("—" if c.rank_in_match is None else f"{c.rank_in_match:.1f}", c.rank_in_match),
                SortItem(_pct(c.top_of_team, 0), c.top_of_team),
                SortItem(_pct(c.top_of_match, 0), c.top_of_match),
                SortItem(_form_text(c.form, compact=True) if c.form else "—",
                         c.form.pct if c.form else None),
            ]
            if c.form:
                cells[-1].setForeground(QColor(_form_color(c.form)))
            cells[-1].setToolTip(_form_text(c.form))
            for col, item in enumerate(cells):
                item.setData(Qt.UserRole, c.name)
                table.setItem(r, col, item)
        table.setSortingEnabled(True)
        table.resizeRowsToContents()
        height = table.horizontalHeader().height() + sum(table.rowHeight(i) for i in range(table.rowCount()))
        table.setFixedHeight(height + 4)
        table.blockSignals(False)
        names = {c.name for c in a.characters}
        if self._selected in names:
            self._select_row(self._selected)
            self._show_detail(self._selected)
        else:
            self._selected = None
            self.detail_card.setVisible(False)

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
            for col, item in enumerate((when, total, vs, chars)):
                self.table.setItem(i, col, item)
            delete = QPushButton("Delete")
            delete.setObjectName("iconButton")
            delete.clicked.connect(lambda _=False, mid=m.match_id: self.delete_match_requested.emit(mid))
            self.table.setCellWidget(i, 4, delete)
        self.table.resizeRowsToContents()
