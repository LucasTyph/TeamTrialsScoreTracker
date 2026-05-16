"""Main entry point for the score extraction system.

Usage:
    python main.py            Record a new match (two screenshots)
    python main.py --analyze  Show performance analysis
    python main.py --tray     Run as background tray app
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
from ocr import detect_green_bars, crop_above_bar, extract_data, extract_text, grab_clipboard
from parser import parse_single_match
from storage import append_match, load_data
from analysis import full_analysis, format_report


def _parse_image(img):
    """Parse scores from an image using green-bar splitting."""
    bars = detect_green_bars(img)

    if not bars:
        print("  No green bars detected — falling back to full-image OCR")
        ocr_data = extract_data(img)
        return parse_single_match(
            ocr_data, CHARACTER_NAMES, ROW_TOLERANCE, FUZZY_MATCH_THRESHOLD, set()
        )

    print(f"  Detected {len(bars)} green bar(s)")
    results = {}
    claimed = set()
    for bar_start, bar_end in bars:
        crop = crop_above_bar(img, bar_start, bar_end, CROP_ABOVE_BAR)
        if crop is None:
            continue
        ocr_data = extract_data(crop)
        scores = parse_single_match(
            ocr_data, CHARACTER_NAMES, ROW_TOLERANCE, FUZZY_MATCH_THRESHOLD, claimed
        )
        results.update(scores)
        claimed.update(scores.keys())
    return results


def _process_screenshot(label):
    input(f"Take {label} screenshot with Win+Shift+S, then press Enter...")
    img = grab_clipboard()
    if img is None:
        print("  No image on clipboard.")
        return None
    print(f"  Captured {img.size[0]}x{img.size[1]}")
    return img


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
    print(f"\n  Combined: {len(combined)}/{len(CHARACTER_NAMES)} characters  (total: {total:,})")
    for name in CHARACTER_NAMES:
        val = combined.get(name, None)
        label = f"{val:,}" if val is not None else "MISSING"
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


def cmd_analyze():
    df = load_data()
    if df.empty:
        print("No match data found. Record some matches first with: python main.py")
        return
    print(format_report(df, k=ADJUSTED_SCORE_K))


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
    claimed = set()
    for i, (bar_start, bar_end) in enumerate(bars):
        crop = crop_above_bar(img, bar_start, bar_end, CROP_ABOVE_BAR)
        if crop is None:
            print(f"  Bar {i+1}: skipped (no room above)")
            continue
        print(f"  Bar {i+1}: y={bar_start}-{bar_end}, crop={crop.size[0]}x{crop.size[1]}")
        ocr_data = extract_data(crop)
        scores = parse_single_match(
            ocr_data, CHARACTER_NAMES, ROW_TOLERANCE, FUZZY_MATCH_THRESHOLD, claimed
        )
        claimed.update(scores.keys())
        for name, val in sorted(scores.items()):
            print(f"    Matched: {name:20s} {val}")

    if not bars:
        print("  No green bars — showing full-image OCR instead")
        print("\nRaw OCR text:")
        print(extract_text(img))
        print()


def cmd_tray():
    """Run as background tray application."""
    from tray_app import run
    run()


def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--analyze":
            cmd_analyze()
        elif arg == "--debug":
            cmd_debug()
        elif arg == "--tray":
            cmd_tray()
        else:
            print(f"Unknown argument: {arg}")
            print("Usage: python main.py [--analyze|--debug|--tray]")
    else:
        cmd_record()


if __name__ == "__main__":
    main()
