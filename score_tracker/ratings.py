"""Rating model: how a character's rating feeds into every score.

Every score = base points × (1 + bonus), and the bonus grows with the
opponent's rating. Matchmaking pairs similar ratings, so on average:

    bonus(R) = k × R        R = your team rating, k ≈ 0.5% per 1k (prior)

Raising one character's rating therefore raises all 15 scores a little:

    d(match total) / dR ≈ T × k / (1 + bonus(R))       ("marginal value")

A character's **Value** is their average score plus what their rating adds to
the rest of the team, relative to a character at the lineup's average rating:

    Value = average + marginal × (effective rating − lineup average)

Effective rating = rating × (1 + s_bonus × number of S aptitudes). Grades
below A are stored but treated as A.

Everything here is a pure function.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from .config import DISTANCES, Settings
from .lineups import Build, Lineup, Roster

Z95 = 1.96


# --- the maths ---------------------------------------------------------------------

def effective_rating(build: Build | None, s_bonus: float) -> float | None:
    if build is None or build.rating is None:
        return None
    return build.rating * (1 + s_bonus * build.s_count)


def k_per_point(per_1k_pct: float) -> float:
    """Bonus fraction per rating point, from percentage points per 1k."""
    return per_1k_pct / 100 / 1000


def bonus(rating: float, per_1k_pct: float) -> float:
    """Score bonus over base (1.72 = +172%) at a team rating."""
    return k_per_point(per_1k_pct) * rating


def base_score(score: float, rating: float, per_1k_pct: float) -> float:
    """A score with the rating bonus taken out, to compare across rating changes."""
    return score / (1 + bonus(rating, per_1k_pct))


def marginal_per_point(match_total: float, rating: float, per_1k_pct: float) -> float:
    """Match-total points gained per point of team rating."""
    return match_total * k_per_point(per_1k_pct) / (1 + bonus(rating, per_1k_pct))


def value(average: float, eff: float | None, mean_eff: float | None, marginal: float | None) -> float:
    if eff is None or mean_eff is None or marginal is None:
        return average
    return average + marginal * (eff - mean_eff)


def break_even(average: float, eff_old: float, eff_new: float, marginal: float) -> float:
    """Average score a replacement with ``eff_new`` needs to keep the match total the same."""
    return average - marginal * (eff_new - eff_old)


def what_if(match_total: float, rating: float, per_1k_pct: float, slot_average: float,
            eff_old: float, eff_new: float, expected: float | None = None) -> tuple[float, float]:
    """Swap one slot's rating and score. Returns (projected match total, expected score used).

    Everyone else's scores scale with (1 + bonus); the default expected score
    is the slot's base score at the new rating.
    """
    b_old = bonus(rating, per_1k_pct)
    b_new = bonus(rating - eff_old + eff_new, per_1k_pct)
    scale = (1 + b_new) / (1 + b_old)
    if expected is None:
        expected = slot_average * scale
    return (match_total - slot_average) * scale + expected, expected


# --- lineup ratings ----------------------------------------------------------------

@dataclass
class LineupRating:
    lineup: Lineup
    computed: float | None  # sum of effective ratings (unrated members count as the average)
    rated: int  # members with a rating
    members: int
    mean_eff: float | None  # average effective rating of rated members
    team_eff: dict = field(default_factory=dict)  # distance -> sum of effective ratings (None if unrated)

    @property
    def displayed(self) -> int | None:
        return self.lineup.displayed_rating

    @property
    def rating(self) -> float | None:
        """R for the bonus: the displayed team rating if entered, else the computed sum."""
        return float(self.displayed) if self.displayed else self.computed


def lineup_rating(roster: Roster, lineup: Lineup, s_bonus: float) -> LineupRating:
    members = roster.members(lineup)
    effs = [effective_rating(b, s_bonus) for _, b in members]
    rated = [e for e in effs if e is not None]
    mean = sum(rated) / len(rated) if rated else None
    computed = sum(e if e is not None else mean for e in effs) if rated else None
    team_eff = {}
    for d in DISTANCES:
        team = [effective_rating(b, s_bonus) for dist, b in members if dist == d]
        team_eff[d] = sum(e if e is not None else mean for e in team) if team and mean is not None else None
    return LineupRating(lineup, computed, len(rated), len(members), mean, team_eff)


# --- fitting k from data ------------------------------------------------------------

@dataclass
class Fit:
    per_1k: float  # fitted percentage points per 1k
    se: float  # its standard error
    matches: int
    lineups: int


MIN_FIT_MATCHES = 3  # complete matches per lineup


def fit_bonus(points) -> Fit | None:
    """Fit k from (lineup id, rating R, match total) of complete matches.

    log(T) = log(base) + log(1 + kR); regressing log T on R gives a slope
    β ≈ k / (1 + kR̄), so k = β / (1 − βR̄). Needs at least two lineups with
    different ratings and ``MIN_FIT_MATCHES`` matches each.
    """
    points = [(l, r, t) for l, r, t in points if r and t > 0]
    counts = {}
    for l, r, _ in points:
        counts.setdefault((l, r), 0)
        counts[(l, r)] += 1
    usable = {key for key, n in counts.items() if n >= MIN_FIT_MATCHES}
    points = [(l, r, t) for l, r, t in points if (l, r) in usable]
    if len({r for _, r, _ in points}) < 2:
        return None
    xs = [r for _, r, _ in points]
    ys = [math.log(t) for _, _, t in points]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0 or n < 3:
        return None
    beta = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    resid = [y - (my + beta * (x - mx)) for x, y in zip(xs, ys)]
    se_beta = math.sqrt(sum(e * e for e in resid) / (n - 2) / sxx)
    denom = 1 - beta * mx
    if denom <= 0.05:
        return None
    k = beta / denom
    dk = 1 / denom ** 2  # dk/dβ
    return Fit(per_1k=k * 1000 * 100, se=abs(dk) * se_beta * 1000 * 100, matches=n,
               lineups=len({l for l, _, _ in points}))


# --- comparing two samples ----------------------------------------------------------

@dataclass
class Diff:
    a: float
    b: float
    n_a: int
    n_b: int
    se: float

    @property
    def delta(self) -> float:
        return self.b - self.a

    @property
    def pct(self) -> float:
        return self.delta / self.a if self.a else 0.0

    @property
    def low(self) -> float:
        return self.delta - Z95 * self.se

    @property
    def high(self) -> float:
        return self.delta + Z95 * self.se

    @property
    def significant(self) -> bool:
        return self.se > 0 and (self.low > 0 or self.high < 0)

    def needed(self) -> int | None:
        """Roughly how many matches per lineup make this difference stand out."""
        if not self.delta or self.se <= 0:
            return None
        # se scales as sd·sqrt(1/n_a + 1/n_b); find n with Z95·se(n) = |delta|
        sd2 = self.se ** 2 / (1 / self.n_a + 1 / self.n_b)
        return math.ceil(2 * sd2 * (Z95 / abs(self.delta)) ** 2)


def diff(a_values, b_values) -> Diff | None:
    a, b = list(a_values), list(b_values)
    if not a or not b:
        return None
    ma, mb = sum(a) / len(a), sum(b) / len(b)

    def var(v, m):
        return sum((x - m) ** 2 for x in v) / (len(v) - 1) if len(v) > 1 else 0.0

    se = math.sqrt(var(a, ma) / len(a) + var(b, mb) / len(b))
    return Diff(ma, mb, len(a), len(b), se)


# --- the analysis --------------------------------------------------------------------

@dataclass
class SlotValue:
    """One slot of the reference lineup."""

    distance: str
    build: Build
    matches: int
    average: float | None  # in the analysed matches
    base: float | None  # rating-neutral average
    eff: float | None  # effective rating (None if unrated)
    value: float | None

    @property
    def name(self) -> str:
        return self.build.character


@dataclass
class LineupCompare:
    a: Lineup
    b: Lineup
    raw: Diff | None
    adjusted: Diff | None  # rating-neutral match totals
    teams: dict  # distance -> Diff of team totals
    slots: list  # (distance, index, build a, build b, Diff of character scores)


@dataclass
class RatingAnalysis:
    per_1k: float  # the k in use (prior or fitted)
    prior: float
    fit: Fit | None
    using_fit: bool
    reference: LineupRating  # the lineup Value is computed for
    lineup_ratings: dict  # lineup id -> LineupRating
    match_total: float | None  # average complete match total of the analysed matches
    bonus: float | None  # at the reference rating
    marginal: float | None  # per rating point
    slots: list  # SlotValue, reference lineup order
    by_name: dict  # character -> SlotValue (reference lineup)
    base_by_name: dict  # character -> rating-neutral average over the analysed matches
    frame: object = None  # prepared rows of every lineup, for comparisons
    match_size: int = 0

    @property
    def marginal_per_1k(self) -> float | None:
        return self.marginal * 1000 if self.marginal is not None else None

    def replace_first(self, n=3) -> list:
        ranked = [s for s in self.slots if s.value is not None]
        return sorted(ranked, key=lambda s: s.value)[:n]

    def weakest_by_value(self, distance) -> SlotValue | None:
        team = [s for s in self.slots if s.distance == distance and s.value is not None]
        return min(team, key=lambda s: s.value) if len(team) > 1 else None


def match_ratings(df: pd.DataFrame, ratings: dict) -> dict:
    """match_id -> team rating R of the lineup it was played with (None if unknown)."""
    first = df.drop_duplicates("match_id").set_index("match_id")["lineup"]
    return {int(m): (ratings[l].rating if l in ratings else None) for m, l in first.items()}


def rate(df: pd.DataFrame, roster: Roster, settings: Settings, reference: Lineup, match_size: int,
         all_df: pd.DataFrame | None = None) -> RatingAnalysis:
    """Rating stats for prepared scores ``df`` (with a resolved ``lineup`` column).

    ``all_df`` (every lineup's matches) is used to fit k; defaults to ``df``.
    """
    s_bonus = settings.s_aptitude_bonus
    ratings = {l.id: lineup_rating(roster, l, s_bonus) for l in roster.lineups}
    all_df = df if all_df is None else all_df

    totals = all_df.groupby("match_id").agg(total=("score", "sum"), n=("score", "size"),
                                            lineup=("lineup", "first"))
    complete_all = totals[totals["n"] >= match_size]
    fit = fit_bonus([(r.lineup, ratings[r.lineup].rating if r.lineup in ratings else None, r.total)
                     for r in complete_all.itertuples()])
    using_fit = bool(settings.use_fitted_bonus and fit and fit.per_1k > 0)
    k = fit.per_1k if using_fit else settings.rating_bonus_per_1k

    ref = ratings[reference.id]
    here = totals.loc[totals.index.isin(df["match_id"].unique())]
    complete = here[here["n"] >= match_size]
    T = float(complete["total"].mean()) if len(complete) else None
    R = ref.rating
    marginal = marginal_per_point(T, R, k) if T and R else None

    # Rating-neutral scores, per character, over the analysed matches
    by_match = match_ratings(df, ratings)
    r_row = df["match_id"].map(by_match)
    known = r_row.notna()
    base_by_name = {}
    if known.any():
        sub = df[known].assign(base=[base_score(s, r, k) for s, r in zip(df.loc[known, "score"], r_row[known])])
        base_by_name = sub.groupby("character")["base"].mean().to_dict()

    slots = []
    for d, b in roster.members(reference):
        g = df[df["character"] == b.character]
        avg = float(g["score"].mean()) if len(g) else None
        eff = effective_rating(b, s_bonus)
        slots.append(SlotValue(
            distance=d, build=b, matches=len(g), average=avg,
            base=base_by_name.get(b.character),
            eff=eff,
            value=value(avg, eff, ref.mean_eff, marginal) if avg is not None else None,
        ))
    return RatingAnalysis(
        per_1k=k, prior=settings.rating_bonus_per_1k, fit=fit, using_fit=using_fit,
        reference=ref, lineup_ratings=ratings, match_total=T,
        bonus=bonus(R, k) if R else None, marginal=marginal,
        slots=slots, by_name={s.name: s for s in slots}, base_by_name=base_by_name,
        frame=all_df, match_size=match_size,
    )


def compare_lineups(df: pd.DataFrame, roster: Roster, a: Lineup, b: Lineup, per_1k: float,
                    s_bonus: float, match_size: int) -> LineupCompare:
    """Lineup B minus lineup A: match totals (raw and rating-neutral), teams and slots."""
    ra, rb = lineup_rating(roster, a, s_bonus).rating, lineup_rating(roster, b, s_bonus).rating
    totals = df.groupby("match_id").agg(total=("score", "sum"), n=("score", "size"), lineup=("lineup", "first"))
    complete = totals[totals["n"] >= match_size]
    ta = complete[complete["lineup"] == a.id]["total"].tolist()
    tb = complete[complete["lineup"] == b.id]["total"].tolist()
    raw = diff(ta, tb)
    adjusted = None
    if ra and rb:
        adjusted = diff([base_score(t, ra, per_1k) for t in ta], [base_score(t, rb, per_1k) for t in tb])

    teams = {}
    for d in DISTANCES:
        def team_totals(lineup):
            rows = df[(df["lineup"] == lineup.id) & (df["distance"] == d)]
            g = rows.groupby("match_id")["score"]
            t = pd.DataFrame({"total": g.sum(), "n": g.size()})
            return t[t["n"] >= 3]["total"].tolist()
        dd = diff(team_totals(a), team_totals(b))
        if dd:
            teams[d] = dd

    slots = []
    for d in DISTANCES:
        sa, sb = a.slots.get(d, []), b.slots.get(d, [])
        for i in range(max(len(sa), len(sb))):
            ba = roster.builds.get(sa[i]) if i < len(sa) else None
            bb = roster.builds.get(sb[i]) if i < len(sb) else None

            def scores(lineup, build):
                if build is None:
                    return []
                return df[(df["lineup"] == lineup.id) & (df["character"] == build.character)]["score"].tolist()
            slots.append((d, i, ba, bb, diff(scores(a, ba), scores(b, bb))))
    return LineupCompare(a, b, raw, adjusted, teams, slots)
