"""OCR extraction from clipboard images."""

import numpy as np
import pytesseract
from PIL import ImageGrab, Image

import config

pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD


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


def detect_green_bars(image):
    """Detect green progress bars and return list of (y_start, y_end) tuples."""
    arr = np.array(image)
    if len(arr.shape) != 3 or arr.shape[2] < 3:
        return []

    R = arr[:, :, 0].astype(float)
    G = arr[:, :, 1].astype(float)
    B = arr[:, :, 2].astype(float)

    # Green must be bright and significantly dominate R and B
    green_mask = (G > 120) & (G > R + 30) & (G > B + 30)

    rows_with_green = np.any(green_mask, axis=1)

    bars = []
    in_bar = False
    bar_start = 0

    for y in range(len(rows_with_green)):
        if rows_with_green[y] and not in_bar:
            bar_start = y
            in_bar = True
        elif not rows_with_green[y] and in_bar:
            bar_end = y
            if bar_end - bar_start < image.height * 0.9:
                cols = np.any(green_mask[bar_start:bar_end, :], axis=0)
                if np.sum(cols) >= config.MIN_BAR_WIDTH:
                    bars.append((bar_start, bar_end))
            in_bar = False

    if in_bar:
        bar_end = len(rows_with_green)
        if bar_end - bar_start < image.height * 0.9:
            cols = np.any(green_mask[bar_start:bar_end, :], axis=0)
            if np.sum(cols) >= config.MIN_BAR_WIDTH:
                bars.append((bar_start, bar_end))

    return bars


def crop_above_bar(image, bar_y_start, bar_y_end, crop_height):
    """Crop the region above a green bar. Returns None if crop would be empty."""
    crop_top = max(0, bar_y_start - crop_height)
    if bar_y_start <= crop_top:
        return None
    return image.crop((0, crop_top, image.width, bar_y_start))
