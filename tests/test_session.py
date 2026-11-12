from pathlib import Path

import pytest
from PIL import Image

from score_tracker import session as session_mod
from score_tracker.config import Settings
from score_tracker.pipeline import DUPLICATE, MATCHED, ImageResult, RowResult
from score_tracker.session import MatchSession

ROSTER = ("A", "B", "C", "D")


@pytest.fixture
def sess(monkeypatch):
    """Session whose parse_image returns queued screens instead of running OCR."""
    queue = []
    saved = []

    def fake_parse(img, settings, claimed=()):
        screen = queue[0]
        rows = []
        for name, score in screen.items():
            status = DUPLICATE if name in claimed else MATCHED
            rows.append(RowResult(name=name, score=score, status=status))
        dups_differ = [n for n, s in screen.items() if n in claimed and claimed[n] != s]
        # The session re-parses a new match's screenshot without claims
        if not claimed or len(dups_differ) < session_mod.NEW_MATCH_MIN_CHANGED:
            queue.pop(0)
        return ImageResult(rows=rows, bars=len(rows))

    monkeypatch.setattr(session_mod, "parse_image", fake_parse)
    s = MatchSession(Settings(roster=ROSTER, data_dir=Path(".")), on_save=saved.append)
    s.feed = lambda screen: (queue.append(screen), s.process_image(Image.new("RGB", (4, 4))))[1]
    s.saved = saved
    return s


def test_two_screenshots_make_one_match(sess):
    sess.feed({"A": 10000, "B": 20000})
    assert sess.saved == [] and sess.pending_count == 2
    out = sess.feed({"B": 20000, "C": 30000, "D": 40000})  # overlaps on B
    assert [s.scores for s in sess.saved] == [{"A": 10000, "B": 20000, "C": 30000, "D": 40000}]
    assert sess.saved[0].complete
    assert out.new_characters == 2 and sess.pending_count == 0


def test_new_match_flushes_incomplete_previous_one(sess):
    sess.feed({"A": 10000, "B": 20000})
    sess.feed({"A": 11000, "B": 21000, "C": 31000})  # next match: same characters, new scores
    assert [(s.scores, s.complete) for s in sess.saved] == [({"A": 10000, "B": 20000}, False)]
    assert sess.pending_count == 3


def test_retaken_screenshot_is_not_a_new_match(sess):
    sess.feed({"A": 10000, "B": 20000})
    sess.feed({"A": 10000, "B": 20000})
    assert sess.saved == [] and sess.pending_count == 2


def test_save_and_discard(sess):
    sess.feed({"A": 10000})
    assert sess.save().scores == {"A": 10000}
    sess.feed({"B": 20000})
    assert sess.discard() == 1
    assert sess.pending_count == 0 and len(sess.saved) == 1


def test_resolving_the_last_character_saves(sess):
    sess.feed({"A": 10000, "B": 20000, "C": 30000})
    saved = sess.resolve("D", 40000)
    assert saved is not None and saved.complete
    assert sess.pending_count == 0


def test_idle_pending_match_is_saved_after_timeout(sess):
    sess.feed({"A": 10000})
    sess._last_activity -= sess.settings.pending_timeout_minutes * 60 + 1
    assert sess.check_timeout().scores == {"A": 10000}


def test_screens_without_scores_are_ignored(monkeypatch):
    monkeypatch.setattr(session_mod, "parse_image",
                        lambda img, settings, claimed=(): ImageResult(rows=[RowResult()], bars=1))
    s = MatchSession(Settings(roster=ROSTER, data_dir=Path(".")), on_save=lambda x: None)
    assert s.process_image(Image.new("RGB", (4, 4))).ignored
    assert s.pending_count == 0
