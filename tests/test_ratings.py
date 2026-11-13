import math

import pandas as pd
import pytest

from score_tracker.analysis import analyze
from score_tracker.config import Settings, load_settings, save_settings
from score_tracker.lineups import Build, Roster, apply_lineup, load_roster, migrate_from_settings, save_roster
from score_tracker.ratings import (
    base_score,
    bonus,
    break_even,
    diff,
    effective_rating,
    fit_bonus,
    lineup_rating,
    marginal_per_point,
    value,
    what_if,
)

TEAMS = {"A": "Sprint", "B": "Sprint", "C": "Sprint", "D": "Dirt", "E": "Dirt", "F": "Dirt"}


@pytest.fixture
def settings(tmp_path):
    return Settings(roster=tuple(TEAMS), teams=TEAMS, data_dir=tmp_path)


# --- maths -----------------------------------------------------------------------

def test_effective_rating_adds_2_percent_per_s():
    b = Build("b1", "A", rating=20000, surface_grade="S", distance_grade="S", style_grade="A")
    assert effective_rating(b, 0.02) == pytest.approx(20800)
    assert effective_rating(Build("b2", "A"), 0.02) is None


def test_grades_below_a_count_as_a():
    b = Build("b1", "A", rating=20000, distance_grade="B")
    assert b.below_a
    assert effective_rating(b, 0.02) == 20000


def test_bonus_matches_the_users_figures():
    # 330k displayed rating at 0.52% per 1k ≈ +172%
    assert bonus(330_000, 0.52) == pytest.approx(1.716)
    assert base_score(265_000, 330_000, 0.5) == pytest.approx(100_000)


def test_marginal_value_per_1k():
    # T ≈ 1,017k, bonus ≈ 1.72 → ≈ +1,900 points per 1k of rating
    m = marginal_per_point(1_017_000, 344_000, 0.5)
    assert m * 1000 == pytest.approx(1_017_000 * 0.005 / 2.72)
    assert 1800 < m * 1000 < 1950


def test_value_and_break_even():
    m = 1.9  # per rating point
    assert value(60_000, 22_000, 21_000, m) == pytest.approx(61_900)
    assert value(60_000, None, 21_000, m) == 60_000  # unrated counts as average
    # A 24k replacement for a 20k racer averaging 61.1k needs 7.6k less
    assert break_even(61_100, 20_000, 24_000, m) == pytest.approx(53_500)


def test_what_if_defaults_to_same_base_points():
    T, R, k = 1_000_000, 300_000, 0.5
    total, expected = what_if(T, R, k, 60_000, 20_000, 20_000)
    assert total == pytest.approx(T) and expected == pytest.approx(60_000)
    total, expected = what_if(T, R, k, 60_000, 20_000, 22_000)
    scale = (1 + bonus(302_000, k)) / (1 + bonus(R, k))
    assert total == pytest.approx(T * scale)
    # A replacement scoring less but rated higher can still come out ahead
    total, _ = what_if(T, R, k, 60_000, 20_000, 24_000, expected=57_000)
    assert total > T


def test_lineup_rating_fills_unrated_with_the_average():
    r = Roster()
    l = r.new_lineup("L")
    for name, rating in (("A", 20000), ("B", 22000), ("C", None)):
        l.slots["Sprint"].append(r.new_build(name, rating=rating).id)
    lr = lineup_rating(r, l, 0.02)
    assert lr.mean_eff == 21000 and lr.computed == 63000 and lr.rated == 2
    assert lr.rating == 63000
    l.displayed_rating = 330000
    assert lineup_rating(r, l, 0.02).rating == 330000


def test_fit_recovers_k():
    k = 0.5
    points = []
    for lid, R in (("l1", 300_000), ("l2", 320_000), ("l3", 340_000)):
        for noise in (-0.01, 0, 0.01):
            points.append((lid, R, 400_000 * (1 + bonus(R, k)) * (1 + noise)))
    fit = fit_bonus(points)
    assert fit.per_1k == pytest.approx(0.5, abs=0.01)
    assert fit.lineups == 3
    assert fit_bonus(points[:3]) is None  # one lineup only


def test_diff_and_matches_needed():
    d = diff([100, 102, 98, 100], [103, 105, 101, 103])
    assert d.delta == 3 and d.significant
    d = diff([100, 110, 90], [101, 111, 91])
    assert not d.significant
    assert d.needed() > 3


# --- lineups ------------------------------------------------------------------------

def test_migration_creates_original_lineup(settings):
    roster = load_roster(settings)
    assert [l.name for l in roster.lineups] == ["Original"]
    assert roster.teams(roster.active_lineup) == TEAMS
    assert all(b.rating is None for b in roster.builds.values())
    assert (settings.data_dir / "roster.json").exists()
    # Old rows without a lineup belong to it
    assert roster.resolve_lineup("") == roster.active


