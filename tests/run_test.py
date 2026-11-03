"""Run parser on test screenshots and compare against expected CSV."""
import csv
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))

from PIL import Image
from config import ROW_TOLERANCE, FUZZY_MATCH_THRESHOLD, CROP_ABOVE_BAR
from ocr import detect_green_bars, crop_above_bar, extract_data
from parser import parse_single_match

EXPECTED = os.path.join(SCRIPT_DIR, "dataset.csv")
IMG1 = os.path.join(SCRIPT_DIR, "print1.png")
IMG2 = os.path.join(SCRIPT_DIR, "print2.png")


def parse_image(img, character_names):
    bars = detect_green_bars(img)
    results = {}
    claimed = set()
    for bar_start, bar_end in bars:
        crop = crop_above_bar(img, bar_start, bar_end, CROP_ABOVE_BAR)
        if crop is None:
            continue
        ocr_data = extract_data(crop)
        scores = parse_single_match(
            ocr_data, character_names, ROW_TOLERANCE, FUZZY_MATCH_THRESHOLD, claimed
        )
        results.update(scores)
        claimed.update(scores.keys())
    return results


with open(EXPECTED, newline="") as f:
    reader = csv.DictReader(f)
    expected = next(reader)
    # Validate against the dataset's own names so the test is independent of
    # whatever team the user has configured in config.py.
    character_names = [name for name in reader.fieldnames if name != "timestamp"]

img1 = Image.open(IMG1)
img2 = Image.open(IMG2)

actual1 = parse_image(img1, character_names)
actual2 = parse_image(img2, character_names)

combined = {}
combined.update(actual1)
combined.update(actual2)

print(f"Tested {len(character_names)} characters across 2 screenshots")
failures = 0
for name in character_names:
    exp = expected.get(name, "MISSING")
    act = combined.get(name, "MISSING")
    if str(exp) == str(act):
        continue
    failures += 1
    print(f"  FAIL: {name:20s} expected={str(exp):>8s}  actual={str(act):>8s}")

if failures == 0:
    print(f"ALL {len(character_names)} MATCHES CORRECT")
    sys.exit(0)

print(f"{failures} MISMATCH(ES)")
sys.exit(1)
