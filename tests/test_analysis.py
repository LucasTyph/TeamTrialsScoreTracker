import pandas as pd
import pytest

from score_tracker.analysis import analyze, form, rolling_mean, spread
from score_tracker.config import Settings

# Two teams of three: a 6-character "complete match"
TEAMS = {"A": "Sprint", "B": "Sprint", "C": "Sprint", "D": "Dirt", "E": "Dirt", "F": "Dirt"}


def _scores(rows, distances=None):
    """rows: (match_id, timestamp, {name: score}); distances default to TEAMS."""
    distances = TEAMS if distances is None else distances
    out = []
    for mid, ts, scores in rows:
        for name, score in scores.items():
            out.append({"match_id": mid, "timestamp": ts, "character": name, "score": score,
                        "distance": distances.get(name, "")})
    return pd.DataFrame(out)


def _ts(i):
    return f"2026-11-{1 + i // 24:02d} {i % 24:02d}:00:00"


@pytest.fixture
def settings(tmp_path):
    return Settings(roster=tuple(TEAMS), teams=TEAMS, data_dir=tmp_path)


def test_rolling_mean():
    assert rolling_mean([1, 2, 3, 4], window=2) == [1, 1.5, 2.5, 3.5]
    assert rolling_mean([]) == []


def test_form_needs_more_than_the_window():
    assert form([1, 2, 3], window=3) is None
    f = form([10, 10, 20, 20], window=2)
    assert (f.recent, f.overall) == (20, 15)
    assert f.delta == 5 and f.pct == pytest.approx(1 / 3)


def test_spread():
    s = spread([10, 20, 30, 40])
    assert (s.n, s.mean, s.median, s.best, s.worst) == (4, 25, 25, 40, 10)
    assert s.std == pytest.approx(12.909944)
    assert s.cv == pytest.approx(s.std / 25)
    assert s.se == pytest.approx(s.std / 2)
    assert spread([]).n == 0


def test_no_data(settings):
    assert analyze(pd.DataFrame(), settings) is None


def test_overview_uses_complete_matches_only(settings):
    full = {"A": 10, "B": 20, "C": 30, "D": 40, "E": 50, "F": 60}  # 210
    rows = [
        (1, _ts(0), full),
        (2, _ts(1), {k: v * 2 for k, v in full.items()}),  # 420
        (3, _ts(2), {"A": 999, "B": 999}),  # partial
        (4, _ts(3), {k: v * 3 for k, v in full.items()}),  # 630
    ]
    a = analyze(_scores(rows), settings)
    o = a.overview
    assert (o.matches, o.complete, o.partial) == (4, 3, 1)
    assert o.totals.mean == 420 and o.totals.median == 420
    assert (o.best.total, o.worst.total) == (630, 210)
    assert o.best.match_id == 4
    assert o.form is None  # not more than 10 complete matches yet
    assert [m.complete for m in a.matches] == [True, True, False, True]


def test_recent_form(settings):
    rows = [(i, _ts(i), {n: (100 if i < 5 else 200) for n in TEAMS}) for i in range(15)]
    f = analyze(_scores(rows), settings).overview.form
    assert f.recent == 1200  # last 10 matches: all 200 × 6
    assert f.overall == pytest.approx((5 * 600 + 10 * 1200) / 15)
    assert f.delta > 0 and f.pct > 0


def test_team_board(settings):
    rows = [
        (1, _ts(0), {"A": 100, "B": 50, "C": 30, "D": 60, "E": 60, "F": 60}),
        (2, _ts(1), {"A": 120, "B": 70, "C": 50, "D": 80, "E": 70, "F": 30}),
    ]
    a = analyze(_scores(rows), settings)
    sprint, dirt = a.teams
    assert (sprint.distance, dirt.distance) == ("Sprint", "Dirt")
    assert sprint.totals.mean == 210 and dirt.totals.mean == 180
    assert (sprint.rank, dirt.rank) == (1, 2)
    assert (sprint.totals.best, sprint.totals.worst) == (240, 180)
    assert sprint.share_of_match == pytest.approx((180 / 360 + 240 / 420) / 2)
    assert [m.name for m in sprint.members] == ["A", "B", "C"]
    assert sprint.top.name == "A" and sprint.weakest.name == "C"
    assert sprint.weakest_gap == pytest.approx(40 - 70)
    assert sum(m.share for m in sprint.members) == pytest.approx(1)
    assert sprint.history[0][1] == 180