def test_roster_round_trip(settings):
    roster = migrate_from_settings(settings)
    b = roster.builds[roster.active_lineup.slots["Sprint"][0]]
    b.rating, b.surface_grade, b.style = 21000, "S", "Pace"
    v2 = roster.new_version(b)
    assert v2.label == "v2" and v2.rating == 21000 and v2.id != b.id
    new = roster.new_lineup("Second", source=roster.active_lineup)
    new.slots["Sprint"][0] = v2.id
    new.displayed_rating = 330000
    save_roster(roster, settings)
    loaded = load_roster(settings)
    assert loaded.builds == roster.builds
    assert [l.name for l in loaded.lineups] == ["Original", "Second"]
    assert loaded.lineup(new.id).displayed_rating == 330000


def test_settings_follow_the_active_lineup(settings):
    roster = migrate_from_settings(settings)
    new = roster.new_lineup("Swap", source=roster.active_lineup)
    new.slots["Sprint"][0] = roster.new_build("Z").id
    roster.active = new.id
    s = apply_lineup(settings.with_roster(("A", "B", "C", "D", "E", "F", "Old"), TEAMS), roster)
    assert s.teams["Z"] == "Sprint" and "A" not in s.teams
    assert s.roster[-1] == "Old"  # unassigned names are kept
    assert "A" not in s.roster  # the old lineup's racer isn't unassigned


def test_bool_setting_round_trip(tmp_path):
    s = Settings(data_dir=tmp_path, use_fitted_bonus=True, rating_bonus_per_1k=0.52)
    save_settings(s)
    loaded = load_settings(tmp_path)
    assert loaded.use_fitted_bonus is True and loaded.rating_bonus_per_1k == 0.52


# --- analysis -----------------------------------------------------------------------

def _scores(matches):
    rows = []
    for mid, lineup, scores in matches:
        for name, score in scores.items():
            rows.append({"match_id": mid, "timestamp": f"2026-11-01 {mid:02d}:00", "character": name,
                         "score": score, "distance": TEAMS.get(name, "Sprint"), "lineup": lineup})
    return pd.DataFrame(rows)


def test_analysis_value_and_lineup_filter(settings):
    roster = migrate_from_settings(settings)
    first = roster.active_lineup
    for name, rating in zip("ABCDEF", (20000, 20000, 20000, 20000, 20000, 26000)):
        roster.build_for(first, name).rating = rating
    second = roster.new_lineup("Second", source=first)
    second.slots["Sprint"][0] = roster.new_build("G", rating=24000).id
    base = {"A": 60000, "B": 60000, "C": 60000, "D": 60000, "E": 60000, "F": 55000}
    data = _scores([(1, "", base), (2, "", base),
                    (3, second.id, {**{k: v for k, v in base.items() if k != "A"}, "G": 59000})])
    s = apply_lineup(settings, roster)
    a = analyze(data, s, roster)
    ra = a.ratings
    assert ra.reference.lineup.id == first.id
    assert [m.lineup for m in a.matches] == [first.id, first.id, second.id]
    # F scores least but is rated highest: their Value beats their average
    f = ra.by_name["F"]
    assert f.value > f.average
    assert ra.replace_first(1)[0].name != "F"
    assert ra.base_by_name["A"] == pytest.approx(60000 / (1 + bonus(ra.reference.rating, 0.5)))

    only_second = analyze(data, s, roster, lineup=second)
    assert [m.match_id for m in only_second.matches] == [3]
    assert only_second.ratings.reference.lineup.id == second.id
    assert analyze(data, s, roster, lineup=roster.new_lineup("Empty")) is None


def test_analysis_without_ratings_still_works(settings):
    roster = migrate_from_settings(settings)
    data = _scores([(1, "", {n: 60000 for n in TEAMS})])
    a = analyze(data, apply_lineup(settings, roster), roster)
    assert a.ratings.marginal is None
    assert all(s.value == s.average for s in a.ratings.slots)
    assert not math.isnan(a.overview.totals.mean)


def test_wrong_lineup_names(settings):
    pytest.importorskip("PySide6")
    from score_tracker.gui.app import wrong_lineup_names
    from score_tracker.pipeline import UNNAMED, ImageResult, RowResult
    roster = migrate_from_settings(settings)
    other = roster.new_lineup("Other", source=roster.active_lineup)
    other.slots["Dirt"][0] = roster.new_build("Oguri Cap").id
    result = ImageResult(rows=[RowResult(read_text="Oguri Cop", status=UNNAMED, score=1)])
    assert wrong_lineup_names(roster, apply_lineup(settings, roster), result) == {"Oguri Cap": "Other"}
