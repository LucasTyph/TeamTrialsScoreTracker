"""Clipboard image monitoring for automatic screenshot detection."""

from __future__ import annotations

import hashlib
import logging
import threading
import time

from PIL import ImageGrab

from .config import Settings
from .notifications import notify, notify_error
from .pipeline import MatchAccumulator, parse_image

logger = logging.getLogger(__name__)

# A screenshot showing at least this many already-recorded characters with
# *different* scores belongs to a new match. (One differing score could just
# be an OCR misread of a re-taken screenshot.)
NEW_MATCH_MIN_CHANGED = 2


class ClipboardMonitor:
    """Watches the clipboard for screenshots and assembles them into matches.

    ``on_match(scores, complete, inferred)`` is called from the monitor (or
    menu) thread whenever a match should be saved. ``inferred`` is the
    ``(name, score)`` filled in by elimination, or None.
    """

    def __init__(self, settings: Settings, on_match, on_state_change=None, on_error=None):
        self._settings = settings
        self._on_match = on_match
        self._on_state_change = on_state_change or (lambda: None)
        self._on_error = on_error or (lambda msg: None)
        self._last_hash = None
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.RLock()
        self._pending = MatchAccumulator(settings.roster)
        self._last_activity = 0.0

    # --- lifecycle -------------------------------------------------------

    def start(self):
        if self.is_running:
            return
        self._stop.clear()
        # Ignore whatever image is already on the clipboard
        initial = ImageGrab.grabclipboard()
        if initial is not None and hasattr(initial, "size"):
            self._last_hash = self._image_hash(initial)
        self._thread = threading.Thread(target=self._loop, daemon=True, name="clipboard-monitor")
        self._thread.start()
        logger.info("Clipboard monitor started")

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=30)
        self._thread = None
        logger.info("Clipboard monitor stopped")

    @property
    def is_running(self):
        return self._thread is not None and self._thread.is_alive() and not self._stop.is_set()

    # --- pending match ---------------------------------------------------

    @property
    def pending_count(self):
        with self._lock:
            return len(self._pending)

    def _take_pending(self):
        """Swap out the pending match for an empty one (call with lock held)."""
        pending, self._pending = self._pending, MatchAccumulator(self._settings.roster)
        return pending

    def _emit(self, pending):
        scores = pending.final_scores()
        if scores:
            self._on_match(scores, pending.complete, pending.inferred())
        return len(scores)

    def save_partial(self):
        """Save the pending match as-is. Returns number of characters saved."""
        with self._lock:
            pending = self._take_pending()
        count = self._emit(pending)
        self._on_state_change()
        return count

    def discard_pending(self):
        with self._lock:
            count = len(self._pending)
            self._pending = MatchAccumulator(self._settings.roster)
        self._on_state_change()
        return count

    # --- internals -------------------------------------------------------

    @staticmethod
    def _image_hash(img):
        small = img.resize((50, 50)).convert("L")
        return hashlib.md5(small.tobytes()).hexdigest()

    def _is_new_match(self, result):
        changed = [n for n, s in result.duplicates.items() if self._pending.scores.get(n) != s]
        if changed:
            logger.info("Already-recorded characters with different scores: %s", changed)
        return len(changed) >= NEW_MATCH_MIN_CHANGED

    def process_image(self, img):
        """Parse one screenshot into the pending match (public for testing)."""
        logger.info("Processing image %sx%s", *img.size)
        total = len(self._settings.roster)
        with self._lock:
            claimed = dict(self._pending.scores)
        # OCR runs outside the lock so the tray menu stays responsive.
        result = parse_image(img, self._settings, claimed=claimed)

        flushed = finished = None
        with self._lock:
            if self._is_new_match(result):
                flushed = self._take_pending()
        if flushed is not None:
            result = parse_image(img, self._settings)

        if result.bars == 0 and not result.scores:
            notify_error("No score rows found in screenshot")
        else:
            with self._lock:
                self._pending.add(result)
                self._last_activity = time.monotonic()
                found = len(self._pending)
                if self._pending.complete:
                    finished = self._take_pending()

        if flushed is not None:
            count = self._emit(flushed)
            notify("Previous match incomplete", f"Saved {count}/{total} characters as a partial match")
        if finished is not None:
            self._emit(finished)
        elif result.bars or result.scores:
            extra = f", {len(result.duplicates)} already recorded" if result.duplicates else ""
            notify("Screenshot processed",
                   f"{len(result.scores)} new character(s){extra} — {found}/{total} so far")
        self._on_state_change()
        return result

    def _check_timeout(self):
        timeout = self._settings.pending_timeout_minutes * 60
        with self._lock:
            stale = len(self._pending) and time.monotonic() - self._last_activity > timeout
        if stale:
            count = self.save_partial()
            notify("Incomplete match saved",
                   f"No new screenshots for {self._settings.pending_timeout_minutes:g} min — "
                   f"saved {count}/{len(self._settings.roster)} characters")

    def _loop(self):
        while not self._stop.is_set():
            try:
                raw = ImageGrab.grabclipboard()
                if raw is not None and hasattr(raw, "size"):
                    current_hash = self._image_hash(raw)
                    if current_hash != self._last_hash:
                        self._last_hash = current_hash
                        self.process_image(raw)
                self._check_timeout()
            except Exception as e:
                logger.exception("Monitor loop error")
                self._on_error(str(e))
            self._stop.wait(1)
