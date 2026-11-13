"""Match data persistence: one row per (match, character) score.

scores.csv columns: match_id, timestamp, character, score, distance, lineup

This long format means roster changes and partial matches never add empty
columns or misalign old data. ``distance`` is the team the character raced
in for that match (read from the screenshot, or from the roster), so moving a
character between teams later doesn't rewrite history. ``lineup`` is the id of
the lineup (see lineups.py) the match was played with; it's empty for matches
saved before lineups existed, which belong to the "Original" lineup.

Data from the old one-column-per-character ``dataset.csv`` is migrated
automatically and the old file kept as a backup.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from .config import Settings

logger = logging.getLogger(__name__)

COLUMNS = ["match_id", "timestamp", "character", "score", "distance", "lineup"]
LEGACY_BACKUP_SUFFIX = ".wide-backup.csv"


def _empty() -> pd.DataFrame:
    return pd.DataFrame({
        "match_id": pd.Series(dtype="int64"), "timestamp": pd.Series(dtype="str"),
        "character": pd.Series(dtype="str"), "score": pd.Series(dtype="int64"),
        "distance": pd.Series(dtype="str"), "lineup": pd.Series(dtype="str"),
    })


def migrate_legacy(settings: Settings) -> int:
    """Convert a wide legacy dataset.csv into scores.csv. Returns matches migrated."""
    legacy = settings.legacy_csv_path
    if not legacy.is_file() or settings.scores_path.exists():
        return 0

    wide = pd.read_csv(legacy)
    characters = [c for c in wide.columns if c != "timestamp"]
    wide.insert(0, "match_id", range(1, len(wide) + 1))
    long = wide.melt(id_vars=["match_id", "timestamp"], value_vars=characters,
                     var_name="character", value_name="score")
    long = long.dropna(subset=["score"])
    long["score"] = long["score"].round().astype("int64")
    long["distance"] = long["character"].map(lambda n: settings.teams.get(n, ""))
    long["lineup"] = ""
    long = long.sort_values(["match_id", "character"], kind="stable")[COLUMNS]

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    long.to_csv(settings.scores_path, index=False)
    backup = legacy.with_name(legacy.stem + LEGACY_BACKUP_SUFFIX)
    legacy.rename(backup)
    logger.info("Migrated %d matches from %s (backup: %s)", len(wide), legacy, backup)
    return len(wide)


def _write(df: pd.DataFrame, settings: Settings):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    tmp = settings.scores_path.with_suffix(".tmp")
    df[COLUMNS].to_csv(tmp, index=False)
    tmp.replace(settings.scores_path)


def load_scores(settings: Settings) -> pd.DataFrame:
    """All recorded scores in long format (empty frame if none yet)."""
    migrate_legacy(settings)
    path = settings.scores_path
    if not path.is_file():
        return _empty()
    with open(path, encoding="utf-8") as f:
        header = f.readline().strip().split(",")
    dtypes = {"timestamp": "str", "character": "str", "distance": "str", "lineup": "str"}
    old_header = header != COLUMNS
    if old_header:
        # Saved by an older version. Rows appended later may have more columns
        # than the header, so read with all columns.
        df = pd.read_csv(path, names=COLUMNS, skiprows=1, dtype=dtypes)
    else:
        df = pd.read_csv(path, dtype=dtypes)
    if df.empty:
        return _empty()
    if old_header:
        if "distance" not in header:
            # Assume the current teams for rows saved before distances were tracked
            missing = df["distance"].isna()
            df.loc[missing, "distance"] = df.loc[missing, "character"].map(lambda n: settings.teams.get(n, ""))
        df["distance"] = df["distance"].fillna("")
        df["lineup"] = df["lineup"].fillna("")
        # Upgrade the header so later appends stay aligned
        _write(df, settings)
    df["distance"] = df["distance"].fillna("")
    df["lineup"] = df["lineup"].fillna("")
    df["match_id"] = df["match_id"].astype("int64")
    df["score"] = df["score"].astype("int64")
    return df[COLUMNS]


def append_match(scores: dict, settings: Settings, distances: dict | None = None,
                 timestamp: str | None = None, lineup: str = "") -> tuple[int, str]:
    """Append one match. Returns (match_id, timestamp).

    ``distances`` maps characters to the team they raced in; characters not
    in it fall back to their team in the roster.
    """
    existing = load_scores(settings)
    match_id = int(existing["match_id"].max()) + 1 if not existing.empty else 1
    timestamp = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    distances = distances or {}

    rows = [
        {"match_id": match_id, "timestamp": timestamp, "character": name, "score": int(score),
         "distance": distances.get(name) or settings.teams.get(name, ""), "lineup": lineup or ""}
        for name, score in scores.items()
        if score is not None
    ]
    if not rows:
        raise ValueError("No scores to save")

    path = settings.scores_path
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=COLUMNS).to_csv(
        path, mode="a", header=not path.exists(), index=False
    )
    return match_id, timestamp


def delete_match(match_id: int, settings: Settings) -> int:
    """Remove one match. Returns the number of score rows removed."""
    df = load_scores(settings)
    keep = df[df["match_id"] != match_id]
    removed = len(df) - len(keep)
    if removed:
        _write(keep, settings)
    return removed


def move_match(match_id: int, lineup: str, settings: Settings) -> int:
    """Attribute one match to another lineup. Returns the number of rows changed."""
    df = load_scores(settings)
    mask = df["match_id"] == match_id
    if mask.any():
        df.loc[mask, "lineup"] = lineup
        _write(df, settings)
    return int(mask.sum())


def last_match(scores: pd.DataFrame) -> pd.DataFrame:
    """Rows of the most recent match."""
    if scores.empty:
        return scores
    return scores[scores["match_id"] == scores["match_id"].max()]


def to_wide(scores: pd.DataFrame, roster) -> pd.DataFrame:
    """One row per match, one column per roster character (NaN if absent).

    Matches containing none of the roster's characters are dropped.
    """
    roster = list(roster)
    if scores.empty:
        return pd.DataFrame(columns=["timestamp", *roster])
    wide = scores.pivot_table(index="match_id", columns="character", values="score", aggfunc="last")
    wide = wide.reindex(columns=roster).dropna(how="all")
    timestamps = scores.groupby("match_id")["timestamp"].first()
    wide.insert(0, "timestamp", timestamps.reindex(wide.index))
    wide.columns.name = None
    return wide
