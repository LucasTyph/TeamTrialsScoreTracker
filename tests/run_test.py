"""Run parser on test screenshots and compare against expected CSV."""
import csv
import sys
sys.path.insert(0, "..")

from PIL import Image
from config import CHARACTER_NAMES, ROW_TOLERANCE, FUZZY_MATCH_THRESHOLD, CROP_ABOVE_BAR
from ocr import detect_green_bars, crop_above_bar, extract_data
from parser import parse_single_match

EXPECTED = "E:\\teste\\tests\\dataset.csv"
IMG1 = "E:\\teste\\tests\\print1.png"
IMG2 = "E:\\teste\\tests\\print2.png"


def parse_image(img):
    bars = detect_green_bars(img)
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


with open(EXPECTED) as f:
    reader = csv.DictReader(f)
    expected = next(reader)

img1 = Image.open(IMG1)
img2 = Image.open(IMG2)

actual1 = parse_image(img1)
actual2 = parse_image(img2)

combined = {}
combined.update(actual1)
combined.update(actual2)

print(f"Tested {len(CHARACTER_NAMES)} characters across 2 screenshots")
all_ok = True
for name in CHARACTER_NAMES:
    exp = expected.get(name, "MISSING")
    act = combined.get(name, "MISSING")
    match = "OK" if str(exp) == str(act) else "FAIL"
    if match == "FAIL":
        all_ok = False
        print(f"  FAIL: {name:20s} expected={exp:>8s}  actual={str(act):>8s}")

if all_ok:
    print("ALL 15 MATCHES CORRECT")
    sys.exit(0)
else:
    print("SOME MISMATCHES")
    sys.exit(1)
