# Team Trials Score Tracker

A tool for extracting, tracking, and analyzing Team Trials scores from Umamusume: Pretty Derby screenshots. Automatically process match data to identify underperforming characters and optimize your team composition.

## Overview

Looking at a character's best score alone isn't enough to gauge their performance in Team Trials. Consistency matters — tracking scores across multiple matches helps identify which characters reliably underperform and should be replaced. 

This tool provides:

- **Automated extraction** — Reads screenshots directly from the clipboard
- **OCR-powered parsing** — Extracts character names and scores from Team Trials result screens
- **Persistent storage** — Saves match data to CSV for long-term tracking
- **Statistical analysis** — Evaluates performance with consistency metrics to identify weak links

## Requirements

- [Python 3.10+](https://www.python.org/downloads/)
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) — Install via UB-Mannheim releases
  - Default path: `C:\Program Files\Tesseract-OCR\tesseract.exe`
  - If installed in a different location, set `tesseract_cmd` in your `settings.toml`, or make sure `tesseract` is available on your `PATH`

## Installation

### Running from a checkout

```bash
pip install -r requirements.txt
```

You can also install Tesseract itself with winget:

```powershell
winget install UB-Mannheim.TesseractOCR
```

### Installing as a command

```bash
pip install .
```

This adds a `score-tracker` command (same options as `python -m score_tracker`).

## Configuration

Your personal settings live in `settings.toml` in the data folder, which is not tracked by git. It is created the first time you run the app:

| Running from | Data folder |
| --- | --- |
| A checkout of this repo | `data/` |
| `pip install .` | `%LOCALAPPDATA%\TeamTrialsScoreTracker` |
| Anywhere, with `SCORE_TRACKER_DATA` set | that folder |

Add your 15 character names exactly as they appear in-game:

```toml
roster = [
    "Maruzensky",
    "Oguri Cap",
    # ... your 15 character names
]
```

Changing the roster later is safe: each saved score records its character, so old matches are never misaligned. The analysis covers the characters in your current roster.

Other settings can be overridden in the same file (they are listed, commented out, in the generated file):

| Setting | Default | Description |
| --- | --- | --- |
| `tesseract_cmd` | `C:\Program Files\Tesseract-OCR\tesseract.exe` | Path to `tesseract.exe` |
| `row_tolerance` | 20 | Vertical pixel tolerance for grouping OCR entries |
| `fuzzy_match_threshold` | 0.6 | Minimum fraction of a name's words that must be read |
| `crop_above_bar` | 55 | Pixels to crop above each detected green progress bar |
| `min_bar_width` | 100 | Minimum width in pixels of a green bar |
| `adjusted_score_k` | 0.5 | Variance penalty multiplier for consistency scoring |
| `pending_timeout_minutes` | 10 | Tray app: save an incomplete match as partial after this long without new screenshots |

## Usage

### Background Tray App (Recommended)

```bash
python -m score_tracker --tray
```

Or double-click `scripts/start_tray.bat`. (`python main.py --tray` also still works.)

The application runs in the system tray and will:

1. Monitor the clipboard for new screenshots
2. Automatically process screenshots taken with `Win+Shift+S`
3. Show a notification with how many characters were found so far
4. Save the match once all 15 characters are found
5. Show a summary notification with the total team score

Screenshots that overlap, or the same screen captured twice, are handled: characters already recorded are recognized and skipped. If you take a screenshot of the *next* match before the current one is complete, the incomplete match is saved as a partial match and a new one starts. The same happens after `pending_timeout_minutes` without new screenshots, and when you exit.

If exactly one character's name can't be read but its score can, and that character is the only one missing, the score is assigned to it by elimination (the notification says so).

**Tray menu options:**

- **Analyze** — View a full performance report
- **View Last Match** — Display the most recently recorded match
- **Save Partial Match** — Save the characters found so far as an incomplete match
- **Discard Pending Match** — Throw away the characters found so far
- **Pause Monitoring** — Temporarily disable clipboard detection
- **Exit** — Close the application

### Command-Line Recording

```bash
python -m score_tracker
```

Prompts for two sequential screenshots. Useful for debugging or when the tray app isn't needed.

### Analysis

```bash
python -m score_tracker --analyze
```

Generates a comprehensive performance report in the console, including:

- Team totals (average, best, and worst), from complete matches only so partial matches don't skew them
- Recent match trends
- Character tier classifications (S/A/B/C)
- Contribution percentages
- Coefficient of variation (consistency)
- Replace priority rankings
- Detailed statistics table

### Debug Mode

```bash
python -m score_tracker --debug
```

