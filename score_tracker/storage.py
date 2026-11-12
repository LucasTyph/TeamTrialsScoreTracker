"""Match data persistence: one row per (match, character) score.

scores.csv columns: match_id, timestamp, character, score

This long format means roster changes and partial matches never add empty
columns or misalign old data. Data from the old one-column-per-character
``dataset.csv`` is migrated automatically and the old file kept as a backup.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from .config import Settings

logger = logging.getLogger(__name__)

COLUMNS = ["match_id", "timestamp", "character", "score"]
LEGACY_BACKUP_SUFFIX = ".wide-backup.csv"


def _empty() -> pd.DataFrame:
    return pd.DataFrame({"match_id": pd.Series(dtype="int64"), "timestamp": pd.Series(dtype="str"),
                         "character": pd.Series(dtype="str"), "score": pd.Series(dtype="int64")})


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
    long = long.sort_values(["match_id", "character"], kind="stable")[COLUMNS]

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    long.to_csv(settings.scores_path, index=False)
    backup = legacy.with_name(legacy.stem + LEGACY_BACKUP_SUFFIX)
    legacy.rename(backup)
    logger.info("Migrated %d matches from %s (backup: %s)", len(wide), legacy, backup)
    return len(wide)


def load_scores(settings: Settings) -> pd.DataFrame:
    """All recorded scores in long format (empty frame if none yet)."""
    migrate_legacy(settings)
    path = settings.scores_path
    if not path.is_file():
        return _empty()
    df = pd.read_csv(path, dtype={"timestamp": "str", "character": "str"})
    if df.empty:
        return _empty()
    df["match_id"] = df["match_id"].astype("int64")
    df["score"] = df["score"].astype("int64")
    return df[COLUMNS]


def append_match(scores: dict, settings: Settings, timestamp: str | None = None) -> tuple[int, str]:
    """Append one match. Returns (match_id, timestamp)."""
    existing = load_scores(settings)
    match_id = int(existing["match_id"].max()) + 1 if not existing.empty else 1
    timestamp = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows = [
        {"match_id": match_id, "timestamp": timestamp, "character": name, "score": int(score)}
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
