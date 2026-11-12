"""OCR primitives: Tesseract setup, green-bar detection, preprocessing."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, replace
from difflib import get_close_matches

import numpy as np
import pytesseract
from PIL import Image, ImageGrab, ImageOps

_tesseract_path: str | None = None


def resolve_tesseract(configured_cmd: str) -> str | None:
    """Configured path if it exists, else ``tesseract`` on PATH, else None."""
    if configured_cmd and os.path.isfile(configured_cmd):
        return configured_cmd
    return shutil.which("tesseract")


def configure(configured_cmd: str) -> bool:
    """Point pytesseract at Tesseract. Returns True if it was found."""
    global _tesseract_path
    _tesseract_path = resolve_tesseract(configured_cmd)
    if _tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = _tesseract_path
    return _tesseract_path is not None


def tesseract_available() -> bool:
    return _tesseract_path is not None


def grab_clipboard():
    """Grab image from clipboard. Returns PIL Image or None."""
    img = ImageGrab.grabclipboard()
    if isinstance(img, Image.Image):
        return img
    return None


def extract_data(image):
    """Run OCR and return positional text data dict (image_to_data)."""
    return pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)


def extract_text(image):
    """Run OCR and return plain text string."""
    return pytesseract.image_to_string(image)


# Preprocessing variants tried in order until a crop yields a name and score.
# Grayscale goes first: on the bundled test screenshots it reads every crop,
# while plain RGB misses some names on the colored row backgrounds.
def _gray(img):
    return ImageOps.grayscale(img)


def _gray_upscaled(img):
    return ImageOps.grayscale(img).resize((img.width * 3, img.height * 3), Image.LANCZOS)


def _rgb(img):
    return img.convert("RGB")


PREPROCESS_VARIANTS = (
    ("gray", _gray),
    ("rgb", _rgb),
    ("gray-3x", _gray_upscaled),
)


from .config import DISTANCES  # noqa: E402


@dataclass(frozen=True)
class ScoreRow:
    """One character row on the Score Info screen, located by its progress bar."""

    x0: int  # left edge of the bar
    y0: int  # top of the bar
    y1: int  # bottom of the bar
    width: int  # full bar width (green fill + grey remainder)
    # Predicted row below the last visible bar (its bar is scrolled out of
    # view but its name and score may still show)
    virtual: bool = False
    # Text band hidden under the panel header (row scrolled half out of view)
    covered: bool = False


def _longest_runs(mask):
    """For each row of a boolean mask: (length, start, end) of its longest True run."""
    h, w = mask.shape
    padded = np.zeros((h, w + 2), dtype=np.int8)
    padded[:, 1:-1] = mask
    diff = np.diff(padded, axis=1)
    out = np.zeros((h, 3), dtype=int)
    for y in np.flatnonzero(mask.any(axis=1)):
        starts = np.flatnonzero(diff[y] == 1)
        ends = np.flatnonzero(diff[y] == -1)
        i = int(np.argmax(ends - starts))
        out[y] = (ends[i] - starts[i], starts[i], ends[i])
    return out


def find_score_rows(image, min_bar_width=100):
    """Locate the score progress bars, top to bottom.

    Works on a tight snip or a full game-window capture: each image row's
    longest run of green is found, runs are grouped into bars, and only the
    largest set of thin bars sharing the same left edge is kept (this skips
    window headers and other green UI).
    """
    arr = np.asarray(image.convert("RGB")).astype(np.int16)
    R, G, B = arr[..., 0], arr[..., 1], arr[..., 2]
    green = (G > 120) & (G > R + 30) & (G > B + 30)
    runs = _longest_runs(green)

    segments = []  # (y0, y1, x0, x1)
    y, h = 0, len(runs)
    while y < h:
        if runs[y, 0] < min_bar_width:
            y += 1
            continue
        y0 = y
        y += 1
        # Rounded bar ends shift the left edge a few px per row
        while y < h and runs[y, 0] >= min_bar_width and abs(runs[y, 1] - runs[y - 1, 1]) <= 4:
            y += 1
        seg = runs[y0:y]
        segments.append((y0, y, int(seg[:, 1].min()), int(np.median(seg[:, 2]))))

    # Grey remainder of a partly-filled bar tells us the full bar width.
    grey = (np.abs(R - G) < 14) & (np.abs(G - B) < 14) & (G > 40) & (G < 130)

    def full_end(y0, y1, x1):
        row = grey[(y0 + y1) // 2]
        x = x1
        while x < row.size and row[x]:
            x += 1
        return x

    clusters = []
    for seg in segments:
        for c in clusters:
            if abs(c[0][2] - seg[2]) <= 6:
                c.append(seg)
                break
        else:
            clusters.append([seg])

    best = []
    for c in clusters:
        x0 = c[0][2]
        width = max(max(full_end(y0, y1, x1), x1) - x0 for y0, y1, _, x1 in c)
        rows = [ScoreRow(s[2], s[0], s[1], width) for s in c
                if 0.02 * width <= s[1] - s[0] <= 0.07 * width]
        if (len(rows), width) > (len(best), best[0].width if best else 0):
            best = rows
    if not best:
        return best

    width = best[0].width
    band = int(0.135 * width)

    def covered(row):
        top = max(0, row.y0 - band)
        region = green[top:row.y0, row.x0:row.x0 + width]
        return region.size > 0 and region.mean() > 0.2

    best = [replace(r, covered=covered(r)) for r in best]
    # One row further down: its bar may be cut off while its text is visible.
    pitch = int(np.median(np.diff([r.y0 for r in best]))) if len(best) > 1 else int(0.276 * width)
    nxt = best[-1].y0 + pitch
    if nxt - band >= 0 and nxt <= h:
        best.append(ScoreRow(best[-1].x0, nxt, nxt + (best[-1].y1 - best[-1].y0), width, virtual=True))
    return best


def _crop(image, box):
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(image.width, x1), min(image.height, y1)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    return image.crop((x0, y0, x1, y1))


def text_crop(image, row: ScoreRow):
    """Name, title and score: the band just above the bar."""
    w = row.width
    return _crop(image, (row.x0 - 0.03 * w, row.y0 - 0.135 * w, row.x0 + 1.0 * w, row.y0))


def badge_crop(image, row: ScoreRow):
    """The distance badge under the portrait, left of the bar.

    None when the badge is cut off by the edge of the screenshot.
    """
    w = row.width
    box = (row.x0 - 0.32 * w, row.y0 + 0.03 * w, row.x0 - 0.07 * w, row.y1 + 0.07 * w)
    if box[0] < 0 or box[3] > image.height:
        return None
    return _crop(image, box)


_DISTANCE_CHARS = "".join(sorted(set("".join(DISTANCES))))


def read_distance(crop):
    """OCR a distance badge (white text on a coloured pill). None if unreadable."""
    arr = np.asarray(crop.convert("RGB")).astype(np.int16)
    # Badge text is near-white; the pill and background are not. Keep only
    # rows that contain pill colour so the portrait above is ignored.
    white = (arr.min(axis=2) > 200)
    pill = (arr[..., 0] > 180) & (arr[..., 1] < 140)
    rows = np.flatnonzero(pill.sum(axis=1) > pill.shape[1] * 0.3)
    if rows.size == 0:
        return None
    r0, r1 = rows.min(), rows.max() + 1
    cols = np.flatnonzero(pill[r0:r1].any(axis=0))
    pad = max(2, (r1 - r0) // 4)  # skip the pill's rounded ends
    text_mask = white[r0:r1, cols.min() + pad:cols.max() + 1 - pad]
    if not text_mask.any():
        return None
    binary = Image.fromarray(np.where(text_mask, 0, 255).astype(np.uint8))
    binary = ImageOps.expand(binary.resize((binary.width * 3, binary.height * 3), Image.LANCZOS),
                             border=12, fill=255)
    text = pytesseract.image_to_string(
        binary, config=f"--psm 7 -c tessedit_char_whitelist={_DISTANCE_CHARS}"
    )
    word = "".join(ch for ch in text if ch.isalpha())
    if not word:
        return None
    match = get_close_matches(word.capitalize(), DISTANCES, n=1, cutoff=0.6)
    return match[0] if match else None
