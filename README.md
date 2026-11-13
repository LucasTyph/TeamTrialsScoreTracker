# Team Trials Score Tracker

A desktop app that reads your Team Trials results in Umamusume: Pretty Derby and shows, from averages over every match you record, which of your teams and characters are strong and which hold your score back.

- **Two key presses per match.** On a race's Score Info screen, press the capture hotkey at the top of the list and again at the bottom. The app captures the game window directly (no snipping), reads all 15 names, scores and distances, and saves the match.
- **Easy fixes when OCR misses.** Any row it can't read shows up with its picture, so you can confirm who it is in one click. A single unread row per team is filled in automatically.
- **Your five teams.** Set up Sprint, Mile, Medium, Long and Dirt (or fill them from a screenshot). Each saved score remembers the team it was earned in.
- **Stable, average-based analysis.** Every score includes opponent and support bonuses, so single matches are noisy. Averages over all your matches even that out, so you can see which teams and characters raise your score on average and which drag it down.

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

Or install it with `pip install .`, which adds a `score-tracker` command that opens the app.

## Getting started

```bash
python -m score_tracker
```

Or double-click `scripts/start.bat`, which opens the app without a console window. Closing the window quits the app; a match that's still missing characters is saved as partial first.

### As a Windows app (.exe)

```bash
pip install -e ".[build]"
python scripts/build_exe.py --shortcut
```

This builds `dist/TeamTrialsScoreTracker/TeamTrialsScoreTracker.exe` (no console window, no Python needed to run it) and adds **Team Trials Score Tracker** shortcuts to the Desktop and Start menu (leave out `--shortcut` to skip them). The .exe uses this checkout's `data/` folder, so keep it where it was built, and rebuild after pulling changes. `scripts/start.bat` also opens the .exe when it exists. A splash screen shows while the app loads, either way. Tesseract is still a separate install.

1. **Roster.** Type your 15 racers into the five teams (names autocomplete), or open a race's Score Info in the game and click **Fill from game screen**: it reads the names and each one's distance badge. Do it once at the top of the list and once at the bottom, check the names, then **Save**.
2. **Capture a match.** In the game, open the race's **Score Info** and press the capture hotkey (`Ctrl+Alt+S` by default). Drag the list to the bottom and press it again. The match saves itself once all 15 are found, with a notice in the window (and a flashing taskbar button if you're in the game). `Win+Shift+S` snips work too: the app watches the clipboard while **Watch the clipboard** is ticked on the **Current match** page.
3. **Fix what OCR missed.** If a row couldn't be read, the **Current match** page shows its picture with the most likely missing name preselected. Click **Assign**, or type a missing score straight into its slot.
4. **Flag bad reads.** If a screenshot missed or misread someone, click **⚑ Flag last capture** on the **Current match** page (with an optional note). The screenshot and everything read from it are kept in the data folder's `flagged/` folder as examples for improving the OCR later; nothing else uses them yet.
5. **Analysis.** Open the **Analysis** page any time. Click a character in the table to see their history.

The hotkey works from anywhere and captures the game window even when it's behind other windows. It never captures the rest of your screen.

## The analysis

Every score in the game is base points × (1 + opponent-rating bonus + support bonus), so a single match says as much about who you faced as about your team. The analysis therefore sticks to **averages over everything you've recorded**, which get steadier with every match.

- **Overview.** Matches recorded (complete and partial), average and median match total, best and worst match, and **recent form**: the average of your last 10 complete matches compared with your overall average.
- **Teams.** One card per distance, ranked strongest to weakest by average team total, with its share of the match total, best, worst and CV (spread relative to the average), and recent form. Members are sorted by average, with each one's share of the team total and how far they sit from the team's per-member average. A bar chart compares the five teams.
- **Replace first** and **Top performers.** The three weakest and the three strongest racers of the lineup (by Value once ratings are in, else by average), each with an archetype (*Low ceiling*, *Boom or bust*, *Inconsistent*, *Reliable star*, …), a strip showing their worst-to-best range against the average racer, and the numbers behind it: their difference from the match average with its 95% range, how often they beat it, ceiling, floor and consistency ranked among the 15, average as a share of their best, and what their rating adds or costs per match.
- **Match totals.** Every complete match in order, with a 10-match rolling average and your overall average.
- **Characters.** A sortable table: team, matches, average, median, best, worst, std, CV, average share of team total, average rank in team (1–3) and in the match (1–15), and how often they top the match (plus Value, rating, effective rating and base score once ratings are in). Click one for their score history (with a rolling average) and the 95% range of their average, their gap to the team's per-member average and, for racers who changed teams, their average in each.
- **Recent matches.** Each match's total, its lineup and its difference from your average. Delete a bad capture here, or **Move…** it to another lineup.

### Ratings and lineups

On the **Roster** page each racer has an optional **rating** (the base rating, before S boosts) and their **surface**, **distance** and **racing style** aptitudes (S or A; Dirt teams race Mile). Each S instead of A adds 2% to the rating. You can also enter the game's **displayed team rating**.

Every score is base points × (1 + bonus), and the bonus grows with your opponents' rating, which matchmaking keeps close to yours (about 0.5 percentage points per 1k of team rating). So a higher-rated racer raises all 15 scores a little, and someone who scores less can still be the better pick. The analysis turns that into:

- **Value**: a racer's average score plus what their rating adds to the rest of the team, compared with a racer at the lineup's average rating. Sort the character table by it.
- **Base score**: the rating-neutral average (each score divided by 1 + bonus), to compare across rating changes.
- **Replace first** ranks by Value.

Racers without a rating count as the lineup's average, so nothing changes until you enter some.

