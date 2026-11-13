import json

import pandas as pd
import pytest
from PIL import Image

from score_tracker.analysis import analyze
from score_tracker.config import Settings
from score_tracker.flagged import flagged_count, save_flagged
from score_tracker.pipeline import MATCHED, UNNAMED, ImageResult, RowResult
from score_tracker.profiles import profiles, strongest, weakest

# Six racers in two teams; each pattern repeats over 12 matches
TEAMS = {"Star": "Sprint", "Steady": "Sprint", "Boom": "Sprint", "Low": "Dirt", "Mid": "Dirt", "Mid2": "Dirt"}
PATTERNS = {
    "Star": [80, 81, 80, 81],  # high and steady
    "Steady": [60, 61, 59, 60],  # low ceiling, close to it every time
    "Boom": [95, 40, 45, 42],  # one big score, mostly low
    "Low": [55, 56, 54, 55],
    "Mid": [70, 69, 71, 70],
    "Mid2": [68, 72, 70, 70],
}


@pytest.fixture
def analysis(tmp_path):
    rows = []
    for m in range(12):
        for name, pattern in PATTERNS.items():
            rows.append({"match_id": m + 1, "timestamp": f"2026-11-01 {m:02d}:00", "character": name,
                         "score": pattern[m % 4] * 1000, "distance": TEAMS[name], "lineup": ""})
    settings = Settings(roster=tuple(TEAMS), teams=TEAMS, data_dir=tmp_path)
    return analyze(pd.DataFrame(rows), settings)


def test_profiles_rank_and_explain(analysis):
    items = {p.name: p for p in profiles(analysis)}
    assert set(items) == set(TEAMS)
    star, steady, boom = items["Star"], items["Steady"], items["Boom"]
    assert star.rank_mean == 1 and star.clearly_above and star.hit_rate == 1.0
    assert star.archetype == "Reliable star"
    assert boom.rank_best == 1 and boom.rank_cv == 6
    assert boom.archetype == "Boom or bust"
    assert steady.of_best > 0.95 and steady.clearly_below
    assert any("Plays close to their best" in text for text, _ in steady.reasons)
    assert items["Low"].archetype == "Low across the board"


def test_weakest_and_strongest_use_the_average_without_ratings(analysis):
    items = profiles(analysis)
    assert [p.name for p in strongest(items, 2)] == ["Star", "Mid"]
    assert weakest(items, 1)[0].name == "Low"


def test_save_flagged(tmp_path):
    settings = Settings(roster=("A", "B"), teams={"A": "Sprint"}, data_dir=tmp_path)
    result = ImageResult(rows=[RowResult(name="A", score=1234, distance="Sprint", status=MATCHED),
                               RowResult(score=999, read_text="8?", status=UNNAMED)], bars=2)
    img = Image.new("RGB", (40, 20), "white")
    png = save_flagged(img, result, settings, note="missed B", lineup="l1")
    save_flagged(img, result, settings)  # same second: doesn't overwrite
    assert flagged_count(settings) == 2
    info = json.loads(png.with_suffix(".json").read_text(encoding="utf-8"))
    assert info["note"] == "missed B" and info["lineup"] == "l1"
    assert [r["status"] for r in info["rows"]] == [MATCHED, UNNAMED]
    assert info["rows"][1]["read_text"] == "8?" and info["teams"] == {"A": "Sprint"}
    assert Image.open(png).size == (40, 20)
