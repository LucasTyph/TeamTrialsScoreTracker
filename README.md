# Team Trials Score Tracker

A desktop app that reads your Team Trials results in Umamusume: Pretty Derby and tells you what to change to raise your **weekly top score**, the single best match that decides your class each week.

- **Two key presses per match.** On a race's Score Info screen, press the capture hotkey at the top of the list and again at the bottom. The app captures the game window directly (no snipping), reads all 15 names, scores and distances, and saves the match.
- **Easy fixes when OCR misses.** Any row it can't read shows up with its picture, so you can confirm who it is in one click. A single unread row per team is filled in automatically.
- **Your five teams.** Set up Sprint, Mile, Medium, Long and Dirt (or fill them from a screenshot). Each saved score remembers the team it was earned in.
- **Analysis built for the weekly best.** How likely you are to beat this week's best, your projected weekly best, and which racer in each team is holding it back.

## Requirements

- Windows, with the game running in its own window
- [Python 3.10+](https://www.python.org/downloads/)
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki), installed via the UB-Mannheim releases or `winget install UB-Mannheim.TesseractOCR`
  - Default path: `C:\Program Files\Tesseract-OCR\tesseract.exe`
  - Elsewhere? Set `tesseract_cmd` in `settings.toml`, or put `tesseract` on your `PATH`

## Installation

```bash
pip install -r requirements.txt
```

Or install it as a command with `pip install .`, which adds `score-tracker` (same options as `python -m score_tracker`).

## Getting started

```bash
python -m score_tracker --app
```

Or double-click `scripts/start_tray.bat`. The app opens a window and puts its icon in the system tray. Closing the window keeps it running in the tray; use the tray menu's **Exit** to quit. Use `--tray` to start without the window.

1. **Roster.** Type your 15 racers into the five teams (names autocomplete), or open a race's Score Info in the game and click **Fill from game screen**: it reads the names and each one's distance badge. Do it once at the top of the list and once at the bottom, check the names, then **Save**.
2. **Capture a match.** In the game, open the race's **Score Info** and press the capture hotkey (`Ctrl+Alt+S` by default). Drag the list to the bottom and press it again. The match saves itself once all 15 are found. `Win+Shift+S` snips still work too: the app watches the clipboard.
3. **Fix what OCR missed.** If a row couldn't be read, the **Current match** page shows its picture with the most likely missing name preselected. Click **Assign**, or type a missing score straight into its slot.
4. **Analysis.** Open the **Analysis** page any time.

The hotkey works from anywhere and captures the game window even when it's behind other windows. It never captures the rest of your screen.

## The analysis

Your class each week is decided by your **best** match, not your average, so the analysis is built around peaks:

- **Projected weekly best.** If your match totals average μ with spread σ, the best of *n* matches lands around μ + c(n)·σ, where c(35) ≈ 2.1. Spread helps here: with 35 tries, one great match is worth more than a steady average.
- **Chance to beat this week's best** (or your target score) in the matches you have left.
- **Each racer's share** of the projected weekly best: their average plus a bonus for scoring high in your best matches (μᵢ + c·cov(xᵢ, total)/σ). The shares add up to the projected weekly best.
- **Upgrade target.** The weakest share in each team is where a better racer raises your weekly best the most.
- **In top matches.** How much more (or less) a racer scores in your best 20% of matches compared with their average. Racers who dip when you peak hold your weekly best back.

Notes:
- Match totals are the sum of the 15 racers' scores. The game's own total also adds team bonuses, so it's a little higher; since that difference is consistent, comparisons aren't affected.
- Only complete matches (all 15 racers) count toward weekly bests and the model. Partial matches still count toward each racer's history.
- Times are shown in UTC to match the game. Set when your week resets on the Roster page.

## Settings

Your settings live in `settings.toml` in the data folder (not tracked by git). Most can be changed in the app; all can be edited by hand:

| Running from | Data folder |
| --- | --- |
| A checkout of this repo | `data/` |
| `pip install .` | `%LOCALAPPDATA%\TeamTrialsScoreTracker` |
| Anywhere, with `SCORE_TRACKER_DATA` set | that folder |

