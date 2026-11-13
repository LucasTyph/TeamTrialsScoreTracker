"""Builds (trained copies of a character) and lineups (named versions of the team).

Stored in ``roster.json`` in the data folder, which the app edits. Exactly one
lineup is active: captured matches are attributed to it, and the settings'
``roster``/``teams`` are derived from it so OCR matching keeps working as before.

The first time this runs, the ``[teams]`` from settings.toml become a lineup
named "Original" that owns every match recorded so far.
"""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from pathlib import Path

from .config import DISTANCES, TEAM_SIZE, Settings

logger = logging.getLogger(__name__)

ROSTER_FILENAME = "roster.json"
GRADES = ("S", "A", "B", "C", "D", "E", "F", "G")
STYLES = ("Front", "Pace", "Late", "End")
DEFAULT_GRADE = "A"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class Build:
    """One trained copy of a character. The rating is the base rating, before S boosts."""

    id: str
    character: str
    label: str = "v1"
    rating: int | None = None
    surface_grade: str = DEFAULT_GRADE
    distance_grade: str = DEFAULT_GRADE
    style: str = ""
    style_grade: str = DEFAULT_GRADE
    created: str = field(default_factory=_now)
    notes: str = ""

    @property
    def grades(self) -> tuple[str, str, str]:
        return (self.surface_grade, self.distance_grade, self.style_grade)

    @property
    def s_count(self) -> int:
        return sum(g == "S" for g in self.grades)

    @property
    def below_a(self) -> bool:
        return any(g not in ("S", "A") for g in self.grades)

    def same_stats(self, other: "Build") -> bool:
        keys = ("character", "rating", "surface_grade", "distance_grade", "style", "style_grade")
        return all(getattr(self, k) == getattr(other, k) for k in keys)


@dataclass
class Lineup:
    id: str
    name: str
    slots: dict = field(default_factory=lambda: {d: [] for d in DISTANCES})  # distance -> [build ids]
    created: str = field(default_factory=_now)
    notes: str = ""
    displayed_rating: int | None = None  # the game's displayed team rating, if entered

    def build_ids(self) -> list[str]:
        return [b for d in DISTANCES for b in self.slots.get(d, [])]


@dataclass
class Roster:
    builds: dict = field(default_factory=dict)  # id -> Build
    lineups: list = field(default_factory=list)  # Lineup, oldest first
    active: str = ""  # active lineup id
    legacy_lineup: str = ""  # owns scores saved without a lineup

    # --- lookups -----------------------------------------------------------

    def lineup(self, lineup_id) -> Lineup | None:
        return next((l for l in self.lineups if l.id == lineup_id), None)

    @property
    def active_lineup(self) -> Lineup | None:
        return self.lineup(self.active) or (self.lineups[0] if self.lineups else None)

    def members(self, lineup: Lineup) -> list[tuple[str, Build]]:
        """(distance, build) for every filled slot, in DISTANCES order."""
        return [(d, self.builds[b]) for d in DISTANCES for b in lineup.slots.get(d, []) if b in self.builds]

    def teams(self, lineup: Lineup | None) -> dict:
        """Character name -> distance for a lineup."""
        return {b.character: d for d, b in self.members(lineup)} if lineup else {}

    def build_for(self, lineup: Lineup | None, character) -> Build | None:
        if lineup is None:
            return None
        return next((b for _, b in self.members(lineup) if b.character == character), None)

    def builds_of(self, character) -> list[Build]:
        return [b for b in self.builds.values() if b.character == character]

    def latest_build(self, character) -> Build | None:
        builds = self.builds_of(character)
        return max(builds, key=lambda b: (b.created, _id_num(b.id))) if builds else None

    def resolve_lineup(self, lineup_id) -> str:
        """Lineup id for a score row ("" = saved before lineups existed)."""
        if lineup_id and self.lineup(lineup_id):
            return lineup_id
        return self.legacy_lineup or (self.lineups[0].id if self.lineups else "")

    # --- edits -------------------------------------------------------------

    def _next_id(self, prefix, existing) -> str:
        n = max((_id_num(i) for i in existing if i.startswith(prefix)), default=0)
        return f"{prefix}{n + 1}"

    def new_build(self, character, **stats) -> Build:
        b = Build(id=self._next_id("b", self.builds), character=character, **stats)
        self.builds[b.id] = b
        return b

    def new_version(self, build: Build) -> Build:
        """A copy of a build with the next version label (for a re-trained character)."""
        n = len(self.builds_of(build.character)) + 1
        stats = {k: v for k, v in asdict(build).items() if k not in ("id", "character", "created", "label")}
        return self.new_build(build.character, label=f"v{n}", **stats)

    def new_lineup(self, name, source: Lineup | None = None) -> Lineup:
        slots = copy.deepcopy(source.slots) if source else {d: [] for d in DISTANCES}
        lineup = Lineup(id=self._next_id("l", [l.id for l in self.lineups]), name=name, slots=slots,
                        displayed_rating=source.displayed_rating if source else None)
        self.lineups.append(lineup)
        return lineup

    def unique_name(self, base) -> str:
        names = {l.name for l in self.lineups}
        if base not in names:
            return base
        i = 2
        while f"{base} ({i})" in names:
            i += 1
        return f"{base} ({i})"

    def copy(self) -> "Roster":
        return copy.deepcopy(self)


