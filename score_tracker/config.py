"""Settings: built-in defaults overridden by the user's settings.toml.

Personal settings (your teams, a custom Tesseract path, ...) live in
``settings.toml`` inside the data folder, which is not tracked by git.
The file is created on first run and can be edited from the app.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import sys
from dataclasses import dataclass, field, fields, replace
from functools import lru_cache
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

logger = logging.getLogger(__name__)

PACKAGE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = PACKAGE_DIR / "assets"
SETTINGS_FILENAME = "settings.toml"
SCORES_FILENAME = "scores.csv"
LEGACY_CSV_FILENAME = "dataset.csv"

DISTANCES = ("Sprint", "Mile", "Medium", "Long", "Dirt")
TEAM_SIZE = 3

# Settings from older versions that no longer do anything (ignored if present)
_RETIRED = {
    "adjusted_score_k", "crop_above_bar",
    # Weekly goals (removed in 0.4)
    "matches_per_week", "week_reset_weekday", "week_reset_hour_utc", "target_score",
}


class SettingsError(Exception):
    """settings.toml is missing required values or contains invalid ones."""


def default_data_dir() -> Path:
    """Where match data and settings are stored.

    - ``SCORE_TRACKER_DATA`` environment variable, if set
    - ``<project>/data`` when running from a source checkout
    - ``%LOCALAPPDATA%/TeamTrialsScoreTracker`` when installed with pip
    """
    env = os.environ.get("SCORE_TRACKER_DATA")
    if env:
        return Path(env).expanduser().resolve()
    root = PACKAGE_DIR.parent
    if (root / "pyproject.toml").is_file():
        return root / "data"
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home()) / "TeamTrialsScoreTracker"


@dataclass(frozen=True)
class Settings:
    roster: tuple[str, ...] = ()
    # Character name -> distance ("Sprint", ...). Characters without a team
    # are in the roster but not in this mapping.
    teams: dict = field(default_factory=dict)
    tesseract_cmd: str = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    # Window capture
    game_process: str = "umamusumeprettyderby.exe"
    capture_hotkey: str = "ctrl+alt+s"
    # OCR / parsing tuning
    row_tolerance: int = 20
    fuzzy_match_threshold: float = 0.6
    min_bar_width: int = 100
    # An incomplete match is saved as partial after this many idle minutes
    pending_timeout_minutes: float = 10.0
    # Rating model: percentage points of score bonus per 1k of team rating,
    # and the rating boost for each S aptitude instead of A
    rating_bonus_per_1k: float = 0.5
    s_aptitude_bonus: float = 0.02
    # Use the per-1k bonus fitted from your lineups instead of rating_bonus_per_1k
    use_fitted_bonus: bool = False
    data_dir: Path = field(default_factory=default_data_dir)

    @property
    def scores_path(self) -> Path:
        return self.data_dir / SCORES_FILENAME

    @property
    def legacy_csv_path(self) -> Path:
        return self.data_dir / LEGACY_CSV_FILENAME

    @property
    def settings_path(self) -> Path:
        return self.data_dir / SETTINGS_FILENAME

    @property
    def log_path(self) -> Path:
        return self.data_dir / "tracker.log"

    def team_members(self, distance) -> list[str]:
        return [n for n in self.roster if self.teams.get(n) == distance]

    def with_roster(self, roster, teams=None) -> "Settings":
        return replace(self, roster=tuple(roster), teams=dict(teams or {}))


_OVERRIDABLE = [f.name for f in fields(Settings) if f.name not in ("roster", "teams", "data_dir")]


def _legacy_roster(data_dir: Path) -> list[str]:
    """Roster from the header of a pre-0.2 wide CSV, if one exists."""
    path = data_dir / LEGACY_CSV_FILENAME
    if not path.is_file():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        header = next(csv.reader(f), [])
    return [name for name in header if name and name != "timestamp"]


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        # Literal string: no escaping needed for Windows paths
        return f"'{value}'" if "'" not in value else json.dumps(value)
    return repr(value)


def _toml_list(names) -> str:
    return "[" + ", ".join(json.dumps(n, ensure_ascii=False) for n in names) + "]"


def settings_template(roster, teams=None, overrides=None) -> str:
    """settings.toml content for a roster, team assignment and overrides.

    TOML needs top-level keys before tables, so [teams] comes last.
    """
    teams = teams or {}
    overrides = overrides or {}
    defaults = Settings(data_dir=Path("."))
    lines = [
        "# Team Trials Score Tracker settings (also editable on the app's Roster page).",
        "",
        "# Characters not assigned to a team yet",
        f"roster = {_toml_list(n for n in roster if n not in teams)}",
        "",
        "# Uncomment a line to override its default.",
    ]
    for name in _OVERRIDABLE:
        value = overrides.get(name, getattr(defaults, name))
        prefix = "" if name in overrides else "# "
        lines.append(f"{prefix}{name} = {_toml_value(value)}")
    lines += [
        "",
        "# Your five teams of three, with each character's exact in-game name.",
        "# Changing them is safe: past matches keep the team each score was earned in.",
        "[teams]",
    ]
    for d in DISTANCES:
        lines.append(f"{d} = {_toml_list(n for n in roster if teams.get(n) == d)}")
    return "\n".join(lines) + "\n"


def ensure_settings_file(data_dir: Path | None = None) -> Path:
    """Create settings.toml if missing (seeding the roster from legacy data)."""
    data_dir = data_dir or default_data_dir()
    path = data_dir / SETTINGS_FILENAME
    if not path.exists():
        data_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(settings_template(_legacy_roster(data_dir)), encoding="utf-8")
    return path


def _names(path, key, value) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(n, str) for n in value):
        raise SettingsError(f"{path}: '{key}' must be a list of names")
    return [n.strip() for n in value if n.strip()]


def load_settings(data_dir: Path | None = None) -> Settings:
    """Read settings.toml from the data folder (creating it if needed)."""
    data_dir = data_dir or default_data_dir()
    path = ensure_settings_file(data_dir)
    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise SettingsError(f"{path}: {e}") from e

    teams_raw = raw.pop("teams", {})
    if not isinstance(teams_raw, dict):
        raise SettingsError(f"{path}: [teams] must be a table")
    unknown_teams = sorted(set(teams_raw) - set(DISTANCES))
    if unknown_teams:
        raise SettingsError(f"{path}: unknown team(s): {', '.join(unknown_teams)} "
                            f"(use {', '.join(DISTANCES)})")
    roster, teams = [], {}
    for d in DISTANCES:
        for name in _names(path, d, teams_raw.get(d, [])):
            roster.append(name)
            teams.setdefault(name, d)
    roster += _names(path, "roster", raw.pop("roster", []))
    dupes = sorted({n for n in roster if roster.count(n) > 1})
    if dupes:
        raise SettingsError(f"{path}: duplicate roster names: {', '.join(dupes)}")

    values = {"data_dir": data_dir, "roster": tuple(roster), "teams": teams}
    for key in _RETIRED & set(raw):
        logger.info("Ignoring retired setting %r in %s", key, path)
        raw.pop(key)
    unknown = sorted(set(raw) - set(_OVERRIDABLE))
    if unknown:
        raise SettingsError(f"{path}: unknown setting(s): {', '.join(unknown)}")
    defaults = Settings(data_dir=data_dir)
    for key, value in raw.items():
        expected = type(getattr(defaults, key))
        if expected is float and isinstance(value, int):
            value = float(value)
        if expected is bool:
            ok = isinstance(value, bool)
        else:
            ok = isinstance(value, expected) and not isinstance(value, bool)
        if not ok:
            raise SettingsError(f"{path}: '{key}' must be of type {expected.__name__}")
        values[key] = value
    return Settings(**values)


def save_settings(settings: Settings) -> Path:
    """Write roster, teams and any non-default settings to settings.toml."""
    defaults = Settings(data_dir=settings.data_dir)
    overrides = {k: getattr(settings, k) for k in _OVERRIDABLE
                 if getattr(settings, k) != getattr(defaults, k)}
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    path = settings.settings_path
    tmp = path.with_suffix(".tmp")
    tmp.write_text(settings_template(settings.roster, settings.teams, overrides), encoding="utf-8")
    tmp.replace(path)
    return path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Settings for the running app (loaded once)."""
    return load_settings()
