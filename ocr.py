"""OCR extraction from clipboard images."""

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
