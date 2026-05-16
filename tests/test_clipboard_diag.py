"""Diagnostic script to test clipboard monitoring."""
import sys
import time
import hashlib
from PIL import ImageGrab

sys.path.insert(0, "..")

print("Clipboard Diagnostic")
print("=" * 40)
print("This script will monitor your clipboard for 30 seconds.")
print("Take a screenshot with Win+Shift+S during this time.")
print()

last_hash = None
check_count = 0

start_time = time.time()
while time.time() - start_time < 30:
    check_count += 1
    raw = ImageGrab.grabclipboard()

    if raw is None:
        if check_count % 5 == 0:
            print(f"[{check_count}] Clipboard: empty")
        time.sleep(1)
        continue

    if not hasattr(raw, "size"):
        print(f"[{check_count}] Clipboard: {type(raw).__name__} (not an image)")
        time.sleep(1)
        continue

    small = raw.resize((50, 50)).convert("L")
    current_hash = hashlib.md5(small.tobytes()).hexdigest()

    if current_hash != last_hash:
        last_hash = current_hash
        print(f"[{check_count}] NEW IMAGE: {raw.size[0]}x{raw.size[1]} mode={raw.mode}")

        # Test green bar detection
        from ocr import detect_green_bars
        bars = detect_green_bars(raw)
        print(f"         Green bars: {len(bars)}")
        if bars:
            for i, (y1, y2) in enumerate(bars):
                print(f"         Bar {i+1}: y={y1}-{y2}")
    else:
        if check_count % 5 == 0:
            print(f"[{check_count}] Same image as before")

    time.sleep(1)

print("\nDiagnostic complete.")
