"""Average-based statistics over every recorded match.

Every score in the game is base points × (1 + opponent and support bonuses),
so single matches carry opponent noise. Averages over all your matches even
that out, which makes them the stable way to find strong and weak teams and
characters.

Data rules:

- Match totals (the sum of the character scores) use complete matches only:
  partial totals aren't comparable.
- A team's stats use the matches where all three of its members were read.
- A character's stats use every match they appear in.
- Teams come from each score's ``distance`` (who actually ran where). Rows
  saved without one fall back to the character's current team in settings.

Everything here is a pure function of the scores and settings.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from .config import DISTANCES, TEAM_SIZE, Settings

# "Recent form" and rolling averages look at this many matches
RECENT = 10


# --- small helpers -------------------------------------------------------------

def rolling_mean(values, window: int = RECENT) -> list[float]:
    """Trailing average of up to ``window`` values at each point."""
    out, total, buf = [], 0.0, []
    for v in values:
        buf.append(v)
        total += v
        if len(buf) > window:
            total -= buf.pop(0)
        out.append(total / len(buf))
    return out


@dataclass
class Form:
    """Average of the most recent matches compared with the overall average."""

    recent: float
    overall: float
    window: int

    @property
    def delta(self) -> float:
        return self.recent - self.overall

    @property
    def pct(self) -> float:
        return self.delta / self.overall if self.overall else 0.0


def form(values, window: int = RECENT) -> Form | None:
    """Last ``window`` values vs. all of them (oldest first). None if there
    aren't more values than the window, since then they'd be the same."""
    values = list(values)
    if len(values) <= window:
        return None
    recent = values[-window:]
    return Form(sum(recent) / len(recent), sum(values) / len(values), window)


def _std(values) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))


def _median(values) -> float:
    s = sorted(values)
    n = len(s)
    if not n:
        return 0.0
    return float(s[n // 2]) if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


@dataclass
class Spread:
    """Summary of a list of numbers."""

    n: int
    mean: float
    median: float
    best: float
    worst: float
    std: float

    @property
    def cv(self) -> float:
        """Coefficient of variation: spread relative to the average."""
        return self.std / self.mean if self.mean else 0.0

    @property
    def se(self) -> float:
        """Standard error of the mean (how much the average itself may be off)."""
        return self.std / math.sqrt(self.n) if self.n > 1 else 0.0


def spread(values) -> Spread:
    values = list(values)
    if not values:
        return Spread(0, 0.0, 0.0, 0.0, 0.0, 0.0)
    return Spread(len(values), sum(values) / len(values), _median(values),
                  max(values), min(values), _std(values))


# --- results --------------------------------------------------------------------

@dataclass
class Match:
    match_id: int
    played_at: datetime  # local time, as saved
    total: int
    characters: int
    complete: bool


@dataclass
class Overview:
    matches: int
    complete: int
    partial: int
    totals: Spread  # complete match totals
    best: Match | None
    worst: Match | None
    form: Form | None


@dataclass
class MemberStats:
    """A character's results within one team."""

    name: str
    matches: int  # team-complete matches they ran in this team
    mean: float
    share: float  # average share of the team total
    current: bool  # on this team in the current settings


@dataclass
class TeamStats:
    distance: str
    totals: Spread  # team totals over the matches where the team was complete
    share_of_match: float  # average share of the match total (complete matches)
    rank: int  # 1 = strongest of the teams
    form: Form | None
    members: list  # MemberStats, highest average first
    top: MemberStats | None
    weakest: MemberStats | None
    history: list = field(default_factory=list)  # (played_at, total), oldest first

    @property
    def per_member(self) -> float:
        return self.totals.mean / TEAM_SIZE

    @property
    def weakest_gap(self) -> float:
        """How far the weakest member is below the team's per-member average."""
        return self.weakest.mean - self.per_member if self.weakest else 0.0


@dataclass
class TeamPart:
    """A character's results in one particular team (for movers)."""

    distance: str
    matches: int
    mean: float


