"""Screenshots you flagged as read wrongly, kept for improving the OCR later.

Each flag saves two files in ``<data folder>/flagged/``:

- ``<time>.png``: the screenshot exactly as captured
- ``<time>.json``: what the app read from it (every row's name, score,
  distance badge, raw OCR text and status), the roster and teams in use,
  and your note

Nothing else uses them yet; they're examples for future tests.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .config import Settings

FLAGGED_DIRNAME = "flagged"


def flagged_dir(settings: Settings) -> Path:
    return settings.data_dir / FLAGGED_DIRNAME


def save_flagged(img, result, settings: Settings, note: str = "", lineup: str = "",
                 when: datetime | None = None) -> Path:
    """Save a screenshot and what was read from it. Returns the .png path."""
    when = when or datetime.now()
    folder = flagged_dir(settings)
    folder.mkdir(parents=True, exist_ok=True)
    stem = when.strftime("%Y-%m-%d_%H-%M-%S")
    i = 1
    while (folder / f"{stem}.png").exists():
        i += 1
        stem = f"{when:%Y-%m-%d_%H-%M-%S}_{i}"
    png = folder / f"{stem}.png"
    img.save(png)
    info = {
        "flagged_at": when.strftime("%Y-%m-%d %H:%M:%S"),
        "note": note,
        "lineup": lineup,
        "image": png.name,
        "size": list(img.size),
        "bars": getattr(result, "bars", 0),
        "rows": [
            {"name": r.name, "score": r.score, "distance": r.distance, "read_text": r.read_text,
             "status": r.status}
            for r in getattr(result, "rows", [])
        ],
        "fallback_scores": dict(getattr(result, "fallback_scores", {}) or {}),
        "roster": list(settings.roster),
        "teams": dict(settings.teams),
    }
    (folder / f"{stem}.json").write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return png


def flagged_count(settings: Settings) -> int:
    folder = flagged_dir(settings)
    return len(list(folder.glob("*.png"))) if folder.is_dir() else 0
