"""Parse OCR output into structured character scores."""

from difflib import SequenceMatcher


def _is_number(text):
    cleaned = text.replace(",", "").replace(".", "").replace(" ", "")
    return cleaned.isdigit() and len(cleaned) > 0


def _clean_number(text):
    return int(text.replace(",", "").replace(" ", ""))


def _find_best_text_match(name, text_entries, fuzzy_threshold):
    """Find the text entry that best matches a character name."""
    name_lower = name.lower()
    name_parts = name_lower.split()

    best_entry = None
    best_ratio = 0

    for entry in text_entries:
        w_lower = entry["text"].lower()

        if w_lower == name_lower:
            return entry

        all_parts_in_row = all(p in w_lower for p in name_parts)
        is_substring = w_lower in name_lower or name_lower in w_lower

        if is_substring or all_parts_in_row:
            ratio = 0.9
            if ratio > best_ratio:
                best_ratio = ratio
                best_entry = entry
            continue

        for part in name_parts:
            if w_lower == part or part in w_lower or w_lower in part:
                ratio = 0.8
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_entry = entry

        ratio = SequenceMatcher(None, w_lower, name_lower).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            if ratio >= fuzzy_threshold:
                best_entry = entry

    return best_entry if best_ratio >= fuzzy_threshold else None


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


def parse_scores(ocr_data, character_names, row_tolerance, fuzzy_threshold):
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

    if not entries:
        return {}

    numbers = [e for e in entries if _is_number(e["text"])]
    text_entries = [e for e in entries if not _is_number(e["text"])]

    results = {}
    for name in character_names:
        match = _find_best_text_match(name, text_entries, fuzzy_threshold)
        if match is None:
            continue

        score_entry = _locate_score(match, numbers, row_tolerance)
        if score_entry is not None:
            results[name] = _clean_number(score_entry["text"])

    return results
