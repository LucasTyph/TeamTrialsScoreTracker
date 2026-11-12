"""End-to-end: real screenshots through OCR. Needs Tesseract installed.

- print1-4.png: hand-drawn snips (Win+Shift+S) of two matches
- window1-2.png: full game-window captures (top and bottom) of one match
"""

import csv
from pathlib import Path

import pytest
from PIL import Image

from score_tracker import ocr
from score_tracker.config import Settings
from score_tracker.pipeline import MatchAccumulator, detect_roster, parse_image

from conftest import DATASET_ROSTER, TESTS_DIR, dataset_rows

pytestmark = pytest.mark.skipif(
    not ocr.configure(Settings().tesseract_cmd), reason="Tesseract OCR not installed"
)


def _window_expected():
    with open(TESTS_DIR / "window_expected.csv", newline="") as f:
        return list(csv.DictReader(f))


@pytest.mark.parametrize("row_index, images", [(0, ("print1.png", "print2.png")),
                                                (1, ("print3.png", "print4.png"))])
def test_snipped_screenshots(settings, row_index, images):
    expected = {n: int(float(v)) for n, v in dataset_rows()[row_index].items() if n != "timestamp"}
    match = MatchAccumulator(settings)
    for name in images:
        match.add(parse_image(Image.open(TESTS_DIR / name), settings, claimed=match.scores))
    assert match.inferred() == [], "every name should be read, not inferred"
    assert match.final_scores() == expected


def test_window_captures():
    rows = _window_expected()
    roster = tuple(r["character"] for r in rows)
    settings = Settings(roster=roster, data_dir=Path("."))
    match = MatchAccumulator(settings)
    for name in ("window1.png", "window2.png"):
        match.add(parse_image(Image.open(TESTS_DIR / name), settings, claimed=match.scores))
    assert match.final_scores() == {r["character"]: int(r["score"]) for r in rows}
    assert match.needs_review == []
    # Every visible badge is read; Taiki Shuttle's is cut off in both captures
    distances = match.final_distances()
    for r in rows:
        if r["character"] != "Taiki Shuttle":
            assert distances[r["character"]] == r["distance"], r["character"]


def test_same_screenshot_twice_adds_nothing(settings):
    img = Image.open(TESTS_DIR / "print1.png")
    first = parse_image(img, settings)
    again = parse_image(img, settings, claimed=first.scores)
    assert again.scores == {}
    assert again.duplicates == first.scores


def test_detect_roster_without_a_roster():
    detected = dict(detect_roster([Image.open(TESTS_DIR / "window2.png")], Settings(data_dir=Path("."))))
    assert detected["Kitasan Black"] == "Long"
    assert detected["Smart Falcon"] == "Dirt"
    assert detected["Maruzensky"] == "Mile"


def test_distance_badges_on_snips():
    rows = ocr.find_score_rows(Image.open(TESTS_DIR / "print1.png"))
    img = Image.open(TESTS_DIR / "print1.png")
    assert [ocr.read_distance(ocr.badge_crop(img, r)) for r in rows if not r.virtual] == \
        ["Long", "Dirt", "Medium", "Mile", "Dirt", "Long", "Mile"]


def test_dataset_roster_fixture_matches():
    assert len(DATASET_ROSTER) == 15
