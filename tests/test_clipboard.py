"""Test clipboard monitor with console output."""
import sys
import time
import logging

sys.path.insert(0, "..")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

from PIL import ImageGrab
from ocr import detect_green_bars, crop_above_bar, extract_data
from parser import parse_single_match
import config

print("Clipboard Monitor Test")
print("=" * 40)
print("Take a screenshot with Win+Shift+S")
print("Press Ctrl+C to stop")
print()

last_hash = None
claimed = set()
pending = {}

while True:
    try:
        raw = ImageGrab.grabclipboard()
        if raw is None:
            time.sleep(1)
            continue

        if not hasattr(raw, "size"):
            print(f"Clipboard type: {type(raw).__name__} (not an image)")
            time.sleep(1)
            continue

        import hashlib
        small = raw.resize((50, 50)).convert("L")
        current_hash = hashlib.md5(small.tobytes()).hexdigest()

        if current_hash == last_hash:
            time.sleep(1)
            continue

        last_hash = current_hash
        print(f"\nNew image detected: {raw.size[0]}x{raw.size[1]}")

        bars = detect_green_bars(raw)
        print(f"Green bars found: {len(bars)}")

        if not bars:
            print("No green bars - skipping")
            continue

        for i, (bar_start, bar_end) in enumerate(bars):
            crop = crop_above_bar(raw, bar_start, bar_end, config.CROP_ABOVE_BAR)
            if crop is None:
                continue
            ocr_data = extract_data(crop)
            scores = parse_single_match(
                ocr_data, config.CHARACTER_NAMES, config.ROW_TOLERANCE, config.FUZZY_MATCH_THRESHOLD, claimed
            )
            if scores:
                for name, score in scores.items():
                    print(f"  {name}: {score:,}")
                    claimed.add(name)
                    pending[name] = score

        if len(claimed) >= len(config.CHARACTER_NAMES):
            total = sum(pending.values())
            print(f"\n*** MATCH COMPLETE: {len(claimed)} characters, total: {total:,} ***")
            claimed.clear()
            pending.clear()

        time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopped.")
        break