def _id_num(i: str) -> int:
    digits = "".join(c for c in i if c.isdigit())
    return int(digits) if digits else 0


# --- (de)serialisation --------------------------------------------------------------

def _clean_grade(g) -> str:
    g = str(g or DEFAULT_GRADE).strip().upper()
    return g if g in GRADES else DEFAULT_GRADE


def _build_from(d: dict) -> Build:
    rating = d.get("rating")
    return Build(
        id=str(d["id"]), character=str(d["character"]), label=str(d.get("label") or "v1"),
        rating=int(rating) if rating not in (None, "") else None,
        surface_grade=_clean_grade(d.get("surface_grade")),
        distance_grade=_clean_grade(d.get("distance_grade")),
        style=str(d.get("style") or ""), style_grade=_clean_grade(d.get("style_grade")),
        created=str(d.get("created") or _now()), notes=str(d.get("notes") or ""),
    )


def _lineup_from(d: dict) -> Lineup:
    raw = d.get("slots") or {}
    slots = {dist: [str(b) for b in raw.get(dist, [])][:TEAM_SIZE] for dist in DISTANCES}
    shown = d.get("displayed_rating")
    return Lineup(id=str(d["id"]), name=str(d.get("name") or d["id"]), slots=slots,
                  created=str(d.get("created") or _now()), notes=str(d.get("notes") or ""),
                  displayed_rating=int(shown) if shown not in (None, "") else None)


def roster_to_dict(roster: Roster) -> dict:
    return {
        "active": roster.active,
        "legacy_lineup": roster.legacy_lineup,
        "lineups": [asdict(l) for l in roster.lineups],
        "builds": [asdict(b) for b in roster.builds.values()],
    }


def roster_from_dict(data: dict) -> Roster:
    builds = {b.id: b for b in (_build_from(x) for x in data.get("builds", []))}
    lineups = [_lineup_from(x) for x in data.get("lineups", [])]
    for l in lineups:
        for d in DISTANCES:
            l.slots[d] = [b for b in l.slots[d] if b in builds]
    roster = Roster(builds=builds, lineups=lineups, active=str(data.get("active") or ""),
                    legacy_lineup=str(data.get("legacy_lineup") or ""))
    if lineups and not roster.lineup(roster.active):
        roster.active = lineups[0].id
    if lineups and not roster.lineup(roster.legacy_lineup):
        roster.legacy_lineup = lineups[0].id
    return roster


def roster_path(settings: Settings) -> Path:
    return settings.data_dir / ROSTER_FILENAME


def migrate_from_settings(settings: Settings) -> Roster:
    """The settings.toml [teams] as a lineup named "Original" (builds without ratings)."""
    roster = Roster()
    lineup = roster.new_lineup("Original")
    for d in DISTANCES:
        for name in settings.team_members(d)[:TEAM_SIZE]:
            lineup.slots[d].append(roster.new_build(name).id)
    roster.active = roster.legacy_lineup = lineup.id
    return roster


def save_roster(roster: Roster, settings: Settings) -> Path:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    path = roster_path(settings)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(roster_to_dict(roster), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def load_roster(settings: Settings) -> Roster:
    """roster.json, created from settings.toml's [teams] the first time."""
    path = roster_path(settings)
    if path.is_file():
        return roster_from_dict(json.loads(path.read_text(encoding="utf-8")))
    roster = migrate_from_settings(settings)
    save_roster(roster, settings)
    logger.info("Created %s with the lineup 'Original' from settings.toml", path)
    return roster


def apply_lineup(settings: Settings, roster: Roster) -> Settings:
    """Settings whose roster and teams are the active lineup's (plus unassigned names)."""
    unassigned = [n for n in settings.roster if n not in settings.teams]
    teams = roster.teams(roster.active_lineup)
    names = list(teams) + [n for n in unassigned if n not in teams]
    return settings.with_roster(names, teams)


def with_slots(settings: Settings, roster: Roster, lineup: Lineup) -> Settings:
    """Settings as if ``lineup`` were active (for analysing one lineup)."""
    return apply_lineup(settings, replace(roster, active=lineup.id))
