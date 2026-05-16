"""Parse OCR output into structured character scores."""

from difflib import SequenceMatcher


def _is_number(text):
    cleaned = text.replace(",", "").replace(".", "").replace(" ", "")
    return cleaned.isdigit() and len(cleaned) > 0


def _clean_number(text):
    return int(text.replace(",", "").replace(" ", ""))


def _score_name(name, text_entries):
    """Score how well a character name matches the words in a crop.

    Returns (score, best_entry) where score is 0.0-1.0 based on what
    fraction of the name's word-parts are found in the crop.  Short
    parts (< 3 chars) require an exact standalone word match to avoid
    spurious hits like 'O' matching 'Oguri' or 'Condor'.
    """
    name_parts = name.lower().split()
    if not name_parts:
        return 0.0, None

    matched = 0
    best_entry = None

    for part in name_parts:
        if len(part) < 3:
            for e in text_entries:
                if e["text"].lower() == part:
                    matched += 1
                    if best_entry is None:
                        best_entry = e
                    break
        else:
            for e in text_entries:
                w = e["text"].lower()
                if part == w or part in w or w in part:
                    matched += 1
                    if best_entry is None:
                        best_entry = e
                    break

    return matched / len(name_parts), best_entry


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

        score_entry = _locate_score(match_entry, numbers, row_tolerance)
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
    entries = _extract_entries(ocr_data)
    if not entries:
        return {}

    numbers = [e for e in entries if _is_number(e["text"])]
    text_entries = [e for e in entries if not _is_number(e["text"])]

    results = {}
    for name in character_names:
        ratio, match = _score_name(name, text_entries)
        if ratio < fuzzy_threshold:
            continue
        score_entry = _locate_score(match, numbers, row_tolerance)
        if score_entry is not None:
            results[name] = _clean_number(score_entry["text"])

    return results
