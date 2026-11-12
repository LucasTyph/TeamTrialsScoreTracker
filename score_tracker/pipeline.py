"""Screenshot → scores: the one parsing pipeline used by the app, CLI and tests."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from . import ocr
from .config import Settings
from .parser import (
    _score_name,
    _split_entries,
    find_score,
    parse_scores,
    parse_single_match,
    read_name_text,
)

logger = logging.getLogger(__name__)

MATCHED = "matched"  # name and score read
DUPLICATE = "duplicate"  # a character already recorded for this match
UNNAMED = "unnamed"  # score read, name unreadable
UNREADABLE = "unreadable"  # no valid score read


@dataclass
class RowResult:
    """One character row of a Score Info screenshot."""

    crop: object = None  # PIL image of the name/score band, for review
    distance: str | None = None  # from the badge under the portrait
    name: str | None = None  # roster name, when matched
    score: int | None = None
    read_text: str | None = None  # name text as OCR read it (no roster)
    status: str = UNREADABLE


@dataclass
class ImageResult:
    rows: list[RowResult] = field(default_factory=list)
    bars: int = 0
    # Fallback path (no bars found): full-image OCR, no per-row data
    fallback_scores: dict[str, int] = field(default_factory=dict)

    @property
    def scores(self) -> dict[str, int]:
        found = {r.name: r.score for r in self.rows if r.status == MATCHED}
        return found or dict(self.fallback_scores)

    @property
    def duplicates(self) -> dict[str, int]:
        return {r.name: r.score for r in self.rows if r.status == DUPLICATE}

    @property
    def orphan_scores(self) -> list[int]:
        return [r.score for r in self.rows if r.status == UNNAMED]

    @property
    def distances(self) -> dict[str, str]:
        return {r.name: r.distance for r in self.rows if r.name and r.distance}


def _name_ratio(ocr_data, name):
    text_entries, _ = _split_entries(ocr_data)
    return _score_name(name, text_entries)[0]


def _match_row(data, settings: Settings, distance, claimed, verbose=False):
    """(status, name, score) for one OCR result of a row."""
    args = (settings.row_tolerance, settings.fuzzy_match_threshold)
    roster = settings.roster
    # The badge tells us the team: try that team's members first.
    team = settings.team_members(distance) if distance else []
    candidate_sets = [team, roster] if team else [roster]
    for names in candidate_sets:
        # Match against all candidates first: if the best match was already
        # recorded, this row is a duplicate (overlapping or re-taken
        # screenshot). Excluding recorded names up front would instead let a
        # similar name win, e.g. "Sakura Chiyono O" → "Sakura Bakushin O".
        best = parse_single_match(data, names, *args, verbose=verbose)
        if not best:
            continue
        (name, score), = best.items()
        if name not in claimed:
            return MATCHED, name, score
        alt = parse_single_match(data, names, *args, claimed)
        if alt and _name_ratio(data, next(iter(alt))) == _name_ratio(data, name):
            (alt_name, alt_score), = alt.items()
            return MATCHED, alt_name, alt_score  # tie: prefer the one not yet recorded
        return DUPLICATE, name, score
    score = find_score(data, settings.row_tolerance)
    return (UNNAMED if score is not None else UNREADABLE), None, score


def _parse_row(crop, settings: Settings, distance, claimed, verbose=False) -> RowResult:
    """Try each preprocessing variant until one yields a name and score."""
    row = RowResult(crop=crop, distance=distance)
    for variant, prepare in ocr.PREPROCESS_VARIANTS:
        data = ocr.extract_data(prepare(crop))
        if verbose:
            print(f"    [{variant}]")
        status, name, score = _match_row(data, settings, distance, claimed, verbose)
        if row.read_text is None:
            row.read_text = read_name_text(data, settings.row_tolerance)
        if row.score is None and score is not None:
            row.score = score
        if status in (MATCHED, DUPLICATE):
            row.status, row.name, row.score = status, name, score
            return row
        if status == UNNAMED:
            row.status = UNNAMED
    return row


def parse_image(img, settings: Settings, claimed=(), verbose=False) -> ImageResult:
    """Parse every character row (one per progress bar) in a screenshot.

    ``claimed`` holds characters already recorded for this match; they are
    reported as duplicates instead of being matched again.
    """
    claimed = set(claimed)
    bars = ocr.find_score_rows(img, settings.min_bar_width)
    result = ImageResult(bars=len(bars))

    if not bars:
        logger.info("No score bars detected; falling back to full-image OCR")
        scores = parse_scores(ocr.extract_data(img), settings.roster,
                              settings.row_tolerance, settings.fuzzy_match_threshold)
        result.fallback_scores = {n: s for n, s in scores.items() if n not in claimed}
        return result

    for i, bar in enumerate(bars):
        crop = ocr.text_crop(img, bar)
        if crop is None:
            continue
        badge = ocr.badge_crop(img, bar)
        distance = ocr.read_distance(badge) if badge is not None else None
        if verbose:
            print(f"  Row {i + 1}: y={bar.y0}, distance={distance}")
        row = _parse_row(crop, settings, distance, claimed, verbose)
        if (bar.virtual or bar.covered) and row.status == UNREADABLE:
            continue  # nothing usable on a half-visible row
        logger.info("Row %d: %s name=%s score=%s distance=%s read=%r",
                    i + 1, row.status, row.name, row.score, row.distance, row.read_text)
        if row.status == MATCHED:
            claimed.add(row.name)
        result.rows.append(row)
    return result


def detect_roster(images, settings: Settings) -> list[tuple[str, str | None]]:
    """(name text, distance) for each row read from screenshots, no roster needed."""
    seen, out = set(), []
    for img in images:
        for bar in ocr.find_score_rows(img, settings.min_bar_width):
            crop = ocr.text_crop(img, bar)
            if crop is None:
                continue
            badge = ocr.badge_crop(img, bar)
            distance = ocr.read_distance(badge) if badge is not None else None
            for _, prepare in ocr.PREPROCESS_VARIANTS:
                name = read_name_text(ocr.extract_data(prepare(crop)), settings.row_tolerance)
                if name:
                    break
            if name and name not in seen:
                seen.add(name)
                out.append((name, distance))
    return out


@dataclass
class MatchAccumulator:
    """Collects scores across the screenshots of one match."""

    settings: Settings
    scores: dict[str, int] = field(default_factory=dict)
    distances: dict[str, str] = field(default_factory=dict)
    # Rows whose name couldn't be read (score may or may not be known)
    unnamed: list[RowResult] = field(default_factory=list)
    # Scores entered by hand in the review window
    manual: dict[str, int] = field(default_factory=dict)

    @property
    def roster(self) -> tuple[str, ...]:
        return self.settings.roster

    def add(self, result: ImageResult):
        self.scores.update(result.scores)
        self.distances.update(result.distances)
        known = set(self.scores.values())
        for row in result.rows:
            if row.status not in (UNNAMED, UNREADABLE):
                continue
            # A row already recorded from an overlapping screenshot
            if row.score is not None and (row.score in known or
                                          any(r.score == row.score for r in self.unnamed)):
                continue
            self.unnamed.append(row)

    def resolve(self, name, score, row: RowResult | None = None):
        """Assign a score by hand (from the review window)."""
        self.manual[name] = int(score)
        if row is not None and row in self.unnamed:
            self.unnamed.remove(row)
            if row.distance:
                self.distances[name] = row.distance

    def discard_row(self, row: RowResult):
        if row in self.unnamed:
            self.unnamed.remove(row)

    def _known(self) -> dict[str, int]:
        return {**self.scores, **self.manual}

    @property
    def missing(self) -> list[str]:
        known = self._known()
        return [n for n in self.roster if n not in known]

    def inferred(self) -> list[tuple[str, int, RowResult]]:
        """Unnamed rows that can only belong to one character.

        Within each team (from the row's distance badge) and then overall:
        if exactly one character is missing and exactly one unnamed row with a
        score is left, they belong together.
        """
        known = self._known()
        missing = [n for n in self.roster if n not in known]
        rows = [r for r in self.unnamed if r.score is not None]
        out = []
        teams = self.settings.teams
        for distance in {r.distance for r in rows if r.distance}:
            team_missing = [n for n in missing if teams.get(n) == distance]
            team_rows = [r for r in rows if r.distance == distance]
            if len(team_missing) == 1 and len(team_rows) == 1:
                out.append((team_missing[0], team_rows[0].score, team_rows[0]))
                missing.remove(team_missing[0])
                rows.remove(team_rows[0])
        if len(missing) == 1 and len(rows) == 1:
            out.append((missing[0], rows[0].score, rows[0]))
        return out

    def final_scores(self) -> dict[str, int]:
        scores = self._known()
        for name, score, _ in self.inferred():
            scores[name] = score
        return scores

    def final_distances(self) -> dict[str, str]:
        out = {n: self.settings.teams[n] for n in self.final_scores() if n in self.settings.teams}
        out.update(self.distances)
        for name, _, row in self.inferred():
            if row.distance:
                out[name] = row.distance
        return out

    @property
    def needs_review(self) -> list[RowResult]:
        inferred_rows = [r for _, _, r in self.inferred()]
        return [r for r in self.unnamed if r not in inferred_rows]

    @property
    def complete(self) -> bool:
        return bool(self.roster) and len(self.final_scores()) >= len(self.roster)

    def __len__(self):
        return len(self._known())
