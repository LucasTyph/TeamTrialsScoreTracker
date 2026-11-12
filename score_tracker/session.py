"""Assemble screenshots into matches (UI-independent; the app drives it)."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from .config import Settings
from .pipeline import DUPLICATE, MATCHED, UNNAMED, ImageResult, MatchAccumulator, parse_image

logger = logging.getLogger(__name__)

# A screenshot showing at least this many already-recorded characters with
# *different* scores belongs to a new match. (One differing score could just
# be an OCR misread of a re-taken screenshot.)
NEW_MATCH_MIN_CHANGED = 2


@dataclass
class SavedMatch:
    scores: dict
    distances: dict
    complete: bool
    inferred: list  # (name, score) filled in by elimination


@dataclass
class ProcessOutcome:
    result: ImageResult
    new_characters: int
    found: int
    total: int
    saved: list  # SavedMatch: a finished match and/or a flushed incomplete one
    ignored: bool = False  # nothing that looks like a Score Info screen


class MatchSession:
    """The match currently being captured.

    Thread-safe: ``process_image`` may run on a worker thread while the UI
    reads ``pending`` or calls ``save``/``discard``. ``on_save`` receives each
    SavedMatch that should be written to storage.
    """

    def __init__(self, settings: Settings, on_save):
        self.settings = settings
        self._on_save = on_save
        self._lock = threading.RLock()
        self._pending = MatchAccumulator(settings)
        self._last_activity = 0.0

    # --- state -----------------------------------------------------------

    @property
    def pending(self) -> MatchAccumulator:
        return self._pending

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    def update_settings(self, settings: Settings):
        with self._lock:
            self.settings = settings
            self._pending.settings = settings

    # --- actions ---------------------------------------------------------

    def _take(self) -> MatchAccumulator:
        pending, self._pending = self._pending, MatchAccumulator(self.settings)
        return pending

    def _emit(self, acc: MatchAccumulator) -> SavedMatch | None:
        scores = acc.final_scores()
        if not scores:
            return None
        saved = SavedMatch(scores, acc.final_distances(), acc.complete,
                           [(n, s) for n, s, _ in acc.inferred()])
        self._on_save(saved)
        return saved

    def save(self) -> SavedMatch | None:
        """Save the pending match as it is (complete or partial)."""
        with self._lock:
            acc = self._take()
        return self._emit(acc)

    def discard(self) -> int:
        with self._lock:
            count = len(self._pending)
            self._pending = MatchAccumulator(self.settings)
        return count

    def resolve(self, name, score, row=None) -> SavedMatch | None:
        """Fill in a character by hand. Saves the match if that completes it."""
        with self._lock:
            self._pending.resolve(name, score, row)
            done = self._take() if self._pending.complete else None
        return self._emit(done) if done else None

    def _is_new_match(self, result: ImageResult) -> bool:
        known = self._pending.final_scores()
        changed = [n for n, s in result.duplicates.items() if known.get(n) != s]
        if changed:
            logger.info("Already-recorded characters with different scores: %s", changed)
        return len(changed) >= NEW_MATCH_MIN_CHANGED

    def process_image(self, img) -> ProcessOutcome:
        """Parse one screenshot into the pending match."""
        with self._lock:
            claimed = dict(self._pending.final_scores())
            settings = self.settings
        # OCR runs outside the lock so the UI stays responsive.
        result = parse_image(img, settings, claimed=claimed)
        saved = []
        readable = [r for r in result.rows if r.status in (MATCHED, DUPLICATE, UNNAMED)]
        if not readable and not result.fallback_scores:
            return ProcessOutcome(result, 0, self.pending_count, len(settings.roster), saved, ignored=True)

        flushed = None
        with self._lock:
            if self._is_new_match(result):
                flushed = self._take()
        if flushed is not None:
            result = parse_image(img, settings)
            if (s := self._emit(flushed)):
                saved.append(s)

        finished = None
        with self._lock:
            before = len(self._pending)
            self._pending.add(result)
            self._last_activity = time.monotonic()
            found = len(self._pending.final_scores())
            new = len(self._pending) - before
            if self._pending.complete:
                finished = self._take()
        if finished is not None and (s := self._emit(finished)):
            saved.append(s)
        return ProcessOutcome(result, new, found, len(settings.roster), saved)

    def check_timeout(self) -> SavedMatch | None:
        """Save an incomplete match nobody added to for a while."""
        timeout = self.settings.pending_timeout_minutes * 60
        with self._lock:
            stale = len(self._pending) and time.monotonic() - self._last_activity > timeout
            acc = self._take() if stale else None
        return self._emit(acc) if acc else None
