"""Convenience launcher: ``python main.py [--analyze|--tray|--debug]``.

Equivalent to ``python -m score_tracker``.
"""

from score_tracker.cli import main

if __name__ == "__main__":
    main()
