from pathlib import Path

from PIL import Image

from score_tracker.config import Settings
from score_tracker.pipeline import (
    DUPLICATE,
    MATCHED,
    UNNAMED,
    UNREADABLE,
    ImageResult,
    MatchAccumulator,
    RowResult,
)

TEAMS = {"A": "Sprint", "B": "Sprint", "C": "Dirt", "D": "Dirt"}
SETTINGS = Settings(roster=tuple(TEAMS), teams=TEAMS, data_dir=Path("."))


def image(*rows) -> ImageResult:
    return ImageResult(rows=list(rows), bars=len(rows))


def matched(name, score, distance=None):
    return RowResult(name=name, score=score, distance=distance, status=MATCHED)


def unnamed(score, distance=None):
    return RowResult(score=score, distance=distance, status=UNNAMED)


def test_complete_when_all_found():
    m = MatchAccumulator(SETTINGS)
    m.add(image(matched("A", 10000), matched("B", 20000)))
    assert not m.complete
    m.add(image(matched("C", 30000), matched("D", 40000)))
    assert m.complete and m.inferred() == []


def test_one_missing_name_inferred_from_unnamed_row():
    m = MatchAccumulator(SETTINGS)
    m.add(image(matched("A", 10000), matched("B", 20000), matched("C", 30000), unnamed(40000)))
    assert [(n, s) for n, s, _ in m.inferred()] == [("D", 40000)]
    assert m.complete
    assert m.final_scores()["D"] == 40000


def test_team_badge_resolves_two_missing_at_once():
    # Two names unread, but each row's badge says which team it's from
    m = MatchAccumulator(SETTINGS)
    m.add(image(matched("A", 10000), matched("C", 30000), unnamed(20000, "Sprint"), unnamed(40000, "Dirt")))
    assert sorted((n, s) for n, s, _ in m.inferred()) == [("B", 20000), ("D", 40000)]
    assert m.final_distances()["B"] == "Sprint"
    assert m.needs_review == []


def test_no_inference_when_ambiguous():
    m = MatchAccumulator(SETTINGS)
    m.add(image(matched("A", 10000), unnamed(20000), unnamed(30000)))
    assert m.inferred() == []
    assert len(m.needs_review) == 2
    assert not m.complete


def test_unnamed_row_matching_a_known_score_is_ignored():
    # Overlapping screenshots: the unread row is a character already recorded.
    m = MatchAccumulator(SETTINGS)
    m.add(image(matched("A", 10000), matched("B", 20000), unnamed(20000)))
    assert m.unnamed == []


def test_resolve_by_hand():
    m = MatchAccumulator(SETTINGS)
    row = unnamed(20000)
    m.add(image(matched("A", 10000), row, unnamed(30000)))
    m.resolve("B", 20000, row)
    assert m.final_scores()["B"] == 20000
    assert row not in m.unnamed


def test_recorded_row_is_duplicate_not_similar_name(settings, monkeypatch):
    from conftest import make_ocr, row

    from score_tracker import ocr, pipeline

    words = row("Sakura", "Chiyono", "O", "51,543", "pts")
    monkeypatch.setattr(ocr, "extract_data", lambda img: make_ocr(words))
    result = pipeline._parse_row(Image.new("RGB", (4, 4)), settings, None, claimed={"Sakura Chiyono O"})
    assert result.status == DUPLICATE
    assert (result.name, result.score) == ("Sakura Chiyono O", 51543)


def test_badge_limits_candidates_to_that_team(monkeypatch):
    from conftest import make_ocr, row

    from score_tracker import ocr, pipeline

    teams = {"Agnes Tachyon": "Medium", "Agnes Digital": "Dirt"}
    s = Settings(roster=tuple(teams), teams=teams, data_dir=Path("."))
    # Only "Agnes" was read: a tie between the two, broken by the badge
    monkeypatch.setattr(ocr, "extract_data", lambda img: make_ocr(row("Agnes", "77,720")))
    s = Settings(roster=tuple(teams), teams=teams, data_dir=Path("."), fuzzy_match_threshold=0.5)
    result = pipeline._parse_row(Image.new("RGB", (4, 4)), s, "Dirt", claimed=set())
    assert (result.status, result.name) == (MATCHED, "Agnes Digital")


def test_unreadable_row_status(monkeypatch, settings):
    from conftest import make_ocr, row

    from score_tracker import ocr, pipeline

    monkeypatch.setattr(ocr, "extract_data", lambda img: make_ocr(row("pts")))
    result = pipeline._parse_row(Image.new("RGB", (4, 4)), settings, None, claimed=set())
    assert result.status == UNREADABLE
