"""Main entry point for the score extraction system.

Usage:
    python main.py            Record a new match (two screenshots)
    python main.py --analyze  Show performance analysis
    python main.py --debug    Show OCR output from clipboard image
"""

import sys

from config import (
    ADJUSTED_SCORE_K,
    CHARACTER_NAMES,
    CROP_ABOVE_BAR,
    CSV_FILENAME,
    FUZZY_MATCH_THRESHOLD,
    ROW_TOLERANCE,
)
from ocr import (
    crop_above_bar,
    detect_green_bars,
    extract_data,
    extract_text,
    grab_clipboard,
)
from parser import parse_scores
from storage import append_match, load_data
from analysis import full_analysis


def _parse_image(img):
    """Parse scores from an image using green-bar splitting."""
    bars = detect_green_bars(img)

    if not bars:
        print("  No green bars detected — falling back to full-image OCR")
        ocr_data = extract_data(img)
        return parse_scores(ocr_data, CHARACTER_NAMES, ROW_TOLERANCE, FUZZY_MATCH_THRESHOLD)

    results = {}
    for i, (bar_start, bar_end) in enumerate(bars):
        crop = crop_above_bar(img, bar_start, bar_end, CROP_ABOVE_BAR)
        if crop is None:
            continue
        ocr_data = extract_data(crop)
        crop_scores = parse_scores(
            ocr_data, CHARACTER_NAMES, ROW_TOLERANCE, FUZZY_MATCH_THRESHOLD
        )
        results.update(crop_scores)

    return results


def _process_screenshot(label):
    input(f"Take {label} screenshot with Win+Shift+S, then press Enter...")
    img = grab_clipboard()
    if img is None:
        print("  No image on clipboard.")
        return None
    print(f"  Captured {img.size[0]}x{img.size[1]}")
    return img


def _show_ocr_summary(ocr_data, label):
    """Print all detected words and positions from OCR."""
    texts = []
    for i, text in enumerate(ocr_data["text"]):
        if ocr_data["level"][i] != 5:
            continue
        text = text.strip()
        if not text:
            continue
        y = ocr_data["top"][i]
        x = ocr_data["left"][i]
        texts.append((y, x, text))

    texts.sort()
    print(f"\n  --- OCR detected words ({label}) ---")
    for y, x, t in texts:
        print(f"  {y:4d},{x:4d}  {t}")
    print(f"  --- {len(texts)} words total ---")


def cmd_record():
    print("Match Score Recorder")
    print("====================")
    print()
    print("You will take two screenshots (Win+Shift+S) for one match.")
    print()

    img1 = _process_screenshot("first")
    if img1 is None:
        return
    scores1 = _parse_image(img1)

    img2 = _process_screenshot("second")
    if img2 is None:
        return
    scores2 = _parse_image(img2)

    print(f"\n  Screenshot 1 matched: {len(scores1)} characters")
    for name, val in sorted(scores1.items()):
        print(f"    {name:20s} {val}")

    print(f"\n  Screenshot 2 matched: {len(scores2)} characters")
    for name, val in sorted(scores2.items()):
        print(f"    {name:20s} {val}")

    combined = {}
    combined.update(scores1)
    combined.update(scores2)

    total = sum(v for v in combined.values() if v is not None)
    print(f"\n  Combined: {len(combined)}/{len(CHARACTER_NAMES)} characters  (total: {total})")
    for name in CHARACTER_NAMES:
        val = combined.get(name, None)
        label = str(val) if val is not None else "MISSING"
        print(f"    {name:20s} {label}")

    if len(combined) == len(CHARACTER_NAMES):
        row = append_match(combined)
        print(f"\nSaved to {CSV_FILENAME}")
    else:
        missing = [n for n in CHARACTER_NAMES if n not in combined]
        print(f"\nWarning: {len(missing)} character(s) not found: {', '.join(missing)}")
        save = input("Save partial data anyway? (y/N): ").strip().lower()
        if save == "y":
            row = append_match(combined)
            print(f"Saved to {CSV_FILENAME}")


def cmd_debug():
    """Run OCR on whatever is on the clipboard and show all detected text."""
    print("OCR Debug Mode")
    print("==============")
    print("Take a screenshot with Win+Shift+S, then press Enter...")
    input()
    img = grab_clipboard()
    if img is None:
        print("No image on clipboard.")
        return
    print(f"Image: {img.size[0]}x{img.size[1]}\n")

    bars = detect_green_bars(img)
    print(f"Detected {len(bars)} green bar(s):")
    for i, (bar_start, bar_end) in enumerate(bars):
        crop = crop_above_bar(img, bar_start, bar_end, CROP_ABOVE_BAR)
        if crop is None:
            print(f"  Bar {i+1}: skipped (no room above)")
            continue
        print(f"  Bar {i+1}: y={bar_start}-{bar_end}, crop={crop.size[0]}x{crop.size[1]}")
        ocr_data = extract_data(crop)
        crop_scores = parse_scores(
            ocr_data, CHARACTER_NAMES, ROW_TOLERANCE, FUZZY_MATCH_THRESHOLD
        )
        for name, val in sorted(crop_scores.items()):
            print(f"    Matched: {name:20s} {val}")

    if not bars:
        print("  No green bars — showing full-image OCR instead")
        print("\nRaw OCR text:")
        print(extract_text(img))
        print()
        data = extract_data(img)
        _show_ocr_summary(data, "full image")

        print("\nAttempting character name matching...")
        for name in CHARACTER_NAMES:
            found = False
            for i, text in enumerate(data["text"]):
                if data["level"][i] != 5:
                    continue
                text = text.strip()
                if not text:
                    continue
                if name.lower() in text.lower() or text.lower() in name.lower():
                    print(f"  '{name}' -> word '{text}' at ({data['left'][i]},{data['top'][i]})")
                    found = True
            if not found:
                print(f"  '{name}' -> no direct word match")


def cmd_analyze():
    df = load_data()
    if df.empty:
        print("No match data found. Record some matches first with: python main.py")
        return
    print(f"Loaded {len(df)} match(es).\n")
    results = full_analysis(df, k=ADJUSTED_SCORE_K)
    col_order = ["adjusted", "avg_rank", "mean", "median", "std", "p75", "min", "max", "matches"]
    available = [c for c in col_order if c in results.columns]
    print(results[available].to_string())


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--analyze":
        cmd_analyze()
    elif len(sys.argv) > 1 and sys.argv[1] == "--debug":
        cmd_debug()
    else:
        cmd_record()


if __name__ == "__main__":
    main()
