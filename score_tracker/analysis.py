"""Analysis aimed at one goal: the highest single match total each week.

Your class each week is decided by your best match, so what matters is not
how steady a team is but how high it can peak in ~35 attempts:

- If a match total T has mean μ and spread σ, the best of n matches is
  expected to land around μ + c(n)·σ, where c(n) is the expected maximum of
  n standard normal draws (c(35) ≈ 2.1). Spread is good here.
- Each character's share of that projected best is
  μᵢ + c(n)·cov(xᵢ, T)/σ, which sums exactly to μ + c(n)·σ. A character who
  scores big in your big matches counts for more than their average alone.
- The weakest share in a team is where an upgrade raises your weekly best
  the most.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from .config import DISTANCES, Settings

# How many recent complete matches the model learns from
MODEL_WINDOW = 60
# Fewer complete matches than this and estimates are flagged as rough
MIN_MATCHES = 8


def expected_max_z(n: int) -> float:
    """E[max of n iid standard normals]."""
    if n <= 1:
        return 0.0
    x = np.linspace(-8, 8, 4001)
    pdf = np.exp(-x * x / 2) / math.sqrt(2 * math.pi)
    cdf = 0.5 * (1 + np.vectorize(math.erf)(x / math.sqrt(2)))
    return float(np.trapezoid(x * n * pdf * cdf ** (n - 1), x)) if hasattr(np, "trapezoid") \
        else float(np.trapz(x * n * pdf * cdf ** (n - 1), x))


def _norm_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def prob_at_least_one_above(target, mu, sigma, n) -> float:
    """P(max of n matches > target) under a normal model of match totals."""
    if n <= 0:
        return 0.0
    if sigma <= 0:
        return 1.0 if mu > target else 0.0
    return 1 - _norm_cdf((target - mu) / sigma) ** n


def week_start(ts_utc: datetime, settings: Settings) -> datetime:
    """Start (UTC) of the Team Trials week containing ts_utc."""
    day = ts_utc.replace(hour=settings.week_reset_hour_utc, minute=0, second=0, microsecond=0)
    day -= timedelta(days=(day.weekday() - settings.week_reset_weekday) % 7)
    if day > ts_utc:
        day -= timedelta(days=7)
    return day


def _to_utc(timestamps: pd.Series) -> pd.Series:
    """Saved local timestamps → UTC."""
    local = pd.to_datetime(timestamps, errors="coerce", format="mixed")
    tz = datetime.now().astimezone().tzinfo
    return local.dt.tz_localize(tz, ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")


@dataclass
class Match:
    match_id: int
    played_at: datetime  # UTC
    total: int
    characters: int
    complete: bool


@dataclass
class CharacterStats:
    name: str
    distance: str
    matches: int
    mean: float
    best: int
    p90: float
    std: float
    contribution: float  # share of the projected weekly best
    top_lift: float  # how much more they score in your best matches
    recent: list = field(default_factory=list)  # (played_at, score), oldest first


@dataclass
class TeamStats:
    distance: str
    members: list  # CharacterStats, best contribution first
    mean_total: float
    contribution: float
    weakest: CharacterStats | None
    gap_to_best: float  # weakest member's share vs. the team's best member


@dataclass
class Report:
    settings: Settings
    matches: list  # Match, oldest first
    model_matches: int
    mean_total: float
    std_total: float
    c: float  # expected-max factor for matches_per_week
    projected_best: float
    week_start: datetime
    week_end: datetime
    week_matches: int
    week_best: int | None
    week_best_match: Match | None
    previous_week_best: int | None
    weekly_bests: list  # (week_start, best, matches)
    characters: list  # CharacterStats, best contribution first
    teams: list  # TeamStats in DISTANCES order
    top_matches: list  # Match, best first

    @property
    def remaining(self) -> int:
        return max(0, self.settings.matches_per_week - self.week_matches)

    @property
    def rough(self) -> bool:
        return self.model_matches < MIN_MATCHES

    def p_beat(self, target, n=None) -> float:
        n = self.remaining if n is None else n
        return prob_at_least_one_above(target, self.mean_total, self.std_total, n)

    @property
    def p_beat_week_best(self) -> float | None:
        if self.week_best is None:
            return None
        return self.p_beat(self.week_best)


def build_report(scores: pd.DataFrame, settings: Settings, now: datetime | None = None) -> Report | None:
    """Everything the analysis window and CLI show. None without data."""
    if scores.empty:
        return None
    now = now or datetime.now(timezone.utc)
    df = scores.copy()
    df["played_at"] = _to_utc(df["timestamp"])
    df = df.dropna(subset=["played_at"])
    if df.empty:
        return None

    roster = list(settings.roster) or sorted(df["character"].unique())
    full_size = len(roster)
    per_match = df.groupby("match_id").agg(total=("score", "sum"), n=("score", "size"),
                                           played_at=("played_at", "first"))
    per_match = per_match.sort_values("played_at")
    matches = [Match(int(i), r.played_at.to_pydatetime(), int(r.total), int(r.n), int(r.n) >= full_size)
               for i, r in per_match.iterrows()]

    # Weekly bests (complete matches only: partial totals aren't comparable)
    complete_ids = [m.match_id for m in matches if m.complete]
    weeks = {}
    for m in matches:
        if not m.complete:
            continue
        ws = week_start(m.played_at, settings)
        best, count, bm = weeks.get(ws, (0, 0, None))
        weeks[ws] = (max(best, m.total), count + 1, m if m.total > best else bm)
    this_week = week_start(now, settings)
    played_this_week = sum(1 for m in matches if week_start(m.played_at, settings) == this_week)
    wb = weeks.get(this_week)
    prev = weeks.get(this_week - timedelta(days=7))

    # Model: recent complete matches
    model_ids = complete_ids[-MODEL_WINDOW:]
    wide = df[df["match_id"].isin(model_ids)].pivot_table(
        index="match_id", columns="character", values="score", aggfunc="last")
    wide = wide.reindex(columns=[c for c in roster if c in wide.columns])
    totals = wide.sum(axis=1)
    mu = float(totals.mean()) if len(totals) else 0.0
    sigma = float(totals.std(ddof=1)) if len(totals) > 1 else 0.0
    c = expected_max_z(settings.matches_per_week)

    top_cut = totals.quantile(0.8) if len(totals) >= 5 else (totals.max() if len(totals) else 0)
    top_ids = totals[totals >= top_cut].index
    latest_distance = (df.sort_values("played_at").groupby("character")["distance"].last())

    characters = []
    for name in wide.columns:
        x = wide[name]
        cov = float(np.cov(x, totals, ddof=1)[0, 1]) if len(x) > 1 else 0.0
        hist = df[df["character"] == name].sort_values("played_at")
        all_scores = hist["score"]
        distance = settings.teams.get(name) or (latest_distance.get(name) or "")
        characters.append(CharacterStats(
            name=name,
            distance=distance,
            matches=int(all_scores.size),
            mean=float(x.mean()),
            best=int(all_scores.max()),
            p90=float(x.quantile(0.9)),
            std=float(x.std(ddof=1)) if len(x) > 1 else 0.0,
            contribution=float(x.mean() + (c * cov / sigma if sigma > 0 else 0.0)),
            top_lift=float(x.loc[top_ids].mean() - x.mean()) if len(top_ids) else 0.0,
            recent=[(t.to_pydatetime(), int(s)) for t, s in zip(hist["played_at"], hist["score"])],
        ))
    characters.sort(key=lambda s: s.contribution, reverse=True)

    teams = []
    for d in (*DISTANCES, ""):
        members = [s for s in characters if s.distance == d]
        if not members:
            continue
        weakest = min(members, key=lambda s: s.contribution)
        best = max(members, key=lambda s: s.contribution)
        teams.append(TeamStats(
            distance=d,
            members=members,
            mean_total=sum(s.mean for s in members),
            contribution=sum(s.contribution for s in members),
            weakest=weakest,
            gap_to_best=best.contribution - weakest.contribution,
        ))

    by_id = {m.match_id: m for m in matches}
    return Report(
        settings=settings,
        matches=matches,
        model_matches=len(totals),
        mean_total=mu,
        std_total=sigma,
        c=c,
        projected_best=mu + c * sigma,
        week_start=this_week,
        week_end=this_week + timedelta(days=7),
        week_matches=played_this_week,
        week_best=wb[0] if wb else None,
        week_best_match=wb[2] if wb else None,
        previous_week_best=prev[0] if prev else None,
        weekly_bests=sorted((ws, b, n) for ws, (b, n, _) in weeks.items()),
        characters=characters,
        teams=teams,
        top_matches=sorted((by_id[i] for i in complete_ids), key=lambda m: m.total, reverse=True)[:5],
    )


def format_report(scores: pd.DataFrame, settings: Settings, now=None) -> str:
    """Plain-text version of the analysis (for the command line)."""
    r = build_report(scores, settings, now)
    if r is None:
        return "No match data found."
    lines = ["=" * 72, "WEEKLY TOP SCORE REPORT", "=" * 72]
    if r.rough:
        lines.append(f"(Only {r.model_matches} complete matches so far: estimates are rough.)")
    lines.append(f"This week: {r.week_matches}/{r.settings.matches_per_week} matches played, "
                 f"best {r.week_best:,}" if r.week_best else
                 f"This week: {r.week_matches}/{r.settings.matches_per_week} matches played, no complete match yet")
    if r.previous_week_best:
        lines.append(f"Last week's best: {r.previous_week_best:,}")
    lines.append(f"Typical match: {r.mean_total:,.0f} ± {r.std_total:,.0f}")
    lines.append(f"Projected best of {r.settings.matches_per_week} matches: {r.projected_best:,.0f}")
    if r.week_best and r.remaining:
        lines.append(f"Chance to beat this week's best in the {r.remaining} matches left: "
                     f"{r.p_beat_week_best:.0%}")
    lines.append("")
    lines.append("Share of projected weekly best, by team (weakest member flagged):")
    for t in r.teams:
        lines.append(f"  {t.distance or 'No team':7s} {t.contribution:>9,.0f}")
        for s in t.members:
            flag = "  <- upgrade target" if s is t.weakest and len(t.members) > 1 else ""
            lines.append(f"    {s.name:20s} share {s.contribution:>8,.0f}  avg {s.mean:>8,.0f}  "
                         f"best {s.best:>8,}  in top matches {s.top_lift:+,.0f}{flag}")
    lines.append("")
    lines.append("Your best matches:")
    for m in r.top_matches:
        lines.append(f"  {m.played_at:%Y-%m-%d %H:%M} UTC  {m.total:,}")
    lines.append("=" * 72)
    return "\n".join(lines)
