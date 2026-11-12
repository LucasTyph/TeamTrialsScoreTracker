"""Settings: built-in defaults overridden by the user's settings.toml.

Personal settings (your roster, a custom Tesseract path, ...) live in
``settings.toml`` inside the data folder, which is not tracked by git.
The file is created on first run.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from dataclasses import dataclass, field, fields, replace
from functools import lru_cache
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

PACKAGE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = PACKAGE_DIR / "assets"
SETTINGS_FILENAME = "settings.toml"
SCORES_FILENAME = "scores.csv"
LEGACY_CSV_FILENAME = "dataset.csv"


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
    tesseract_cmd: str = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    # Analysis: adjusted score = mean - k * std
    adjusted_score_k: float = 0.5
    # OCR / parsing tuning
    row_tolerance: int = 20
    fuzzy_match_threshold: float = 0.6
    crop_above_bar: int = 55
    min_bar_width: int = 100
    # Tray: an incomplete match is saved as partial after this many idle minutes
    pending_timeout_minutes: float = 10.0
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
        return self.data_dir / "tray.log"

    def with_roster(self, roster) -> "Settings":
        return replace(self, roster=tuple(roster))


_OVERRIDABLE = {f.name: f for f in fields(Settings) if f.name not in ("roster", "data_dir")}


def _legacy_roster(data_dir: Path) -> list[str]:
    """Roster from the header of a pre-0.2 wide CSV, if one exists."""
    path = data_dir / LEGACY_CSV_FILENAME
    if not path.is_file():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        header = next(csv.reader(f), [])
    return [name for name in header if name and name != "timestamp"]


def settings_template(roster) -> str:
    defaults = Settings(data_dir=Path("."))
    lines = [
        "# Team Trials Score Tracker settings.",
        "#",
        "# roster: the exact in-game names of the 15 characters on your team.",
        "# Changing it is safe: past matches keep their own characters.",
        "roster = [",
    ]
    lines += [f"    {json.dumps(name, ensure_ascii=False)}," for name in roster]
    lines += [
        "]",
        "",
        "# Uncomment a line to override its default.",
        f"# tesseract_cmd = '{defaults.tesseract_cmd}'",
    ]
    for name in _OVERRIDABLE:
        if name != "tesseract_cmd":
            lines.append(f"# {name} = {getattr(defaults, name)}")
    return "\n".join(lines) + "\n"


def ensure_settings_file(data_dir: Path | None = None) -> Path:
    """Create settings.toml if missing (seeding the roster from legacy data)."""
    data_dir = data_dir or default_data_dir()
    path = data_dir / SETTINGS_FILENAME
    if not path.exists():
        data_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(settings_template(_legacy_roster(data_dir)), encoding="utf-8")
    return path


def load_settings(data_dir: Path | None = None) -> Settings:
    """Read settings.toml from the data folder (creating it if needed)."""
    data_dir = data_dir or default_data_dir()
    path = ensure_settings_file(data_dir)
    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise SettingsError(f"{path}: {e}") from e

    values = {"data_dir": data_dir}
    roster = raw.pop("roster", [])
    if not isinstance(roster, list) or not all(isinstance(n, str) for n in roster):
        raise SettingsError(f"{path}: 'roster' must be a list of names")
    roster = [n.strip() for n in roster if n.strip()]
    dupes = sorted({n for n in roster if roster.count(n) > 1})
    if dupes:
        raise SettingsError(f"{path}: duplicate roster names: {', '.join(dupes)}")
    values["roster"] = tuple(roster)

    unknown = sorted(set(raw) - set(_OVERRIDABLE))
    if unknown:
        raise SettingsError(f"{path}: unknown setting(s): {', '.join(unknown)}")
    for key, value in raw.items():
        expected = type(getattr(Settings(data_dir=data_dir), key))
        if expected is float and isinstance(value, int):
            value = float(value)
        if not isinstance(value, expected) or isinstance(value, bool):
            raise SettingsError(f"{path}: '{key}' must be of type {expected.__name__}")
        values[key] = value
    return Settings(**values)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Settings for the running app (loaded once)."""
    return load_settings()