Runs OCR on the current clipboard image and shows, for each green bar, the words and numbers detected with each preprocessing pass and the candidate name matches.

## How It Works

### Screenshot Processing

1. **Green bar detection** — Scans the image for bright green progress bars (G channel dominant over R and B)
2. **Region cropping** — For each bar, crops the area above it where the character name and score appear
3. **Per-crop OCR** — Runs Tesseract on each small crop individually, avoiding cross-row confusion. Each crop is tried in grayscale first, then in color, then grayscale upscaled 3×, until a name and score are read (grayscale alone reads all 30 rows in the test screenshots; color misses one)
4. **Name matching** — Matches OCR words to character names using part-fraction scoring (what fraction of the name's word-parts appear in the crop)
5. **Score extraction** — Finds the number in the crop, handling OCR splits (e.g., "64,636" read as "6" + "4,636")

### Number Merging

Scores are always between 10,000 and 200,000. When OCR splits a number:
- Adjacent fragments on the same row are merged
- The merge direction is determined by the position of extracted fragments
- Results outside the valid range are discarded as UI noise

### Data Storage

Matches are stored in `scores.csv` in the data folder, one row per character score:

```text
match_id,timestamp,character,score
1,2026-11-02 22:33:00,Agnes Digital,65582
```

Data from older versions (`dataset.csv`, one column per character) is converted automatically on first run; the original is kept as `dataset.wide-backup.csv`.

### Statistical Analysis

| Metric | Formula | Purpose |
| --- | --- | --- |
| **Adjusted Score** | `mean - k * std` | Rewards consistency; higher values are better |
| **Contribution %** | `char_mean / total_mean × 100` | Percentage of total team score contributed by each character (complete matches) |
| **CV (Coefficient of Variation)** | `std / mean × 100` | Measures reliability relative to average performance (lower is better) |
| **Replace Priority** | Weighted composite (low contribution, high CV, low adjusted score) | Ranked list of replacement candidates from worst to best |

## Project Structure

```text
├── score_tracker/
│   ├── cli.py                # Command-line entry point (python -m score_tracker)
│   ├── config.py             # Default settings and settings.toml loading
│   ├── pipeline.py           # Screenshot → scores (shared by CLI, tray and tests)
│   ├── ocr.py                # Tesseract setup, green-bar detection, preprocessing
│   ├── parser.py             # Name matching, score parsing and number merging
│   ├── storage.py            # scores.csv read/write and legacy migration
│   ├── analysis.py           # Statistical analysis and report generation
│   ├── clipboard_monitor.py  # Background clipboard watcher
│   ├── tray_app.py           # System tray application
│   ├── notifications.py      # Desktop notifications
│   └── assets/icon.png       # Tray icon
├── main.py                   # Shortcut for python -m score_tracker
├── scripts/
│   └── start_tray.bat        # Windows launcher script
├── data/                     # settings.toml, scores.csv, tray.log (gitignored)
├── tests/                    # pytest suite, test screenshots and expected scores
├── requirements.txt          # Python dependencies
├── pyproject.toml            # Project metadata and dependencies
└── LICENSE                   # MIT License
```

## Testing

```bash
pip install pytest
python -m pytest
```

Most tests use synthetic OCR data and run anywhere. `tests/test_screenshots.py` runs the real screenshots in `tests/` through Tesseract and checks every score against `tests/dataset.csv`; it is skipped when Tesseract isn't installed (as in CI). The tests use their own roster, so they don't depend on your `settings.toml`.

## Troubleshooting

| Issue | Solution |
| --- | --- |
| **`Tesseract OCR was not found`** | Install Tesseract (see [Requirements](#requirements)) and make sure `tesseract_cmd` in `settings.toml` points to `tesseract.exe`, or add its install folder to your `PATH`. |
| **`Your roster is empty`** | Add your character names to `settings.toml` (the error shows its path). |
| **No green bars detected** | Ensure your screenshot captures the character score area with visible green progress bars. Adjust `crop_above_bar` in `settings.toml` if needed. |
| **Character names not matching** | Verify that the roster names exactly match the in-game names. Use `--debug` to inspect detected text. Lower `fuzzy_match_threshold` only with care: similar names (e.g. "Sakura Chiyono O" / "Sakura Bakushin O") can then be confused. |
| **Incorrect or missing scores** | Use `--debug` to view detected numbers and merge candidates. Scores must fall within 10,000–200,000 (`SCORE_MIN`/`SCORE_MAX` in `score_tracker/parser.py`). |
| **Tray app not responding** | Check `data/tray.log` for errors, ensure no other process is holding the clipboard, and restart the application. |

## License

This project is licensed under the [MIT License](LICENSE).
