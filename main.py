"""Convenience launcher: ``python main.py`` opens the app.

Equivalent to ``python -m score_tracker``.
"""

import sys

from score_tracker.gui.app import run

if __name__ == "__main__":
    sys.exit(run())