| Setting | Default | Description |
| --- | --- | --- |
| `[teams]` | — | `Sprint`, `Mile`, `Medium`, `Long`, `Dirt`: three names each |
| `roster` | `[]` | Characters not on a team (kept for old matches) |
| `matches_per_week` | 35 | How many matches you play per week |
| `week_reset_weekday`, `week_reset_hour_utc` | 0, 0 | When the Team Trials week resets (0 = Monday) |
| `target_score` | 0 | A score you're aiming for, shown in the analysis |
| `capture_hotkey` | `ctrl+alt+s` | Global capture hotkey (`ctrl`, `alt`, `shift`, `win` + a letter, digit or `F1`–`F24`) |
| `game_process` | `umamusumeprettyderby.exe` | The game's process, for window capture |
| `tesseract_cmd` | `C:\Program Files\Tesseract-OCR\tesseract.exe` | Path to `tesseract.exe` |
| `pending_timeout_minutes` | 10 | Save an incomplete match as partial after this long without new screenshots |
| `row_tolerance`, `fuzzy_match_threshold`, `min_bar_width` | 20, 0.6, 100 | OCR tuning |

## Command line

| Command | What it does |
| --- | --- |
| `python -m score_tracker --app` | Open the app |
| `python -m score_tracker --tray` | Start the app in the tray, without the window |
| `python -m score_tracker` | Record a match in the terminal from two clipboard screenshots |
| `python -m score_tracker --analyze` | Print the analysis |
| `python -m score_tracker --debug` | Show what OCR reads from the clipboard image |

## How it works

1. **Find the rows.** Each character row on Score Info has a green progress bar. The app finds the longest green run on each line of pixels, groups them into bars, and keeps the set of thin bars that share a left edge. That works on a tight snip or on the whole game window, skipping headers and other green UI. Rows are evenly spaced, so it also looks one row below the last bar, where a row's name can be visible even though its bar is scrolled out of view.
2. **Crop around each bar.** The name and score sit above the bar; the distance badge sits under the portrait to its left.
3. **Read.** Tesseract reads each crop in grayscale first, then in colour, then enlarged 3×, until a name and score are found. The badge's white text is isolated from the pill before reading.
4. **Match names.** OCR words are matched to your roster, trying the row's team first. Rows already recorded (from the other screenshot) are recognised as duplicates instead of being matched to a similar name.
5. **Fill gaps.** If one character is missing from a team and one unread row from that team has a score, they belong together.

## Data storage

Scores are stored in `scores.csv`, one row per character score:

```text
match_id,timestamp,character,score,distance
1,2026-11-02 22:33:00,Agnes Digital,65582,Dirt
```

`distance` is the team the character raced in for that match, from the screenshot's badge or your roster. Older files are upgraded automatically.

## Project structure

```text
├── score_tracker/
│   ├── gui/                  # PySide6 app: window, pages, theme, tray icon
│   ├── cli.py                # Command-line entry point
│   ├── capture.py            # Capture the game window (Windows)
│   ├── pipeline.py           # Screenshot → rows → match (shared by app, CLI and tests)
│   ├── session.py            # Assembles screenshots into matches
│   ├── ocr.py                # Row detection, crops, preprocessing, distance badges
│   ├── parser.py             # Name matching and score parsing
│   ├── analysis.py           # Weekly-top-score analysis
│   ├── storage.py            # scores.csv
│   ├── config.py             # Settings and settings.toml
│   ├── characters.py         # Known names for autocomplete
│   └── assets/icon.png       # App and tray icon
├── main.py                   # Shortcut for python -m score_tracker
├── scripts/start_tray.bat    # Windows launcher
├── data/                     # Your settings and scores (gitignored)
└── tests/                    # pytest suite with real screenshots
```

## Testing

```bash
pip install pytest
python -m pytest
```

Most tests use synthetic OCR data and run anywhere. `tests/test_screenshots.py` runs real screenshots through Tesseract: snips of two matches (`print1-4.png`) and full game-window captures of a third (`window1-2.png`). It's skipped where Tesseract isn't installed (as in CI).

## Troubleshooting

| Issue | Solution |
| --- | --- |
| **`Tesseract OCR was not found`** | Install Tesseract (see [Requirements](#requirements)) and check `tesseract_cmd`. |
| **"Couldn't capture the game"** | Make sure the game is running and not minimized. If it runs under a different process name, set it on the Roster page. |
| **"Hotkey unavailable"** | Another program uses that key combination. Pick another on the Roster page. |
| **A name keeps failing** | Check the spelling on the Roster page matches the game exactly. Use `--debug` to see what OCR reads. |
| **Something else** | Check `data/tracker.log`. |

## License

This project is licensed under the [MIT License](LICENSE).
