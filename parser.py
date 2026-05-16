"""Parse OCR output into structured character scores."""

import re
from difflib import SequenceMatcher


def _is_number(text):
    cleaned = text.replace(",", "").replace(".", "").replace(" ", "")
    return cleaned.isdigit() and len(cleaned) > 0


def _clean_number(text):
    return int(text.replace(",", "").replace(" ", "").rstrip(".").lstrip("."))


def _extract_numeric_fragments(text_entries, numbers):
    """Pull digit sequences out of text entries into the numbers list.

    OCR sometimes fuses a leading digit with following text (e.g. "6pts"
    instead of separate "6" and "pts").  These fragments are needed for
    the score-merge step.

    The X position of each extracted fragment is estimated from its
    character offset inside the parent text so that left/right ordering
    is correct even for trailing digits like "pts6".
    """
    for e in text_entries:
        text = e["text"]
        char_width = e["w"] / max(len(text), 1)
        for m in re.finditer(r"\d[\d,]*\d|\d", text):
            offset = m.start() * char_width
            numbers.append(
                {
                    "text": m.group(),
                    "x": e["x"] + offset,
                    "y": e["y"],
                    "w": len(m.group()) * char_width,
                    "h": e["h"],
                    "_extracted": True,
                }
            )


def _score_name(name, text_entries):
    """Score how well a character name matches the words in a crop.

    Returns (score, best_entry) where score is 0.0-1.0 based on what
    fraction of the name's word-parts are found in the crop.  Short
    parts (< 3 chars) require an exact standalone word match to avoid
    spurious hits like 'O' matching 'Oguri' or 'Condor'.
    """
    name_parts = name.lower().split()
    name_no_space = name.lower().replace(" ", "")
    if not name_parts:
        return 0.0, None

    matched = 0
    best_entry = None

    for part in name_parts:
        for e in text_entries:
            w = e["text"].lower()
            if _part_matches(part, w):
                matched += 1
                if best_entry is None:
                    best_entry = e
                break
        else:
            # Part not found as substring — try matching the whole
            # spaceless name against the OCR word (handles "GoldShip"
            # vs "Gold Ship").
            if w == name_no_space:
                matched += 1
                if best_entry is None:
                    best_entry = e
                break

    return matched / len(name_parts), best_entry


def _part_matches(part, word):
    """Check if a name part matches an OCR word, avoiding short-substring traps."""
    if part == word:
        return True
    if len(part) < 3 and len(word) < 3:
        return False
    if len(part) < 3:
        return word == part
    if len(word) < 3:
        return part == word
    return part in word or word in part


SCORE_MIN = 10_000
SCORE_MAX = 200_000


def _find_score_number(numbers, row_tolerance):
    """Find the score number from a list of detected numbers.

    Scores are always in [10_000, 200_000].  Strategy:
    1. Return any single number already in range (fast path).
    2. Merge adjacent small numbers on the same row; return if merged
       value falls in range.  Tries X-sorted order first, then reverse
       (handles trailing-digit OCR like "pts6").
    3. Otherwise return None (no valid score found).
    """
    if not numbers:
        return None

    # Fast path: a single number already in the valid range
    for n in numbers:
        val = _clean_number(n["text"])
        if SCORE_MIN <= val <= SCORE_MAX:
            return n

    # Merge adjacent small numbers on the same row
    numbers.sort(key=lambda n: n["x"])
    groups = []
    current = [numbers[0]]

    has_extracted = any(n.get("_extracted") for n in numbers)
    has_regular = any(not n.get("_extracted") for n in numbers)
    # When both extracted fragments and regular numbers exist on the
    # same row, the fragment X position is unreliable — use a much
    # wider gap tolerance so they still get grouped.
    merge_gap = 100 if (has_extracted and has_regular) else 20

    for n in numbers[1:]:
        prev = current[-1]
        same_row = abs((n["y"] + n["h"] / 2) - (prev["y"] + prev["h"] / 2)) <= row_tolerance
        close = n["x"] - (prev["x"] + prev["w"]) < merge_gap

        if same_row and close:
            current.append(n)
        else:
            groups.append(current)
            current = [n]
    groups.append(current)

    for group in groups:
        if len(group) < 2:
            continue

        extracted = [n for n in group if n.get("_extracted")]
        others = [n for n in group if not n.get("_extracted")]
        try_reverse = False
        if extracted and others:
            max_extracted_x = max(n["x"] for n in extracted)
            min_other_x = min(n["x"] for n in others)
            try_reverse = max_extracted_x > min_other_x

        orders = [list(reversed(group)), group] if try_reverse else [group, list(reversed(group))]

        for order in orders:
            merged_text = "".join(e["text"] for e in order)
            try:
                val = _clean_number(merged_text)
            except ValueError:
                continue
            if SCORE_MIN <= val <= SCORE_MAX:
                return {
                    "text": merged_text,
                    "x": order[0]["x"],
                    "y": order[0]["y"],
                    "w": order[-1]["x"] + order[-1]["w"] - order[0]["x"],
                    "h": max(e["h"] for e in order),
                }

    return None


def _locate_score(text_entry, numbers, row_tolerance):
    """Find the nearest number to the right (same row), or below the text."""
    y_center = text_entry["y"] + text_entry["h"] / 2
    right_edge = text_entry["x"] + text_entry["w"]
    text_bottom = text_entry["y"] + text_entry["h"]

    same_row = []
    for n in numbers:
        n_y_center = n["y"] + n["h"] / 2
        if abs(y_center - n_y_center) <= row_tolerance and n["x"] >= right_edge:
            same_row.append((n["x"] - right_edge, n))

    if same_row:
        same_row.sort(key=lambda c: c[0])
        return same_row[0][1]

    below = []
    for n in numbers:
        if n["y"] > text_bottom and (n["y"] - text_bottom) <= row_tolerance * 2:
            x_dist = n["x"] - right_edge
            if x_dist > -50:
                below.append(((n["y"] - text_bottom) + max(0, x_dist) * 0.5, n))

    if below:
        below.sort(key=lambda c: c[0])
        return below[0][1]

    return None