**Lineups** are named versions of your 15. Each captured match is saved to the **active** lineup (switch it on the **Current match** page; the app warns if it reads a racer from another lineup). Re-trained a racer? Use **New version** on their slot. Changing who's in a lineup that already has matches offers to **save it as a new lineup**, so history stays truthful. On the Analysis page, filter by lineup, **compare two lineups** (difference per match, team and slot, with a 95% range and roughly how many matches it takes to tell), and, once two lineups with different ratings have a few matches each, see the **bonus per 1k fitted from your data** next to the 0.5% estimate, and choose which one to use.

Rules:
- Match totals are the sum of the 15 racers' scores. The game's own total also adds team bonuses, so it's a little higher; since that difference is consistent, comparisons aren't affected.
- Match totals and the overview use complete matches only (all 15 racers). Team stats use the matches where all three of that team's members were read. Character stats use every match the character appears in.
- Teams come from the distance badge saved with each score (who actually ran where), so moving a racer to another team doesn't rewrite the past. Scores saved without one use the racer's current team.
- Times are your computer's local time.

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
| `capture_hotkey` | `ctrl+alt+s` | Global capture hotkey (`ctrl`, `alt`, `shift`, `win` + a letter, digit or `F1`–`F24`) |
| `game_process` | `umamusumeprettyderby.exe` | The game's process, for window capture |
| `tesseract_cmd` | `C:\Program Files\Tesseract-OCR\tesseract.exe` | Path to `tesseract.exe` |
| `pending_timeout_minutes` | 10 | Save an incomplete match as partial after this long without new screenshots |
| `row_tolerance`, `fuzzy_match_threshold`, `min_bar_width` | 20, 0.6, 100 | OCR tuning |
| `rating_bonus_per_1k` | 0.5 | Score bonus (percentage points) per 1k of team rating |
| `s_aptitude_bonus` | 0.02 | Rating boost per S aptitude instead of A |
| `use_fitted_bonus` | `false` | Use the bonus fitted from your lineups instead (toggle on the Analysis page) |

Lineups, racers' ratings and aptitudes live in `roster.json` in the data folder. The `[teams]` in `settings.toml` mirror the active lineup and are only read the first time, to create the lineup "Original".

Settings from older versions (`matches_per_week`, `week_reset_weekday`, `week_reset_hour_utc`, `target_score`) are ignored and dropped the next time you save from the app.

## How it works

1. **Find the rows.** Each character row on Score Info has a green progress bar. The app finds the longest green run on each line of pixels, groups them into bars, and keeps the set of thin bars that share a left edge. That works on a tight snip or on the whole game window, skipping headers and other green UI. Rows are evenly spaced, so it also looks one row below the last bar, where a row's name can be visible even though its bar is scrolled out of view.
2. **Crop around each bar.** The name and score sit above the bar; the distance badge sits under the portrait to its left.
3. **Read.** Tesseract reads each crop in grayscale first, then in colour, then enlarged 3×, until a name and score are found. The badge's white text is isolated from the pill before reading.
4. **Match names.** OCR words are matched to your roster, trying the row's team first. Rows already recorded (from the other screenshot) are recognised as duplicates instead of being matched to a similar name.
5. **Fill gaps.** If one character is missing from a team and one unread row from that team has a score, they belong together.

## Data storage

Scores are stored in `scores.csv`, one row per character score:

```text
match_id,timestamp,character,score,distance,lineup
1,2026-11-02 22:33:00,Agnes Digital,65582,Dirt,l1
```

`distance` is the team the character raced in for that match, from the screenshot's badge or your roster. `lineup` is the id of the lineup it was played with (empty for matches saved before lineups, which belong to "Original"). Older files are upgraded automatically.

## Project structure

```text
├── score_tracker/
│   ├── gui/                  # PySide6 app: window, pages, theme (app.py has run())
│   ├── capture.py            # Capture the game window (Windows)
│   ├── pipeline.py           # Screenshot → rows → match (shared by the app and tests)
│   ├── session.py            # Assembles screenshots into matches
│   ├── ocr.py                # Row detection, crops, preprocessing, distance badges
│   ├── parser.py             # Name matching and score parsing
│   ├── analysis.py           # Average-based match, team and character stats
│   ├── profiles.py           # Why a racer is weak or strong (Replace first, Top performers)
│   ├── flagged.py            # Screenshots flagged as misread, kept for OCR work
│   ├── launch.py             # Entry point: splash screen, then the app
│   ├── ratings.py            # Rating model: Value, break-even, what-if, fit, lineup comparison
│   ├── lineups.py            # Builds and lineups (roster.json)
│   ├── storage.py            # scores.csv
│   ├── config.py             # Settings and settings.toml
│   ├── characters.py         # Known names for autocomplete
│   └── assets/icon.png       # App icon
├── main.py                   # Shortcut for python -m score_tracker
├── scripts/start.bat         # Windows launcher (no console window)
├── scripts/build_exe.py      # Builds the .exe with PyInstaller
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
| **"Tesseract OCR was not found"** | Install Tesseract (see [Requirements](#requirements)) and check `tesseract_cmd`, then restart the app. |
| **"Couldn't capture the game"** | Make sure the game is running and not minimized. If it runs under a different process name, set it on the Roster page. |
| **"Hotkey unavailable"** | Another program uses that key combination. Pick another on the Roster page. |
| **A name keeps failing** | Check the spelling on the Roster page matches the game exactly. The row shows up under **Rows to review** with what OCR read. |
| **The app doesn't open** | Run `python -m score_tracker` from a terminal to see the error, and check `data/tracker.log`. |

## License

This project is licensed under the [MIT License](LICENSE).
