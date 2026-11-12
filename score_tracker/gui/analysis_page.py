"""Analysis: what drives your weekly top score."""

from __future__ import annotations

from datetime import timezone

from PySide6.QtCharts import QChart, QChartView, QDateTimeAxis, QLineSeries, QScatterSeries, QValueAxis
from PySide6.QtCore import QDateTime, QMargins, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIntValidator, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..analysis import Report
from . import theme
from .widgets import StatTile, card, clear_layout, distance_badge, label


def _k(value) -> str:
    """1,129,370 -> 1.13M; 86,501 -> 86.5k."""
    if value is None:
        return "—"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.3f}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.1f}k"
    return f"{value:.0f}"


def _qdt(dt) -> QDateTime:
    return QDateTime.fromMSecsSinceEpoch(int(dt.astimezone(timezone.utc).timestamp() * 1000))


class AnalysisPage(QWidget):
    target_changed = Signal(int)
    delete_match_requested = Signal(int)

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
        lay = QVBoxLayout(body)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(16)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label("Analysis", "h1"))
        self.subtitle = label("", "muted")
        titles.addWidget(self.subtitle)
        header.addLayout(titles)
        header.addStretch(1)
        header.addWidget(label("Target score", "muted"))
        self.target = QLineEdit()
        self.target.setPlaceholderText("e.g. 1,150,000")
        self.target.setValidator(QIntValidator(0, 99_999_999))
        self.target.setFixedWidth(130)
        self.target.editingFinished.connect(self._target_edited)
        header.addWidget(self.target)
        lay.addLayout(header)

        self.empty = label("No matches yet. Capture a match and it will show up here.", "muted")
        lay.addWidget(self.empty)

        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self.t_week = StatTile("This week's best")
        self.t_played = StatTile("Matches this week")
        self.t_projected = StatTile("Projected weekly best")
        self.t_chance = StatTile("Chance to beat it")
        for t in (self.t_week, self.t_played, self.t_projected, self.t_chance):
            tiles.addWidget(t, 1)
        self.tiles = QWidget()
        self.tiles.setLayout(tiles)
        lay.addWidget(self.tiles)

        self.chart_card, chart_lay = card()
        chart_lay.addWidget(label("Match totals", "h2"))
        self.chart_view = QChartView()
        self.chart_view.setRenderHint(QPainter.Antialiasing)
        self.chart_view.setMinimumHeight(280)
        self.chart_view.setStyleSheet("background: transparent;")
        chart_lay.addWidget(self.chart_view)
        lay.addWidget(self.chart_card)

        self.teams_card, teams_lay = card()
        teams_lay.addWidget(label("Where your weekly best comes from", "h2"))
        self.teams_note = label("", "muted", wrap=True)
        teams_lay.addWidget(self.teams_note)
        self.teams_grid = QGridLayout()
        self.teams_grid.setHorizontalSpacing(12)
        self.teams_grid.setVerticalSpacing(12)
        teams_lay.addLayout(self.teams_grid)
        lay.addWidget(self.teams_card)

        self.matches_card, m_lay = card()
        m_lay.addWidget(label("Recent matches", "h2"))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Played (UTC)", "Total", "Characters", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2):
            hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(3, 90)
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.setMinimumHeight(260)
        m_lay.addWidget(self.table)
        lay.addWidget(self.matches_card)
        lay.addStretch(1)

    def _target_edited(self):
        text = self.target.text().replace(",", "")
        self.target_changed.emit(int(text) if text else 0)

    # ------------------------------------------------------------------

    def refresh(self, report: Report | None, target: int = 0):
        has = report is not None and report.model_matches > 0
        self.empty.setVisible(not has)
        for w in (self.tiles, self.chart_card, self.teams_card, self.matches_card):
            w.setVisible(has)
        if target and not self.target.hasFocus():
            self.target.setText(f"{target}")
        if not has:
            self.subtitle.setText("")
            return
        r = report
        s = r.settings
        self.subtitle.setText(
            f"Week of {r.week_start:%b %d} (resets {r.week_end:%a %b %d, %H:%M} UTC) · "
            f"model from your last {r.model_matches} complete matches"
            + (" · still rough: keep capturing" if r.rough else "")
        )

        if r.week_best:
            delta = ""
            if r.previous_week_best:
                diff = r.week_best - r.previous_week_best
                delta = f"{'+' if diff >= 0 else ''}{diff:,} vs last week ({r.previous_week_best:,})"
            self.t_week.set(f"{r.week_best:,}", delta)
        else:
            self.t_week.set("—", f"Last week: {r.previous_week_best:,}" if r.previous_week_best else "")
        self.t_played.set(f"{r.week_matches} / {s.matches_per_week}", f"{r.remaining} left this week")
        self.t_projected.set(f"{r.projected_best:,.0f}",
                             f"Typical match {r.mean_total:,.0f} ± {r.std_total:,.0f}")
        goal = target or r.week_best
        if goal and r.remaining:
            p = r.p_beat(goal)
            what = "your target" if target else "this week's best"
            color = theme.SUCCESS if p >= 0.6 else theme.WARNING if p >= 0.25 else theme.DANGER
            self.t_chance.caption.setText(f"Chance to beat {what}")
            self.t_chance.set(f"{p:.0%}", f"In the {r.remaining} matches left, if you play them all", color)
        else:
            self.t_chance.caption.setText("Chance to beat it")
            self.t_chance.set("—", "Play a match this week or set a target")

        self._draw_chart(r, target)
        self._draw_teams(r)
        self._fill_table(r)

    def _draw_chart(self, r: Report, target):
        chart = QChart()
        chart.setBackgroundVisible(False)
        chart.setPlotAreaBackgroundVisible(False)
        chart.legend().setLabelColor(QColor(theme.MUTED))
        chart.legend().setAlignment(Qt.AlignBottom)
        chart.setMargins(QMargins(0, 0, 0, 0))

        dots = QScatterSeries()
        dots.setName("Match")
        dots.setMarkerSize(7)
        dots.setColor(QColor(theme.ACCENT))
        dots.setBorderColor(QColor(theme.ACCENT))
        complete = [m for m in r.matches if m.complete]
        for m in complete:
            dots.append(_qdt(m.played_at).toMSecsSinceEpoch(), m.total / 1000)

        weekly = QLineSeries()
        weekly.setName("Weekly best")
        weekly.setPen(QPen(QColor(theme.SUCCESS), 2.2))
        for ws, best, _ in r.weekly_bests:
            start = _qdt(ws).toMSecsSinceEpoch()
            end = _qdt(min(ws + (r.week_end - r.week_start), r.matches[-1].played_at)).toMSecsSinceEpoch()
            weekly.append(start, best / 1000)
            weekly.append(max(end, start + 1), best / 1000)

        x_min = _qdt(complete[0].played_at).toMSecsSinceEpoch() if complete else 0
        x_max = _qdt(complete[-1].played_at).toMSecsSinceEpoch() if complete else 1
        pad = max((x_max - x_min) // 20, 3_600_000)

        def hline(value, name, color, dashed=True):
            series = QLineSeries()
            series.setName(name)
            pen = QPen(QColor(color), 1.6)
            if dashed:
                pen.setStyle(Qt.DashLine)
            series.setPen(pen)
            series.append(x_min - pad, value / 1000)
            series.append(x_max + pad, value / 1000)
            return series

        series = [dots, weekly, hline(r.projected_best, "Projected weekly best", theme.WARNING)]
        if target:
            series.append(hline(target, "Target", theme.DANGER))
        for sr in series:
            chart.addSeries(sr)

        ax = QDateTimeAxis()
        ax.setFormat("MMM d")
        ax.setRange(QDateTime.fromMSecsSinceEpoch(x_min - pad), QDateTime.fromMSecsSinceEpoch(x_max + pad))
        ay = QValueAxis()
        ay.setLabelFormat("%.0fk")
        values = [m.total for m in complete] + [r.projected_best] + ([target] if target else [])
        lo, hi = min(values) / 1000, max(values) / 1000
        span = max(hi - lo, 1)
        ay.setRange(lo - span * 0.1, hi + span * 0.1)
        for axis in (ax, ay):
            axis.setLabelsColor(QColor(theme.MUTED))
            axis.setGridLineColor(QColor(theme.BORDER))
            axis.setLinePenColor(QColor(theme.BORDER))
            font = QFont()
            font.setPointSizeF(8.5)
            axis.setLabelsFont(font)
        chart.addAxis(ax, Qt.AlignBottom)
        chart.addAxis(ay, Qt.AlignLeft)
        for sr in series:
            sr.attachAxis(ax)
            sr.attachAxis(ay)
        self.chart_view.setChart(chart)

    def _draw_teams(self, r: Report):
        clear_layout(self.teams_grid)
        self.teams_note.setText(
            f"Each racer's share of your projected weekly best ({r.projected_best:,.0f}). It's their "
            "average plus a bonus for scoring high in your best matches: with "
            f"{r.settings.matches_per_week} tries a week only your best match counts, so spikes help. "
            "The weakest share in each team is where an upgrade raises your weekly best the most."
        )
        top = max((s.contribution for s in r.characters), default=1) or 1
        for i, t in enumerate(r.teams):
            frame = QFrame()
            frame.setObjectName("slot")
            lay = QVBoxLayout(frame)
            lay.setContentsMargins(12, 10, 12, 10)
            lay.setSpacing(6)
            head = QHBoxLayout()
            head.addWidget(distance_badge(t.distance))
            head.addStretch(1)
            head.addWidget(label(f"{t.contribution:,.0f}", "muted"))
            lay.addLayout(head)
            for s in t.members:
                weakest = s is t.weakest and len(t.members) > 1
                name_line = QHBoxLayout()
                name_line.addWidget(label(s.name))
                name_line.addStretch(1)
                if weakest:
                    tag = label("Upgrade target", "badge")
                    tag.setStyleSheet(f"background: {theme.rgba(theme.WARNING, 0.18)}; color: {theme.WARNING};")
                    name_line.addWidget(tag)
                lay.addLayout(name_line)
                bar = QProgressBar()
                bar.setRange(0, 1000)
                bar.setValue(int(1000 * max(s.contribution, 0) / top))
                bar.setTextVisible(False)
                bar.setFixedHeight(6)
                color = theme.WARNING if weakest else theme.distance_color(t.distance)
                bar.setStyleSheet(f"QProgressBar {{ background: {theme.BG}; border: none; border-radius: 3px; }}"
                                  f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}")
                lay.addWidget(bar)
                lift = f"{'+' if s.top_lift >= 0 else ''}{_k(s.top_lift)}"
                detail = label(f"share {_k(s.contribution)} · avg {_k(s.mean)} · best {_k(s.best)} · "
                               f"in top matches {lift}", "faint", wrap=True)
                detail.setToolTip(
                    f"{s.name}: {s.matches} matches\n"
                    f"Share of projected weekly best: {s.contribution:,.0f}\n"
                    f"Average: {s.mean:,.0f} (spread {s.std:,.0f})\n"
                    f"Best: {s.best:,} · 90th percentile: {s.p90:,.0f}\n"
                    f"In your top 20% matches they score {s.top_lift:+,.0f} vs their average"
                )
                lay.addWidget(detail)
            lay.addStretch(1)
            self.teams_grid.addWidget(frame, i // 3, i % 3)
        for col in range(3):
            self.teams_grid.setColumnStretch(col, 1)

    def _fill_table(self, r: Report):
        matches = list(reversed(r.matches))[:50]
        self.table.setRowCount(len(matches))
        best_ids = {m.match_id for m in r.top_matches[:1]}
        for i, m in enumerate(matches):
            when = QTableWidgetItem(m.played_at.strftime("%a %b %d, %H:%M"))
            total = QTableWidgetItem(f"{m.total:,}")
            total.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if m.match_id in best_ids:
                total.setForeground(QColor(theme.SUCCESS))
            chars = QTableWidgetItem(f"{m.characters}" + ("" if m.complete else " (partial)"))
            if not m.complete:
                chars.setForeground(QColor(theme.WARNING))
            self.table.setItem(i, 0, when)
            self.table.setItem(i, 1, total)
            self.table.setItem(i, 2, chars)
            delete = QPushButton("Delete")
            delete.setObjectName("iconButton")
            delete.clicked.connect(lambda _=False, mid=m.match_id: self.delete_match_requested.emit(mid))
            self.table.setCellWidget(i, 3, delete)
        self.table.resizeRowsToContents()
