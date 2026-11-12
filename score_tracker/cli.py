"""Command-line entry point.

Usage:
    python -m score_tracker --app      Open the app (window + tray icon)
    python -m score_tracker --tray     Start the app in the tray, without the window
    python -m score_tracker            Record a match in the terminal (two screenshots)
    python -m score_tracker --analyze  Print the analysis
    python -m score_tracker --debug    Show OCR output for the clipboard image
"""

from __future__ import annotations

import argparse
import sys

from . import ocr
from .analysis import format_report
from .config import Settings, SettingsError, load_settings
from .pipeline import MatchAccumulator, parse_image
from .storage import append_match, load_scores, migrate_legacy


def _load_settings(require_roster=True) -> Settings:
    try:
        settings = load_settings()
    except SettingsError as e:
        raise SystemExit(f"Settings error: {e}")
    migrated = migrate_legacy(settings)
    if migrated:
        print(f"Migrated {migrated} matches to {settings.scores_path}")
    if not settings.roster and require_roster:
        raise SystemExit(
            f"Your roster is empty. Add your characters' names to:\n  {settings.settings_path}"
        )
    return settings


def _require_tesseract(settings: Settings):
    if ocr.configure(settings.tesseract_cmd):
        return
    raise SystemExit(
        "ERROR: Tesseract OCR was not found.\n"
        "  Install it from: https://github.com/UB-Mannheim/tesseract/wiki\n"
        f"  Expected path: {settings.tesseract_cmd}\n"
        f"  If it is installed elsewhere, set tesseract_cmd in {settings.settings_path}\n"
        "  or add the Tesseract install folder to your PATH."
    )


def _grab_screenshot(label):
    input(f"Take {label} screenshot with Win+Shift+S, then press Enter...")
    img = ocr.grab_clipboard()
    if img is None:
        print("  No image on clipboard.")
        return None
    print(f"  Captured {img.size[0]}x{img.size[1]}")
    return img


def cmd_record(settings: Settings):
    _require_tesseract(settings)
    print("Match Score Recorder")
    print("====================")
    print()
    print("You will take two screenshots (Win+Shift+S) for one match.")
    print()

    match = MatchAccumulator(settings)
    for label in ("first", "second"):
        img = _grab_screenshot(label)
        if img is None:
            return
        result = parse_image(img, settings, claimed=match.scores)
        if not result.bars:
            print("  No score bars detected — used full-image OCR")
        print(f"  Matched {len(result.scores)} character(s)")
        for name, val in sorted(result.scores.items()):
            print(f"    {name:20s} {val:,}")
        if result.duplicates:
            print(f"  Already recorded: {', '.join(sorted(result.duplicates))}")
        if result.orphan_scores:
            print(f"  Unreadable name(s) for score(s): {', '.join(f'{s:,}' for s in result.orphan_scores)}")
        match.add(result)

    scores = match.final_scores()
    inferred = match.inferred()
    total = sum(scores.values())
    print(f"\n  Combined: {len(scores)}/{len(settings.roster)} characters  (total: {total:,})")
    for name in settings.roster:
        val = scores.get(name)
        label = f"{val:,}" if val is not None else "MISSING"
        if name in {n for n, _, _ in inferred}:
            label += "  (name unreadable; matched by elimination)"
        print(f"    {name:20s} {label}")

    if not scores:
        print("\nNothing to save.")
        return
    if not match.complete:
        missing = [n for n in settings.roster if n not in scores]
        print(f"\nWarning: {len(missing)} character(s) not found: {', '.join(missing)}")
        if input("Save partial data anyway? (y/N): ").strip().lower() != "y":
            return
    append_match(scores, settings, match.final_distances())
    print(f"\nSaved to {settings.scores_path}")


def cmd_analyze(settings: Settings):
    scores = load_scores(settings)
    if scores.empty:
        print("No match data found. Record some matches first with: python -m score_tracker")
        return
    print(format_report(scores, settings))


def cmd_debug(settings: Settings):
    """Run OCR on whatever is on the clipboard and show all detected text."""
    _require_tesseract(settings)
    print("OCR Debug Mode")
    print("==============")
    input("Take a screenshot with Win+Shift+S, then press Enter...")
    img = ocr.grab_clipboard()
    if img is None:
        print("No image on clipboard.")
        return
    print(f"Image: {img.size[0]}x{img.size[1]}\n")

    result = parse_image(img, settings, verbose=True)
    print(f"\nDetected {result.bars} score row(s); matched {len(result.scores)}:")
    for name, val in sorted(result.scores.items()):
        print(f"    {name:20s} {val:,}")
    if result.orphan_scores:
        print(f"Scores with unreadable names: {result.orphan_scores}")
    if not result.bars:
        print("\nRaw OCR text:")
        print(ocr.extract_text(img))


def cmd_app(settings: Settings, show_window=True):
    _require_tesseract(settings)
    from .gui.app import run

    return run(settings, show_window=show_window)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="score-tracker", description="Team Trials score tracker")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--analyze", action="store_true", help="show performance analysis")
    mode.add_argument("--app", action="store_true", help="open the app (window and tray icon)")
    mode.add_argument("--tray", action="store_true", help="start the app in the tray, window hidden")
    mode.add_argument("--debug", action="store_true", help="show OCR output for a clipboard image")
    args = parser.parse_args(argv)

    settings = _load_settings(require_roster=not (args.app or args.tray or args.analyze))
    if args.analyze:
        cmd_analyze(settings)
    elif args.debug:
        cmd_debug(settings)
    elif args.app or args.tray:
        return cmd_app(settings, show_window=not args.tray)
    else:
        cmd_record(settings)


if __name__ == "__main__":
    sys.exit(main())
