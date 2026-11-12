"""OCR primitives: Tesseract setup, green-bar detection, preprocessing."""

from __future__ import annotations

import os
import shutil

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


def detect_green_bars(image, min_bar_width=100):
    """Detect green progress bars and return list of (y_start, y_end) tuples."""
    arr = np.array(image.convert("RGB"))
    if arr.ndim != 3 or arr.shape[2] < 3:
        return []

    R = arr[:, :, 0].astype(float)
    G = arr[:, :, 1].astype(float)
    B = arr[:, :, 2].astype(float)

    # Green must be bright and significantly dominate R and B
    green_mask = (G > 120) & (G > R + 30) & (G > B + 30)
    rows_with_green = np.any(green_mask, axis=1)

    bars = []

    def _close(start, end):
        if end - start < image.height * 0.9:
            cols = np.any(green_mask[start:end, :], axis=0)
            if np.sum(cols) >= min_bar_width:
                bars.append((start, end))

    in_bar = False
    bar_start = 0
    for y, has_green in enumerate(rows_with_green):
        if has_green and not in_bar:
            bar_start = y
            in_bar = True
        elif not has_green and in_bar:
            _close(bar_start, y)
            in_bar = False
    if in_bar:
        _close(bar_start, len(rows_with_green))

    return bars


def crop_above_bar(image, bar_y_start, bar_y_end, crop_height):
    """Crop the region above a green bar. Returns None if crop would be empty."""
    crop_top = max(0, bar_y_start - crop_height)
    if bar_y_start <= crop_top:
        return None
    return image.crop((0, crop_top, image.width, bar_y_start))
