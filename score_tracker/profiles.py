"""Why a character is weak or strong: their score profile compared with their peers.

For each character of the lineup being analysed:

- **vs the match average**: every match, their score minus that match's
  average per character. The mean of those differences (with a 95% range)
  says whether they're really below or above the rest, or it's still noise.
  The share of matches they beat it is their **hit rate**.
- **Ceiling** (best), **floor** (worst), **median** and **consistency** (CV),
  each ranked among the lineup's characters (#1 = best).
- **% of best**: their average as a share of their best. High = they play
  near their ceiling, so the ceiling is the problem; low = their best is
  rare.
- **Rating**: their effective rating against the lineup average, and what
  the difference is worth per match (from ratings.py).

From those, an archetype (headline) and a few plain-language reasons are
picked. Everything here is a pure function.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .analysis import Analysis, CharacterStats

Z95 = 1.96


@dataclass
class Profile:
    name: str
    team: str
    matches: int
    mean: float
    median: float
    best: float
    worst: float
    std: float
    cv: float
    vs_field: float  # average of (score − that match's per-character average)
    vs_field_se: float
    hit_rate: float  # share of matches above the match average
    hits: int
    of_best: float  # mean / best
    peers: int
    rank_mean: int  # 1 = highest
    rank_best: int
    rank_worst: int  # 1 = highest floor
    rank_cv: int  # 1 = steadiest
    form_pct: float | None
    vs_team: float | None  # vs their team's per-member average
    value: float | None = None
    eff: float | None = None
    rating_gap: float | None = None  # effective rating − lineup average
    rating_worth: float | None = None  # what that gap is worth per match
    archetype: str = ""
    reasons: list = field(default_factory=list)  # (text, sentiment: +1 good / −1 bad / 0)

    @property
    def low(self) -> float:
        return self.vs_field - Z95 * self.vs_field_se

    @property
    def high(self) -> float:
        return self.vs_field + Z95 * self.vs_field_se

    @property
    def clearly_below(self) -> bool:
        return self.vs_field_se > 0 and self.high < 0

    @property
    def clearly_above(self) -> bool:
        return self.vs_field_se > 0 and self.low > 0

    def third(self, rank) -> str:
        """'top', 'middle' or 'bottom' third of the peers for a rank."""
        if self.peers < 3:
            return "middle"
        cut = self.peers / 3
        return "top" if rank <= cut else "bottom" if rank > self.peers - cut else "middle"


def _rank(values: dict, name, higher_is_better=True) -> int:
    ordered = sorted(values, key=lambda n: values[n], reverse=higher_is_better)
    return ordered.index(name) + 1


def _ord(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _k(v) -> str:
    return f"{v / 1000:.1f}k"


def _signed_k(v) -> str:
    return f"{'+' if v >= 0 else '−'}{abs(v) / 1000:.1f}k"


def profiles(a: Analysis, names=None) -> list[Profile]:
    """Profiles of ``names`` (default: the lineup's characters, else everyone with a team)."""
    ra = a.ratings
    if names is None:
        names = [s.name for s in ra.slots] if ra and ra.slots else [c.name for c in a.characters if c.team]
    chars = {c.name: c for c in a.characters if c.name in set(names) and c.scores.n}
    if not chars:
        return []
    field_mean = {m.match_id: m.total / m.characters for m in a.matches if m.characters}

    means = {n: c.scores.mean for n, c in chars.items()}
    bests = {n: c.scores.best for n, c in chars.items()}
    worsts = {n: c.scores.worst for n, c in chars.items()}
    cvs = {n: c.scores.cv for n, c in chars.items()}
    out = []
    for name, c in chars.items():
        diffs = [score - field_mean[mid] for mid, _, score, _ in c.history if mid in field_mean]
        n = len(diffs)
        mean_diff = sum(diffs) / n if n else 0.0
        sd = math.sqrt(sum((d - mean_diff) ** 2 for d in diffs) / (n - 1)) if n > 1 else 0.0
        hits = sum(d > 0 for d in diffs)
        s = c.scores
        p = Profile(
            name=name, team=c.team, matches=s.n, mean=s.mean, median=s.median, best=s.best, worst=s.worst,
            std=s.std, cv=s.cv, vs_field=mean_diff, vs_field_se=sd / math.sqrt(n) if n > 1 else 0.0,
            hit_rate=hits / n if n else 0.0, hits=hits, of_best=s.mean / s.best if s.best else 0.0,
            peers=len(chars), rank_mean=_rank(means, name), rank_best=_rank(bests, name),
            rank_worst=_rank(worsts, name), rank_cv=_rank(cvs, name, higher_is_better=False),
            form_pct=c.form.pct if c.form else None, vs_team=c.above_team_avg,
        )
        slot = ra.by_name.get(name) if ra else None
        if slot is not None:
            p.eff = slot.eff
            if ra.marginal is not None:
                p.value = slot.value
                if slot.eff is not None and ra.reference.mean_eff:
                    p.rating_gap = slot.eff - ra.reference.mean_eff
                    p.rating_worth = ra.marginal * p.rating_gap
        _explain(p, c)
        out.append(p)
    return out


def _explain(p: Profile, c: CharacterStats):
    """Pick an archetype and plain-language reasons from the profile."""
    ceiling, floor, steady = p.third(p.rank_best), p.third(p.rank_worst), p.third(p.rank_cv)
    average = p.third(p.rank_mean)
    n = p.peers
    reasons = []

    # How sure we are about their level
    if p.clearly_below:
        reasons.append((f"Clearly below the match average: {_signed_k(p.vs_field)} per match "
                        f"(95% range {_signed_k(p.low)} to {_signed_k(p.high)}).", -1))
    elif p.clearly_above:
        reasons.append((f"Clearly above the match average: {_signed_k(p.vs_field)} per match "
                        f"(95% range {_signed_k(p.low)} to {_signed_k(p.high)}).", +1))
    else:
        reasons.append((f"{_signed_k(p.vs_field)} vs the match average per match, but within noise so far "
                        f"(95% range {_signed_k(p.low)} to {_signed_k(p.high)}).", 0))

    # Hit rate
    rate = f"{p.hits} of {p.matches} matches ({p.hit_rate:.0%})"
    if p.hit_rate <= 0.3:
        reasons.append((f"Beat the match average in only {rate}.", -1))
    elif p.hit_rate >= 0.7:
        reasons.append((f"Beat the match average in {rate}.", +1))

    # Ceiling vs consistency
    if ceiling == "bottom":
        reasons.append((f"Low ceiling: their best ({_k(p.best)}) is only {_ord(p.rank_best)} of {n}.", -1))
    elif ceiling == "top":
        reasons.append((f"High ceiling: their best ({_k(p.best)}) is {_ord(p.rank_best)} of {n}.", +1))
    if p.of_best >= 0.85:
        reasons.append((f"Plays close to their best: the average is {p.of_best:.0%} of it, so the ceiling "
                        "is what limits them, not bad luck.", -1 if ceiling != "top" else +1))
    elif p.of_best <= 0.75:
        reasons.append((f"Their best is rare: the average is only {p.of_best:.0%} of it.", -1))
    if steady == "bottom":
        reasons.append((f"Inconsistent: swings ±{_k(p.std)} (CV {p.cv:.0%}, {_ord(p.rank_cv)} steadiest of {n}).",
                        -1))
    elif steady == "top":
        reasons.append((f"Consistent: swings only ±{_k(p.std)} (CV {p.cv:.0%}, {_ord(p.rank_cv)} steadiest of {n}).",
                        +1 if average != "bottom" else 0))
    if floor == "bottom":
        reasons.append((f"Low floor: their worst ({_k(p.worst)}) is {_ord(p.rank_worst)} of {n}.", -1))
    elif floor == "top":
        reasons.append((f"High floor: even their worst ({_k(p.worst)}) is {_ord(p.rank_worst)} of {n}.", +1))
    if p.median < p.mean - 0.03 * p.mean:
        reasons.append((f"A few big scores lift the average: the median ({_k(p.median)}) is lower.", 0))

    # Rating, team and form
    if p.rating_worth is not None and abs(p.rating_worth) >= 500:
        if p.rating_gap < 0:
            reasons.append((f"Rating {_k(abs(p.rating_gap))} below the lineup average costs ≈{_k(abs(p.rating_worth))} "
                            "per match across the team.", -1))
        else:
            reasons.append((f"Rating {_k(p.rating_gap)} above the lineup average adds ≈{_k(p.rating_worth)} "
                            "per match across the team.", +1))
    if p.vs_team is not None and abs(p.vs_team) >= 0.05 * p.mean:
        word = "above" if p.vs_team > 0 else "below"
        reasons.append((f"{_signed_k(p.vs_team)} {word} their team's per-member average.",
                        +1 if p.vs_team > 0 else -1))
    if p.form_pct is not None and abs(p.form_pct) >= 0.03:
        word = "Improving" if p.form_pct > 0 else "Slipping"
        reasons.append((f"{word}: last {c.form.window} matches are {p.form_pct:+.1%} vs their average.",
                        +1 if p.form_pct > 0 else -1))

    # Archetype
    if average == "bottom" or p.vs_field < 0:
        if ceiling == "top" and steady == "bottom":
            p.archetype = "Boom or bust"
        elif ceiling == "bottom" and floor == "bottom":
            p.archetype = "Low across the board"
        elif ceiling == "bottom" and steady == "top":
            p.archetype = "Low ceiling, steady"
        elif ceiling == "bottom":
            p.archetype = "Low ceiling"
        elif steady == "bottom":
            p.archetype = "Inconsistent"
        elif p.hit_rate <= 0.3:
            p.archetype = "Consistently below average"
        else:
            p.archetype = "Slightly below the field"
    else:
        if floor == "top" and steady == "top":
            p.archetype = "Reliable star"
        elif ceiling == "top" and steady == "bottom":
            p.archetype = "Explosive"
        elif p.hit_rate >= 0.7:
            p.archetype = "Consistently above average"
        elif ceiling == "top":
            p.archetype = "High ceiling"
        else:
            p.archetype = "Solid"
    p.reasons = reasons


def ranking_key(p: Profile) -> float:
    """Value when ratings are in, else the average."""
    return p.value if p.value is not None else p.mean


def weakest(items: list[Profile], n=3) -> list[Profile]:
    return sorted(items, key=ranking_key)[:n]


def strongest(items: list[Profile], n=3) -> list[Profile]:
    return sorted(items, key=ranking_key, reverse=True)[:n]
