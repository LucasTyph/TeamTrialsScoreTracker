# Team Trials Score Tracker

Are you ever in doubt of which character is tanking your Team Trials score in Umamusume? Or just curious about which umas are carrying your score?
I was too, so I created this. And by 'I created', I mean 'I didn't spend a single neuron coding this'.
Extract structured Team Trials score data from game screenshots and track uma performance over time. Designed to identify which umas consistently underperform and should be replaced.

## Overview

In Team Trials, you obviously want to have high performing umas, but just looking at their best scores is not enough. If every single one of your umas peaks half of the time, you'll only have all your umas peaking once every 32768 TT tries. I don't think you can get all those runs reliably in a week. So, to truly improve, you have to keep records of your umas' scores match-after-match, identify weak links, build them again, and repeat the cycle. Or, well, that's the way I found to get decent scores with my lack of good cards and skill.

The tool:
- Reads screenshots directly from the clipboard
- Extracts character names and scores using OCR
- Stores data persistently in CSV
- Analyzes long-term character performance statistically

## Requirements

- **Python 3.10+**
- **Tesseract OCR** — install from [UB-Mannheim releases](https://github.com/UB-Mannheim/tesseract/wiki)
  - Default path: `C:\Program Files\Tesseract-OCR\tesseract.exe`
  - If installed elsewhere, update `TESSERACT_CMD` in `config.py`

## Installation

```
pip install -r requirements.txt
```

Or using pyproject.toml:

```
pip install .
```

## Configuration

Edit `config.py` before first use:

```python
CHARACTER_NAMES = [
    "Maruzensky",
    "Oguri Cap",
    # ... your 15 character names
]

TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

Adjustable thresholds:

| Setting | Default | Description |
|---|---|---|
| `ROW_TOLERANCE` | 20 | Vertical pixel tolerance for grouping OCR entries |
| `FUZZY_MATCH_THRESHOLD` | 0.6 | Minimum similarity ratio for character name matching |
| `CROP_ABOVE_BAR` | 55 | Pixels to crop above each detected green progress bar |
| `ADJUSTED_SCORE_K` | 0.5 | Variance penalty multiplier for consistency scoring |

## Usage

### Background Tray App (Recommended)

```
python main.py --tray
```

Or double-click `scripts/start_tray.bat`.

The app runs silently in the system tray and:
1. Monitors the clipboard for new screenshots
2. Automatically processes screenshots taken with Win+Shift+S
3. Shows a toast notification per screenshot with the character count found
4. Saves the match to CSV when all 15 characters are collected
5. Shows a summary notification with the total score

Right-click the tray icon for:
- **Analyze** — opens a scrollable window with the full performance report
- **View Last Match** — shows the most recently recorded match
- **Pause Monitoring** — temporarily stop clipboard detection
- **Exit** — close the application

### Command-Line Recording

```
python main.py
```

Prompts you to take two screenshots sequentially. Useful for debugging or when the tray app is not desired.

### Analysis

```
python main.py --analyze
```

Prints a full performance report to the console, including:
- Team average, best, and worst match totals
- Team trend over recent matches
- Tier classification (S/A/B/C) for each character
- Contribution percentage per character
- Coefficient of variation (consistency metric)
- Replace priority ranking
- Full statistics table

### Debug Mode

```
python main.py --debug
```

Runs OCR on the current clipboard image and shows all detected words, green bar positions, and character name matches. Use `--verbose` for per-crop candidate details.

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
|---|---|---|
| Adjusted Score | `mean - k * std` | Rewards consistency; higher is better |
| Contribution % | `char_mean / total_mean * 100` | What fraction of total score each character provides |
| CV (Coefficient of Variation) | `std / mean * 100` | How reliable a character is relative to its average |
| Replace Priority | Weighted composite of low contribution, high CV, low adjusted | Single ranking for worst-to-best replacement candidates |

## Project Structure

```
├── main.py                 # CLI entry point
├── config.py               # Character names and thresholds
├── ocr.py                  # Clipboard reading and OCR extraction
├── parser.py               # Score parsing and number merging logic
├── storage.py              # CSV read/append
├── analysis.py             # Statistics, tiers, and report generation
├── clipboard_monitor.py    # Background clipboard watcher
├── tray_app.py             # System tray application
├── notifications.py        # Windows toast notifications
├── scripts/
│   └── start_tray.bat      # Double-click launcher
├── data/                   # Match data (gitignored)
├── assets/
│   └── icon.png            # Custom tray icon (gitignored)
├── tests/
│   ├── run_test.py         # Automated test suite
│   ├── dataset.csv         # Expected results
│   └── print[1-4].png      # Test screenshots
├── tray.log                # Runtime log (gitignored)
├── requirements.txt
├── pyproject.toml
└── LICENSE
```

## Testing

```
cd tests
python run_test.py
```

Runs the parser against bundled test screenshots and compares results against expected values.

## Troubleshooting

**No green bars detected**
- Ensure the screenshot captures the character score area with visible green progress bars
- Adjust `CROP_ABOVE_BAR` if the name/score is positioned differently in your screenshots

**Character names not matching**
- Verify names in `config.py` exactly match the in-game names
- Lower `FUZZY_MATCH_THRESHOLD` if OCR consistently misreads certain characters
- Use `--debug` to see what OCR detects for each crop

**Numbers are wrong or missing**
- Use `--debug --verbose` to see all detected numbers and merge candidates
- Check that scores fall within the 10,000-200,000 range (adjust `SCORE_MIN`/`SCORE_MAX` in `parser.py` if needed)

**Tray app not responding**
- Check `tray.log` for error messages
- Ensure no other process is holding the clipboard
- Restart the application

## License

MIT
