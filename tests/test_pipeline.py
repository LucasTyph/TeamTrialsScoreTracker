from score_tracker.pipeline import ImageResult, MatchAccumulator

ROSTER = ("A", "B", "C")


def test_complete_when_all_found():
    m = MatchAccumulator(ROSTER)
    m.add(ImageResult(scores={"A": 10000, "B": 20000}))
    assert not m.complete
    m.add(ImageResult(scores={"C": 30000}))
    assert m.complete and m.inferred() is None


def test_one_missing_name_inferred_from_orphan_score():
    m = MatchAccumulator(ROSTER)
    m.add(ImageResult(scores={"A": 10000, "B": 20000}, orphan_scores=[30000]))
    assert m.inferred() == ("C", 30000)
    assert m.complete
    assert m.final_scores() == {"A": 10000, "B": 20000, "C": 30000}


def test_no_inference_when_ambiguous():
    m = MatchAccumulator(ROSTER)
    m.add(ImageResult(scores={"A": 10000}, orphan_scores=[20000, 30000]))
    assert m.inferred() is None
    assert not m.complete


def test_orphan_matching_a_known_score_is_ignored():
    # Overlapping screenshots: the orphan row is a character already recorded.
    m = MatchAccumulator(ROSTER)
    m.add(ImageResult(scores={"A": 10000, "B": 20000}, orphan_scores=[20000]))
    assert m.inferred() is None


def test_recorded_row_is_duplicate_not_similar_name(settings, monkeypatch):
    from score_tracker import ocr, pipeline
    from PIL import Image
    from conftest import make_ocr, row

    words = row("Sakura", "Chiyono", "O", "51,543", "pts")
    monkeypatch.setattr(ocr, "extract_data", lambda img: make_ocr(words))
    scores, orphan, dup = pipeline._parse_crop(Image.new("RGB", (4, 4)), settings, claimed={"Sakura Chiyono O"})
    assert scores == {} and orphan is None
    assert dup == {"Sakura Chiyono O": 51543}
