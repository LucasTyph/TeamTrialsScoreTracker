"""Screenshot → scores: the one parsing pipeline used by CLI, tray and tests."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from . import ocr
from .config import Settings
from .parser import _score_name, _split_entries, find_score, parse_scores, parse_single_match

logger = logging.getLogger(__name__)


@dataclass
class ImageResult:
    scores: dict[str, int] = field(default_factory=dict)
    # Scores read from crops where no roster name could be read.
    orphan_scores: list[int] = field(default_factory=list)
    # Crops showing a character already recorded earlier in this match.
    duplicates: dict[str, int] = field(default_factory=dict)
    bars: int = 0


def _parse_crop(crop, settings: Settings, claimed, verbose=False):
    """Try each preprocessing variant until one yields a name and score.

    Returns (scores, orphan_score, duplicate) where at most one is non-empty.
    """
    roster = settings.roster
    args = (settings.row_tolerance, settings.fuzzy_match_threshold)
    orphan = None
    for variant, prepare in ocr.PREPROCESS_VARIANTS:
        data = ocr.extract_data(prepare(crop))
        if verbose:
            print(f"    [{variant}]")
        # Match against the whole roster first: if the best match was already
        # recorded, this row is a duplicate (overlapping or re-taken
        # screenshot). Excluding recorded names up front would instead let a
        # similar name win, e.g. "Sakura Chiyono O" → "Sakura Bakushin O".
        best = parse_single_match(data, roster, *args, verbose=verbose)
        if best:
            (name, score), = best.items()
            if name not in claimed:
                return best, None, {}
            alt = parse_single_match(data, roster, *args, claimed)
            if alt and _name_ratio(data, next(iter(alt))) == _name_ratio(data, name):
                return alt, None, {}  # tie: prefer the character not yet recorded
            return {}, None, best
        if orphan is None:
            orphan = find_score(data, settings.row_tolerance)
    return {}, orphan, {}


def _name_ratio(ocr_data, name):
    text_entries, _ = _split_entries(ocr_data)
    return _score_name(name, text_entries)[0]


def parse_image(img, settings: Settings, claimed=(), verbose=False) -> ImageResult:
    """Parse every character row (one per green bar) in a screenshot.

    ``claimed`` holds characters already recorded for this match; they are
    reported as duplicates instead of being matched again.
    """
    claimed = set(claimed)
    bars = ocr.detect_green_bars(img, settings.min_bar_width)
    result = ImageResult(bars=len(bars))

    if not bars:
        logger.info("No green bars detected; falling back to full-image OCR")
        scores = parse_scores(ocr.extract_data(img), settings.roster,
                              settings.row_tolerance, settings.fuzzy_match_threshold)
        result.duplicates = {n: s for n, s in scores.items() if n in claimed}
        result.scores = {n: s for n, s in scores.items() if n not in claimed}
        return result

    for i, (bar_start, bar_end) in enumerate(bars):
        crop = ocr.crop_above_bar(img, bar_start, bar_end, settings.crop_above_bar)
        if crop is None:
            continue
        if verbose:
            print(f"  Bar {i + 1}: y={bar_start}-{bar_end}, crop={crop.size[0]}x{crop.size[1]}")
        scores, orphan, dup = _parse_crop(crop, settings, claimed, verbose)
        logger.info("Bar y=%d-%d: matched=%s orphan=%s duplicate=%s",
                    bar_start, bar_end, scores, orphan, dup)
        result.scores.update(scores)
        result.duplicates.update(dup)
        claimed.update(scores)
        if orphan is not None:
            result.orphan_scores.append(orphan)
    return result


@dataclass
class MatchAccumulator:
    """Collects scores across the screenshots of one match."""

    roster: tuple[str, ...]
    scores: dict[str, int] = field(default_factory=dict)
    orphan_scores: list[int] = field(default_factory=list)

    def add(self, result: ImageResult):
        self.scores.update(result.scores)
        known = set(self.scores.values())
        for s in result.orphan_scores:
            if s not in known and s not in self.orphan_scores:
                self.orphan_scores.append(s)

    @property
    def missing(self) -> list[str]:
        return [n for n in self.roster if n not in self.scores]

    def inferred(self) -> tuple[str, int] | None:
        """If exactly one character is missing and exactly one row's score was
        read without its name, that score must belong to the missing character."""
        unmatched = [s for s in self.orphan_scores if s not in self.scores.values()]
        if len(self.missing) == 1 and len(unmatched) == 1:
            return self.missing[0], unmatched[0]
        return None

    def final_scores(self) -> dict[str, int]:
        scores = dict(self.scores)
        guess = self.inferred()
        if guess:
            scores[guess[0]] = guess[1]
        return scores

    @property
    def complete(self) -> bool:
        return len(self.final_scores()) >= len(self.roster)

    def __len__(self):
        return len(self.scores)
