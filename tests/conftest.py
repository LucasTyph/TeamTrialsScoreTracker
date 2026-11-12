import csv
from pathlib import Path

import pytest

from score_tracker.config import Settings

TESTS_DIR = Path(__file__).resolve().parent


def dataset_rows():
    with open(TESTS_DIR / "dataset.csv", newline="") as f:
        return list(csv.DictReader(f))


DATASET_ROSTER = tuple(n for n in dataset_rows()[0] if n != "timestamp")


def make_ocr(words):
    """Build a pytesseract image_to_data dict from (text, x, y, w, h) tuples."""
    data = {"level": [], "text": [], "left": [], "top": [], "width": [], "height": []}
    for text, x, y, w, h in words:
        data["level"].append(5)
        data["text"].append(text)
        data["left"].append(x)
        data["top"].append(y)
        data["width"].append(w)
        data["height"].append(h)
    return data


def row(*texts, y=10, h=14):
    """Words laid out left to right on one line."""
    words, x = [], 0
    for t in texts:
        w = 9 * len(t)
        words.append((t, x, y, w, h))
        x += w + 8
    return words


@pytest.fixture
def settings(tmp_path):
    return Settings(roster=DATASET_ROSTER, data_dir=tmp_path)
