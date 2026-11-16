"""The app's screenshot jobs: results always come back, and cancelling works."""

import threading
import time

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication  # noqa: E402

from score_tracker.config import Settings  # noqa: E402
from score_tracker.gui.app import TrackerApp, _make_app  # noqa: E402
from score_tracker.pipeline import ImageResult  # noqa: E402
from score_tracker.session import ProcessOutcome  # noqa: E402

TEAMS = {"A": "Sprint", "B": "Sprint", "C": "Sprint"}


@pytest.fixture
def tracker(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = _make_app()
    t = TrackerApp(app, Settings(roster=tuple(TEAMS), teams=TEAMS, data_dir=tmp_path))
    yield t
    t.shutdown()


def _wait(condition, seconds=10):
    end = time.monotonic() + seconds
    while time.monotonic() < end and not condition():
        QCoreApplication.processEvents()
        time.sleep(0.01)
    return condition()


def test_results_arrive_even_when_the_ui_is_busy(tracker, monkeypatch):
    """Regression: results were lost (stuck on "Reading…") when the UI thread was busy."""
    handled = []

    def fake_read(img):
        return ProcessOutcome(ImageResult(), 0, 0, 3, [], ignored=True)

    monkeypatch.setattr(tracker.session, "process_image", fake_read)
    monkeypatch.setattr(tracker, "notify", lambda *a, **k: handled.append(a))
    for _ in range(20):
        tracker.process(object())
    time.sleep(0.5)  # jobs finish (and are deleted) while no events are processed
    assert _wait(lambda: tracker.busy == 0)
    assert len(handled) == 20
    assert not tracker.window.match_page.cancel_btn.isVisibleTo(tracker.window)


def test_cancel_stops_a_stuck_read(tracker, monkeypatch):
    release = threading.Event()
    notes = []

    def stuck_read(img):
        release.wait(5)  # like a hung OCR call
        return ProcessOutcome(ImageResult(), 0, 0, 3, [], ignored=True)

    monkeypatch.setattr(tracker.session, "process_image", stuck_read)
    monkeypatch.setattr(tracker, "notify", lambda title, *a, **k: notes.append(title))
    tracker.process(object())
    tracker.process(object())  # queued behind it
    page = tracker.window.match_page
    assert tracker.busy == 2 and page.cancel_btn.isVisibleTo(tracker.window)
    assert not page.capture_btn.isEnabled()

    tracker.cancel_captures()
    assert tracker.busy == 0 and notes == ["Capture cancelled"]
    assert page.capture_btn.isEnabled() and not page.cancel_btn.isVisibleTo(tracker.window)

    # New captures don't wait for the stuck one
    monkeypatch.setattr(tracker.session, "process_image",
                        lambda img: ProcessOutcome(ImageResult(), 0, 0, 3, [], ignored=True))
    tracker.process(object())
    assert _wait(lambda: tracker.busy == 0, seconds=3)
    assert notes[-1] == "No scores found"
    release.set()
    # The stuck job's result is ignored when it finally finishes
    time.sleep(0.2)
    QCoreApplication.processEvents()
    assert notes.count("No scores found") == 1