def test_teams_need_all_three_members(settings):
    rows = [
        (1, _ts(0), {"A": 100, "B": 100, "C": 100, "D": 10, "E": 10, "F": 10}),
        (2, _ts(1), {"A": 900, "B": 900, "D": 20, "E": 20, "F": 20}),  # Sprint incomplete
    ]
    a = analyze(_scores(rows), settings)
    sprint, dirt = a.teams
    assert sprint.totals.n == 1 and sprint.totals.mean == 300
    assert dirt.totals.n == 2
    # But characters count every match they appear in
    a_stats = next(c for c in a.characters if c.name == "A")
    assert a_stats.scores.n == 2 and a_stats.scores.mean == 500
    assert a_stats.rank_in_team == 1  # only the complete-team match


def test_teams_come_from_the_distance_column(settings):
    """A character moved from Dirt to Sprint: old scores stay with Dirt."""
    old = {"A": 10, "B": 10, "C": 10, "D": 50, "E": 10, "F": 10}
    new = {"A": 10, "B": 10, "C": 10, "D": 10, "E": 10, "F": 10}
    raced_old = dict(TEAMS)
    raced_new = {**TEAMS, "C": "Dirt", "D": "Sprint"}
    df = pd.concat([_scores([(1, _ts(0), old)], raced_old), _scores([(2, _ts(1), new)], raced_new)])
    settings_now = Settings(roster=tuple(TEAMS), teams=raced_new, data_dir=settings.data_dir)
    a = analyze(df, settings_now)
    dirt = next(t for t in a.teams if t.distance == "Dirt")
    assert dirt.history[0][1] == 70  # D's 50 counted in Dirt in match 1
    assert {m.name for m in dirt.members} == {"C", "D", "E", "F"}
    assert not next(m for m in dirt.members if m.name == "D").current
    # Former members don't count as the team's top or weakest
    assert dirt.top.name != "D"
    d = next(c for c in a.characters if c.name == "D")
    assert d.team == "Sprint"
    assert {p.distance for p in d.by_team} == {"Sprint", "Dirt"}


def test_empty_distance_falls_back_to_current_teams(settings):
    rows = [(1, _ts(0), {n: 10 for n in TEAMS})]
    a = analyze(_scores(rows, distances={}), settings)
    assert [t.distance for t in a.teams] == ["Sprint", "Dirt"]


def test_character_stats(settings):
    rows = [
        (1, _ts(0), {"A": 100, "B": 50, "C": 30, "D": 60, "E": 60, "F": 20}),
        (2, _ts(1), {"A": 40, "B": 70, "C": 50, "D": 80, "E": 70, "F": 30}),
    ]
    a = analyze(_scores(rows), settings)
    a_stats = next(c for c in a.characters if c.name == "A")
    assert a_stats.team == "Sprint"
    assert (a_stats.scores.mean, a_stats.scores.best, a_stats.scores.worst) == (70, 100, 40)
    assert a_stats.share_of_team == pytest.approx((100 / 180 + 40 / 160) / 2)
    assert a_stats.rank_in_team == pytest.approx((1 + 3) / 2)
    assert a_stats.rank_in_match == pytest.approx((1 + 5) / 2)
    assert a_stats.top_of_team == 0.5 and a_stats.top_of_match == 0.5
    sprint_per_member = (180 + 160) / 2 / 3
    assert a_stats.above_team_avg == pytest.approx(70 - sprint_per_member)
    assert [h[2] for h in a_stats.history] == [100, 40]
    assert a_stats.best_match[1] == 100 and a_stats.worst_match[1] == 40
    # Highest average first
    assert a.characters[0].scores.mean == max(c.scores.mean for c in a.characters)


def test_mixed_timestamp_formats(settings):
    rows = [(1, "2026-11-02 22:33", {"A": 1}), (2, "2026-11-12 14:00:21", {"A": 2})]
    a = analyze(_scores(rows), settings)
    assert [m.match_id for m in a.matches] == [1, 2]


def test_without_settings_teams_complete_size_is_inferred(tmp_path):
    rows = [(1, _ts(0), {"A": 1, "B": 2}), (2, _ts(1), {"A": 1})]
    a = analyze(_scores(rows, distances={}), Settings(data_dir=tmp_path))
    assert a.match_size == 2
    assert [m.complete for m in a.matches] == [True, False]
    assert a.teams == []