def _extract_entries(ocr_data):
    """Pull word-level entries from OCR data."""
    entries = []
    for i, text in enumerate(ocr_data["text"]):
        if ocr_data["level"][i] != 5:
            continue
        text = text.strip()
        if not text:
            continue
        entries.append(
            {
                "text": text,
                "x": ocr_data["left"][i],
                "y": ocr_data["top"][i],
                "w": ocr_data["width"][i],
                "h": ocr_data["height"][i],
            }
        )
    return entries


def parse_single_match(ocr_data, character_names, row_tolerance, fuzzy_threshold, claimed=None, verbose=False):
    """Parse one crop and return at most ONE (name, score) pair.

    Each crop sits above a single green bar, so it should contain exactly
    one character entry.  We find the best-matching name and its score.
    """
    if claimed is None:
        claimed = set()
    entries = _extract_entries(ocr_data)
    if not entries:
        return {}

    numbers = [e for e in entries if _is_number(e["text"])]
    text_entries = [e for e in entries if not _is_number(e["text"])]

    # OCR sometimes fuses digits with text (e.g. "6pts").  Extract those
    # fragments into the numbers list so the merge step can use them.
    _extract_numeric_fragments(text_entries, numbers)

    if verbose:
        print(f"    Words: {[e['text'] for e in text_entries]}")
        print(f"    Numbers: {[e['text'] for e in numbers]}")

    best_name = None
    best_score = None
    best_ratio = 0

    candidates = []
    for name in character_names:
        if name in claimed:
            continue
        ratio, match_entry = _score_name(name, text_entries)
        if ratio < fuzzy_threshold:
            continue

        score_entry = _find_score_number(numbers, row_tolerance)
        if score_entry is None:
            continue

        candidates.append((ratio, name, _clean_number(score_entry["text"]), match_entry["text"]))

        if ratio > best_ratio:
            best_ratio = ratio
            best_name = name
            best_score = _clean_number(score_entry["text"])

    if verbose and candidates:
        candidates.sort(key=lambda c: c[0], reverse=True)
        for ratio, name, score, matched_text in candidates:
            marker = ">>>" if name == best_name else "   "
            print(f"    {marker} {ratio:.2f}  {name:20s} score={score}  (matched word: '{matched_text}')")

    if best_name is not None:
        return {best_name: best_score}
    return {}


def parse_scores(ocr_data, character_names, row_tolerance, fuzzy_threshold):
    """Fallback: parse full-image OCR (used when no green bars detected)."""
    entries = _extract_entries(ocr_data)
    if not entries:
        return {}

    all_numbers = [e for e in entries if _is_number(e["text"])]
    text_entries = [e for e in entries if not _is_number(e["text"])]

    # Extract numeric fragments from words
    _extract_numeric_fragments(text_entries, all_numbers)

    # Build a list of valid score numbers using range-aware merging
    valid_scores = _collect_valid_scores(all_numbers, row_tolerance)

    results = {}
    for name in character_names:
        ratio, match = _score_name(name, text_entries)
        if ratio < fuzzy_threshold:
            continue
        score_entry = _locate_score(match, valid_scores, row_tolerance)
        if score_entry is not None:
            results[name] = _clean_number(score_entry["text"])

    return results


def _collect_valid_scores(numbers, row_tolerance):
    """Return only numbers that are valid scores (10k–200k), merging fragments."""
    if not numbers:
        return []

    valid = []
    for n in numbers:
        try:
            val = _clean_number(n["text"])
        except ValueError:
            continue
        if SCORE_MIN <= val <= SCORE_MAX:
            valid.append(n)

    if valid:
        return valid

    # No single number in range — try merging adjacent fragments
    numbers.sort(key=lambda n: n["x"])
    groups = []
    current = [numbers[0]]
    has_extracted = any(n.get("_extracted") for n in numbers)
    has_regular = any(not n.get("_extracted") for n in numbers)
    merge_gap = 100 if (has_extracted and has_regular) else 20
    for n in numbers[1:]:
        prev = current[-1]
        same_row = abs((n["y"] + n["h"] / 2) - (prev["y"] + prev["h"] / 2)) <= row_tolerance
        close = n["x"] - (prev["x"] + prev["w"]) < merge_gap
        if same_row and close:
            current.append(n)
        else:
            groups.append(current)
            current = [n]
    groups.append(current)

    for group in groups:
        if len(group) < 2:
            continue
        extracted = [n for n in group if n.get("_extracted")]
        others = [n for n in group if not n.get("_extracted")]
        try_reverse = False
        if extracted and others:
            max_extracted_x = max(n["x"] for n in extracted)
            min_other_x = min(n["x"] for n in others)
            try_reverse = max_extracted_x > min_other_x
        orders = [list(reversed(group)), group] if try_reverse else [group, list(reversed(group))]
        for order in orders:
            merged_text = "".join(e["text"] for e in order)
            try:
                val = _clean_number(merged_text)
            except ValueError:
                continue
            if SCORE_MIN <= val <= SCORE_MAX:
                valid.append({
                    "text": merged_text,
                    "x": order[0]["x"],
                    "y": order[0]["y"],
                    "w": order[-1]["x"] + order[-1]["w"] - order[0]["x"],
                    "h": max(e["h"] for e in order),
                })
                break

    return valid
