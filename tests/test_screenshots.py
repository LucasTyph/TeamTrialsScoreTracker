"""End-to-end: real screenshots through OCR. Needs Tesseract installed."""

import pytest
from PIL import Image

from score_tracker import ocr
from score_tracker.config import Settings
from score_tracker.pipeline import MatchAccumulator, parse_image

from conftest import DATASET_ROSTER, TESTS_DIR, dataset_rows

pytestmark = pytest.mark.skipif(
    not ocr.configure(Settings().tesseract_cmd), reason="Tesseract OCR not installed"
)


@pytest.mark.parametrize("row_index, images", [(0, ("print1.png", "print2.png")),
                                                (1, ("print3.png", "print4.png"))])
def test_match_screenshots(settings, row_index, images):
    expected = {n: int(float(v)) for n, v in dataset_rows()[row_index].items() if n != "timestamp"}
    match = MatchAccumulator(DATASET_ROSTER)
    for name in images:
        match.add(parse_image(Image.open(TESTS_DIR / name), settings, claimed=match.scores))
    assert match.inferred() is None, "every name should be read, not inferred"
    assert match.final_scores() == expected


def test_same_screenshot_twice_adds_nothing(settings):
    img = Image.open(TESTS_DIR / "print1.png")
    first = parse_image(img, settings)
    again = parse_image(img, settings, claimed=first.scores)
    assert again.scores == {}
    assert again.duplicates == first.scores
