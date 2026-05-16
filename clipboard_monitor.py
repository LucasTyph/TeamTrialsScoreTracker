"""Clipboard image monitoring for automatic screenshot detection."""
import hashlib
import time
import threading
import logging
from PIL import ImageGrab

import config
from ocr import detect_green_bars, crop_above_bar, extract_data
from parser import parse_single_match
from notifications import notify, notify_error

logger = logging.getLogger("clipboard_monitor")


class ClipboardMonitor:
    """Watches clipboard for new images and processes them."""

    def __init__(self, on_match_complete=None, on_error=None):
        self._last_hash = None
        self._running = False
        self._thread = None
        self._pending_scores = {}
        self._claimed = set()
        self._lock = threading.Lock()
        self._on_match_complete = on_match_complete
        self._on_error = on_error or (lambda msg: None)

    def start(self):
        """Start monitoring in background thread."""
        self._running = True
        # Capture initial clipboard state to ignore existing images
        initial = ImageGrab.grabclipboard()
        if initial is not None and hasattr(initial, "size"):
            self._last_hash = self._image_hash(initial)
            logger.info("Initial clipboard image captured (will ignore)")
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Clipboard monitor started")

    def stop(self):
        """Stop monitoring."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("Clipboard monitor stopped")

    @property
    def is_running(self):
        return self._running

    def _image_hash(self, img):
        """Compute a quick hash of the image to detect changes."""
        small = img.resize((50, 50)).convert("L")
        return hashlib.md5(small.tobytes()).hexdigest()

    def _process_image(self, img):
        """Process a single screenshot image."""
        logger.info("Processing image %sx%s", img.size[0], img.size[1])
        bars = detect_green_bars(img)
        logger.info("Detected %d green bars", len(bars))
        if not bars:
            notify_error("No green bars detected in screenshot")
            return {}

        results = {}
        with self._lock:
            claimed = set(self._claimed)

        for bar_start, bar_end in bars:
            crop = crop_above_bar(img, bar_start, bar_end, config.CROP_ABOVE_BAR)
            if crop is None:
                continue
            ocr_data = extract_data(crop)
            scores = parse_single_match(
                ocr_data, config.CHARACTER_NAMES, config.ROW_TOLERANCE, config.FUZZY_MATCH_THRESHOLD, claimed
            )
            logger.info("Bar y=%d-%d matched: %s", bar_start, bar_end, list(scores.keys()))
            results.update(scores)
            claimed.update(scores.keys())

        with self._lock:
            self._claimed.update(results.keys())
            self._pending_scores.update(results)

        # Single notification per image with summary
        if results:
            count = len(results)
            notify("Screenshot Processed", f"{count} character(s) found")

        return results

    def _check_match_complete(self):
        """Check if we have all 15 characters for a match."""
        with self._lock:
            if len(self._claimed) >= len(config.CHARACTER_NAMES):
                scores = dict(self._pending_scores)
                total = sum(scores.values())
                self._pending_scores.clear()
                self._claimed.clear()
                return scores, total
        return None, None

    def _loop(self):
        """Main monitoring loop."""
        logger.info("Monitor loop started")
        while self._running:
            try:
                raw = ImageGrab.grabclipboard()
                if raw is None:
                    time.sleep(1)
                    continue

                img_type = type(raw).__name__
                logger.debug("Clipboard content type: %s", img_type)

                if not hasattr(raw, "size"):
                    logger.debug("Clipboard is not an image (type: %s)", img_type)
                    time.sleep(1)
                    continue

                current_hash = self._image_hash(raw)
                if current_hash != self._last_hash:
                    logger.info("New image detected (hash: %s)", current_hash[:8])
                    self._last_hash = current_hash
                    self._process_image(raw)

                    scores, total = self._check_match_complete()
                    if scores is not None:
                        if self._on_match_complete:
                            self._on_match_complete(scores, total)

            except Exception as e:
                logger.error("Monitor loop error: %s", str(e))
                self._on_error(str(e))

            time.sleep(1)