@dataclass
class CharacterStats:
    name: str
    team: str  # current team, else the team they last ran in
    scores: Spread
    share_of_team: float | None  # average share of their team's total
    rank_in_team: float | None  # average rank among teammates (1..3)
    rank_in_match: float | None  # average rank in complete matches (1..15)
    top_of_team: float | None  # fraction of matches as the team's top scorer
    top_of_match: float | None  # fraction of complete matches as the top scorer
    above_team_avg: float | None  # average score minus their team's per-member average
    form: Form | None
    by_team: list  # TeamPart per distance they ran, most matches first
    history: list = field(default_factory=list)  # (match_id, played_at, score, distance)
    best_match: tuple | None = None  # (played_at, score)
    worst_match: tuple | None = None


@dataclass
class Analysis:
    matches: list  # Match, oldest first
    overview: Overview
    teams: list  # TeamStats, in DISTANCES order (teams with data only)
    characters: list  # CharacterStats, highest average first
    match_size: int  # characters in a complete match

    @property
    def complete_matches(self) -> list:
        return [m for m in self.matches if m.complete]


# --- computation -------------------------------------------------------------------

def prepare(scores: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    """Clean copy with parsed times and every row's distance filled in."""
    df = scores.copy()
    df["played_at"] = pd.to_datetime(df["timestamp"], errors="coerce", format="mixed")
    df = df.dropna(subset=["played_at"])
    distance = df["distance"].fillna("").astype(str) if "distance" in df else pd.Series("", index=df.index)
    fallback = df["character"].map(lambda n: settings.teams.get(n, ""))
    df["distance"] = distance.where(distance != "", fallback)
    df["score"] = df["score"].astype("int64")
    return df.sort_values(["played_at", "match_id"], kind="stable").reset_index(drop=True)


def match_size(df: pd.DataFrame, settings: Settings) -> int:
    """How many characters a complete match has."""
    if settings.teams:
        return len(settings.teams)
    if settings.roster:
        return len(settings.roster)
    return int(df.groupby("match_id").size().max()) if not df.empty else 0


def analyze(scores: pd.DataFrame, settings: Settings) -> Analysis | None:
    """All the stats the Analysis page shows. None without data."""
    if scores is None or scores.empty:
        return None
    df = prepare(scores, settings)
    if df.empty:
        return None

    size = match_size(df, settings)
    per_match = (df.groupby("match_id", sort=False)
                 .agg(total=("score", "sum"), n=("score", "size"), played_at=("played_at", "first")))
    matches = [Match(int(mid), r.played_at.to_pydatetime(), int(r.total), int(r.n), int(r.n) >= size)
               for mid, r in per_match.iterrows()]
    complete_ids = {m.match_id for m in matches if m.complete}
    match_total = {m.match_id: m.total for m in matches}
    order = {m.match_id: i for i, m in enumerate(matches)}

    # Overview
    complete = [m for m in matches if m.complete]
    totals = [m.total for m in complete]
    overview = Overview(
        matches=len(matches),
        complete=len(complete),
        partial=len(matches) - len(complete),
        totals=spread(totals),
        best=max(complete, key=lambda m: m.total) if complete else None,
        worst=min(complete, key=lambda m: m.total) if complete else None,
        form=form(totals),
    )

    # Team totals per match, for teams with all members present
    team_rows = df[df["distance"] != ""]
    grouped = team_rows.groupby(["match_id", "distance"])["score"]
    team_match = pd.DataFrame({"total": grouped.sum(), "n": grouped.size()}).reset_index()
    team_match = team_match[team_match["n"] >= TEAM_SIZE]
    team_match["order"] = team_match["match_id"].map(order)
    team_match = team_match.sort_values("order")
    team_total = {(r.match_id, r.distance): r.total for r in team_match.itertuples()}

    # Per-row context: rank within team and match, share of team total
    df = df.copy()
    df["team_total"] = [team_total.get((m, d)) for m, d in zip(df["match_id"], df["distance"])]
    df["team_rank"] = df.groupby(["match_id", "distance"])["score"].rank(ascending=False, method="min")
    df["match_rank"] = df.groupby("match_id")["score"].rank(ascending=False, method="min")
    df["in_complete_team"] = df["team_total"].notna()
    df["in_complete_match"] = df["match_id"].isin(complete_ids)

    teams = _team_stats(df, team_match, match_total, complete_ids, settings)
    per_member_avg = {t.distance: t.per_member for t in teams}
    characters = _character_stats(df, settings, per_member_avg)
    return Analysis(matches=matches, overview=overview, teams=teams, characters=characters, match_size=size)


def _team_stats(df, team_match, match_total, complete_ids, settings) -> list:
    teams = []
    played_at = df.drop_duplicates("match_id").set_index("match_id")["played_at"]
    for d in DISTANCES:
        tm = team_match[team_match["distance"] == d]
        if tm.empty:
            continue
        values = tm["total"].tolist()
        shares = [t / match_total[m] for m, t in zip(tm["match_id"], tm["total"])
                  if m in complete_ids and match_total[m]]
        rows = df[(df["distance"] == d) & df["in_complete_team"]]
        current = set(settings.team_members(d))
        members = []
        for name, g in rows.groupby("character"):
            members.append(MemberStats(
                name=name,
                matches=len(g),
                mean=float(g["score"].mean()),
                share=float((g["score"] / g["team_total"]).mean()),
                current=name in current or not current,
            ))
        members.sort(key=lambda m: m.mean, reverse=True)
        ranked = [m for m in members if m.current] or members
        teams.append(TeamStats(
            distance=d,
            totals=spread(values),
            share_of_match=sum(shares) / len(shares) if shares else 0.0,
            rank=0,
            form=form(values),
            members=members,
            top=ranked[0] if len(ranked) > 1 else None,
            weakest=ranked[-1] if len(ranked) > 1 else None,
            history=[(played_at[m].to_pydatetime(), int(t)) for m, t in zip(tm["match_id"], tm["total"])],
        ))
    for rank, t in enumerate(sorted(teams, key=lambda t: t.totals.mean, reverse=True), start=1):
        t.rank = rank
    return teams


def _character_stats(df, settings, per_member_avg) -> list:
    out = []
    for name, g in df.groupby("character"):
        values = g["score"].tolist()
        in_team = g[g["in_complete_team"]]
        in_match = g[g["in_complete_match"]]
        parts = [TeamPart(d, len(p), float(p["score"].mean())) for d, p in g.groupby("distance")]
        parts.sort(key=lambda p: p.matches, reverse=True)
        team = settings.teams.get(name) or g["distance"].iloc[-1]
        gaps = [s - per_member_avg[d] for s, d in zip(g["score"], g["distance"]) if d in per_member_avg]
        best_i, worst_i = g["score"].idxmax(), g["score"].idxmin()

        def frac(mask):
            return float(mask.mean()) if len(mask) else None

        out.append(CharacterStats(
            name=name,
            team=team,
            scores=spread(values),
            share_of_team=float((in_team["score"] / in_team["team_total"]).mean()) if len(in_team) else None,
            rank_in_team=float(in_team["team_rank"].mean()) if len(in_team) else None,
            rank_in_match=float(in_match["match_rank"].mean()) if len(in_match) else None,
            top_of_team=frac(in_team["team_rank"] == 1),
            top_of_match=frac(in_match["match_rank"] == 1),
            above_team_avg=sum(gaps) / len(gaps) if gaps else None,
            form=form(values),
            by_team=parts,
            history=[(int(m), t.to_pydatetime(), int(s), d)
                     for m, t, s, d in zip(g["match_id"], g["played_at"], g["score"], g["distance"])],
            best_match=(g.at[best_i, "played_at"].to_pydatetime(), int(g.at[best_i, "score"])),
            worst_match=(g.at[worst_i, "played_at"].to_pydatetime(), int(g.at[worst_i, "score"])),
        ))
    out.sort(key=lambda c: c.scores.mean, reverse=True)
    return out
