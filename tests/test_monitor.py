import pytest
from PIL import Image

from score_tracker import clipboard_monitor
from score_tracker.clipboard_monitor import ClipboardMonitor
from score_tracker.config import Settings
from score_tracker.pipeline import ImageResult

ROSTER = ("A", "B", "C", "D")


@pytest.fixture
def monitor(tmp_path, monkeypatch):
    """Monitor whose parse_image returns queued results instead of running OCR."""
    monkeypatch.setattr(clipboard_monitor, "notify", lambda *a: None)
    monkeypatch.setattr(clipboard_monitor, "notify_error", lambda *a: None)
    saved = []
    results = []

    def fake_parse(img, settings, claimed=()):
        full = results[0]
        if not claimed:
            results.pop(0)
            return ImageResult(scores=dict(full), bars=len(full))
        scores = {n: s for n, s in full.items() if n not in claimed}
        dups = {n: s for n, s in full.items() if n in claimed}
        if not dups or all(claimed[n] == s for n, s in dups.items()):
            results.pop(0)
        return ImageResult(scores=scores, duplicates=dups, bars=len(full))

    monkeypatch.setattr(clipboard_monitor, "parse_image", fake_parse)
    m = ClipboardMonitor(Settings(roster=ROSTER, data_dir=tmp_path),
                         on_match=lambda *args: saved.append(args))
    m.feed = lambda scores: (results.append(scores), m.process_image(Image.new("RGB", (4, 4))))
    m.saved = saved
    return m


def test_two_screenshots_make_one_match(monitor):
    monitor.feed({"A": 10000, "B": 20000})
    assert monitor.saved == [] and monitor.pending_count == 2
    monitor.feed({"B": 20000, "C": 30000, "D": 40000})  # overlaps on B
    assert monitor.saved == [({"A": 10000, "B": 20000, "C": 30000, "D": 40000}, True, None)]
    assert monitor.pending_count == 0


def test_new_match_flushes_incomplete_previous_one(monitor):
    monitor.feed({"A": 10000, "B": 20000})
    # Next match's screenshot: same characters, different scores
    monitor.feed({"A": 11000, "B": 21000, "C": 31000})
    assert monitor.saved == [({"A": 10000, "B": 20000}, False, None)]
    assert monitor.pending_count == 3


def test_retaken_screenshot_is_not_a_new_match(monitor):
    monitor.feed({"A": 10000, "B": 20000})
    monitor.feed({"A": 10000, "B": 20000})
    assert monitor.saved == [] and monitor.pending_count == 2


def test_save_partial_and_discard(monitor):
    monitor.feed({"A": 10000})
    assert monitor.save_partial() == 1
    assert monitor.saved == [({"A": 10000}, False, None)]
    monitor.feed({"B": 20000})
    assert monitor.discard_pending() == 1
    assert monitor.pending_count == 0 and len(monitor.saved) == 1


def test_idle_pending_match_is_saved_after_timeout(monitor, monkeypatch):
    monitor.feed({"A": 10000})
    monitor._last_activity -= monitor._settings.pending_timeout_minutes * 60 + 1
    monitor._check_timeout()
    assert monitor.saved == [({"A": 10000}, False, None)]
