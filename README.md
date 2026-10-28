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
  - If installed in a different location, update `TESSERACT_CMD` in `config.py`

## Installation

### Using pip

```bash
pip install -r requirements.txt
```

### Using pyproject.toml

```bash
pip install .
```

## Configuration

1. Edit `config.py` to configure your team and Tesseract path:

   ```python
   CHARACTER_NAMES = [
       "Maruzensky",
       "Oguri Cap",
       # ... add your 15 character names
   ]

   TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
   ```

2. Adjust detection thresholds as needed:

   | Setting | Default | Description |
   | --- | --- | --- |
   | `ROW_TOLERANCE` | 20 | Vertical pixel tolerance for grouping OCR entries |
   | `FUZZY_MATCH_THRESHOLD` | 0.6 | Minimum similarity ratio for character name matching |
   | `CROP_ABOVE_BAR` | 55 | Pixels to crop above each detected green progress bar |
   | `ADJUSTED_SCORE_K` | 0.5 | Variance penalty multiplier for consistency scoring |

## Usage

### Background Tray App (Recommended)

```bash
python main.py --tray
```

Or double-click `scripts/start_tray.bat`. 

The application runs in the system tray and will:

1. Monitor the clipboard for new screenshots
2. Automatically process screenshots taken with `Win+Shift+S`
3. Display toast notifications with the number of characters detected
4. Save complete matches (all 15 characters) to CSV
5. Show a summary notification with the total team score

**Tray menu options:**

- **Analyze** — View a full performance report
- **View Last Match** — Display the most recently recorded match
- **Pause Monitoring** — Temporarily disable clipboard detection
- **Exit** — Close the application

### Command-Line Recording

```bash
python main.py
```

Prompts for two sequential screenshots. Useful for debugging or when the tray app isn't needed.

### Analysis

```bash
python main.py --analyze
```

Generates a comprehensive performance report in the console, including:

- Team totals (average, best, and worst)
- Recent match trends
- Character tier classifications (S/A/B/C)
- Contribution percentages
- Coefficient of variation (consistency)
- Replace priority rankings
- Detailed statistics table

### Debug Mode

```bash
python main.py --debug
```

Runs OCR on the current clipboard image and displays detected words, green bar positions, and character name matches. Add `--verbose` for detailed per-crop candidate information.

## How It Works

### Screenshot Processing

1. **Green bar detection** — Scans the image for bright green progress bars (G channel dominant over R and B)
2. **Region cropping** — For each bar, crops the area above it where the character name and score appear
3. **Per-crop OCR** — Runs Tesseract on each small crop individually, avoiding cross-row confusion
4. **Name matching** — Matches OCR words to character names using part-fraction scoring (what fraction of the name's word-parts appear in the crop)
5. **Score extraction** — Finds the number in the crop, handling OCR splits (e.g., "64,636" read as "6" + "4,636")

### Number Merging

Scores are always between 10,000 and 200,000. When OCR splits a number:
- Adjacent fragments on the same row are merged
- The merge direction is determined by the position of extracted fragments
- Results outside the valid range are discarded as UI noise

### Statistical Analysis

| Metric | Formula | Purpose |
| --- | --- | --- |
| **Adjusted Score** | `mean - k * std` | Rewards consistency; higher values are better |
| **Contribution %** | `char_mean / total_mean × 100` | Percentage of total team score contributed by each character |
| **CV (Coefficient of Variation)** | `std / mean × 100` | Measures reliability relative to average performance (lower is better) |
| **Replace Priority** | Weighted composite (low contribution, high CV, low adjusted score) | Ranked list of replacement candidates from worst to best |

## Project Structure

```text
├── main.py                 # CLI entry point
├── config.py               # Character names and configuration thresholds
├── ocr.py                  # Clipboard reading and OCR extraction
├── parser.py               # Score parsing and number merging logic
├── storage.py              # CSV read/write operations
├── analysis.py             # Statistical analysis and report generation
├── clipboard_monitor.py    # Background clipboard watcher
├── tray_app.py             # System tray application
├── notifications.py        # Windows toast notifications
├── scripts/
│   └── start_tray.bat      # Windows launcher script
├── data/                   # Match data (gitignored)
├── assets/
│   └── icon.png            # Tray icon (gitignored)
├── tests/
│   ├── run_test.py         # Automated test suite
│   ├── dataset.csv         # Expected test results
│   └── print[1-4].png      # Test screenshots
├── tray.log                # Runtime logs (gitignored)
├── requirements.txt        # Python dependencies
├── pyproject.toml          # Project metadata and dependencies
└── LICENSE                 # MIT License
```

## Testing

```bash
cd tests
python run_test.py
```

Runs the parser against the bundled test screenshots and validates the extracted scores against expected results.

## Troubleshooting

| Issue | Solution |
| --- | --- |
| **No green bars detected** | Ensure your screenshot captures the character score area with visible green progress bars. Adjust `CROP_ABOVE_BAR` in `config.py` if needed. |
| **Character names not matching** | Verify that names in `config.py` exactly match the in-game names. Lower `FUZZY_MATCH_THRESHOLD` if OCR misreads characters. Use `--debug` to inspect detected text. |
| **Incorrect or missing scores** | Use `--debug --verbose` to view detected numbers and merge candidates. Ensure scores fall within the 10,000–200,000 range, or adjust `SCORE_MIN`/`SCORE_MAX` in `parser.py`. |
| **Tray app not responding** | Check `tray.log` for errors, ensure no other process is holding the clipboard, and restart the application. |

## License

This project is licensed under the [MIT License](LICENSE).
