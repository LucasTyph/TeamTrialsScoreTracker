# Plan: character ratings and team lineups

Status: agreed with the user, not started. Written 2026-11-12 after commit 87c4f7b
(app-only tracker with average-based analysis). Build it in the three phases at the end.

## Goals

1. Let the user enter each character's **rating** and **aptitudes** on the Roster page, and use
   them to rank which characters are worth replacing first. Sometimes a character who scores
   less makes the whole team better because their rating is higher.
2. **Lineups**: named versions of the 15-character team that can be compared over time.

## Background the user gave

- Every score = base points × (1 + bonus). The bonus grows with the **opponent's** rating, and
  matchmaking pairs similar ratings, so raising your own rating raises the bonus for **all 15**
  characters on average. The effect is indirect and noisy, and opponent ratings aren't captured.
- With the game's **displayed team rating of about 330k** the user sees about **172%** bonus over
  base. Their estimate is **about 0.5 percentage points of bonus per 1k of team rating**
  (330 × 0.52 ≈ 172). They aren't sure exactly what the displayed total includes (probably the
  sum of ratings with S boosts, maybe more). That's fine: use their figures as the prior.
- Each character has three aptitudes that matter for their team, graded G…A, S
  (default **A**; the user never uses anything below A, so don't spend effort on G–B):
  - **surface**: dirt for the Dirt team, turf for every other team;
  - **distance**: the team's distance; **the Dirt team always races Mile**;
  - **racing style**: the style they run (Front/Pace/Late/End), and its grade.
- Each **S instead of A adds 2%** to the character's rating for these calculations.
- The rating the user types is the **base rating, before S boosts**. The app applies the boosts.
- The game can't field duplicates, so one character never appears twice in a match. Between
  lineups, either a character's rating/aptitudes changed (a re-trained version), or character X
  was replaced by character Y.

## Rating model

- `effective_rating = rating × (1 + s_bonus × number_of_S)`, with `s_bonus = 0.02` and up to
  3 S grades (surface, distance, style).
- `bonus(R) = k × R` with `k = 0.005 per 1k` of team rating (setting
  `rating_bonus_per_1k = 0.5`, in percent). R = the lineup's **displayed team rating** if the user
  entered it, else the sum of effective ratings. Store both; show the computed sum next to the
  displayed value so the user can compare them.
- Marginal value of rating: every score scales with (1 + bonus), so adding ΔR of rating changes
  the match total by about `T × k × ΔR / (1 + bonus)`. With T ≈ 1,017k and bonus ≈ 1.72:
  **≈ +1,900 points per match per 1k of rating**, spread over the team. Compute it from current
  data rather than hard-coding it.
- **Rating-neutral (base) score** = observed score / (1 + bonus(R of that match's lineup)).
  Use it to compare characters and lineups fairly across rating changes.
- Characters without a rating count as the team-average rating (so their rating term is zero).
  Nothing should break while ratings are missing.
- Grades below A: store them; treat as A in the maths and show a faint "below A not modelled".

## Versioning: builds and lineups

- **Build**: one trained copy of a character: `id, character, label (e.g. "v2"), rating,
  surface_grade, distance_grade, style, style_grade, created, notes`. A rating is fixed per
  training, so upgrading means **New version** (copy the build) rather than editing. Editing in
  place is for typos.
- **Lineup**: `id, name, created, notes, displayed_rating (optional), slots: {distance: [3 build
  ids]}`. Exactly one lineup is **active**.
- Storage:
  - New `data/roster.json` holding builds, lineups and the active lineup id (the app edits it;
    keep it readable). Write atomically like `save_settings`.
  - `scores.csv` gains a `lineup` column (lineup id). A score's build = the build for that
    character in that match's lineup (unique, since there are no duplicates in a match).
  - Migration: the current `settings.toml` `[teams]` become a lineup named **"Original"** that
    owns every existing match. Builds start with no rating. Old rows without `lineup` map to it.
  - `Settings.roster`/`teams` are derived from the active lineup, so `pipeline.py`/`session.py`
    keep working unchanged. Keep `[teams]` readable for back-compat, but the lineup becomes the
    source of truth; decide whether to stop writing `[teams]` once migrated.
  - New settings: `rating_bonus_per_1k = 0.5`, `s_aptitude_bonus = 0.02`.
- Capture attributes each match to the **active lineup**. Show the active lineup's name on the
  Current match page with a switcher. If a captured name isn't in the active lineup but is in
  another one, say so (likely forgot to switch). Recent matches gets **Move to lineup…**.
- Changing slots in a lineup that already has matches offers **Save as new lineup** (default), so
  history stays truthful. Rating/grade typo fixes edit in place.

## UI

### Roster page (becomes lineup editor)
- Lineup bar: active lineup dropdown, New (copy of current), Rename, Set active, optional
  "Displayed team rating" field.
- Each slot: name (autocomplete as now), rating (optional), surface/distance/style grade pickers
  (default A), style picker, **New version** button.
- Team headers show the team's effective rating; page shows the lineup total vs displayed total.
- Keep the Capture card (hotkey, game process).

### Analysis page
- Lineup filter at the top: all lineups, or one.
- Character table: add Rating, Effective rating, Base score (rating-neutral), **Value**.
  - `Value = average score + marginal_value_per_point × (effective_rating − team-average effective rating)`.
  - Sort by Value to get the replacement order.
- Team cards: team effective rating; mark the weakest member by Value as well as by score, when
  the two differ.
- **Replace first** card: the 3 lowest-Value slots, each with a break-even line, e.g. "a 24k-rating
  replacement needs ≈53.5k per match to break even".
- **What-if** calculator: pick a slot, enter candidate rating + grades + expected score (default:
  the slot's base score re-scaled) → projected change in match total.
- **Compare lineups** (phase 3): pick two lineups → match-average difference with a 95% range,
  per team and per slot, raw and rating-adjusted. Show "not significant yet (n = 7)" and roughly
  how many matches are needed. Today match totals swing ≈4.7% (std ≈48k), so telling apart a ≈3%
  difference takes ≈20 matches per lineup.

## Phases

1. **Ratings on the current roster**: builds + migration to an "Original" lineup (one lineup
   only), rating/grade/style fields, effective rating, settings, Value, Replace first, what-if.
   Tests for the maths (effective rating, marginal value, break-even, base score) and migration.
2. **Lineups**: create/copy/rename/activate, `lineup` column on capture, Move to lineup,
   wrong-lineup warning, lineup filter on Analysis.
3. **Compare view** + **fit k from data**: once two or more lineups with different ratings have
   enough matches, regress log(match total) on lineup rating and show the fitted per-1k bonus
   next to the 0.5% prior. Let the user pick which one to use.

## Ground rules (from the user)

- Fewest screenshots: still only the two Score Info captures per match. Don't add capture of
  other screens without asking (opponent rating capture was declined earlier; it would be the
  biggest accuracy gain if they ever change their mind).
- Match totals = sum of the 15 character scores (ignore official team bonuses).
- No weekly goals or projections.
- Test only on copies of `data/` via `SCORE_TRACKER_DATA`; never modify the real `data/`.
  Check pages visually by rendering `MainWindow` offscreen (`widget.grab().save(...)`).
- Commit and push straight to `main`.
