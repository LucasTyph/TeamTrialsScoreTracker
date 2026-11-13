"""Convenience launcher: ``python main.py`` opens the app.

Equivalent to ``python -m score_tracker``.
"""

import sys

from score_tracker.launch import main

if __name__ == "__main__":
    sys.exit(main())
