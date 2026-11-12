from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from score_tracker.analysis import (
    build_report,
    expected_max_z,
    format_report,
    prob_at_least_one_above,
    week_start,
)
from score_tracker.config import Settings

TEAMS = {"A": "Sprint", "B": "Sprint", "C": "Dirt"}


def _scores(rows):
    """rows: (match_id, local timestamp, {name: score})"""
    out = []
    for mid, ts, scores in rows:
        for name, score in scores.items():
            out.append({"match_id": mid, "timestamp": ts, "character": name, "score": score,
                        "distance": TEAMS.get(name, "")})
    return pd.DataFrame(out)


def _local(dt_utc):
    return dt_utc.astimezone().strftime("%Y-%m-%d %H:%M:%S")


@pytest.fixture
def settings(tmp_path):
    return Settings(roster=tuple(TEAMS), teams=TEAMS, data_dir=tmp_path, matches_per_week=35)


def test_expected_max_matches_known_values():
    assert expected_max_z(1) == 0
    assert expected_max_z(2) == pytest.approx(0.5642, abs=1e-3)
    assert expected_max_z(35) == pytest.approx(2.107, abs=5e-3)


def test_probability_of_beating_a_score():
    assert prob_at_least_one_above(100, 100, 10, 1) == pytest.approx(0.5)
    assert prob_at_least_one_above(100, 100, 10, 2) == pytest.approx(0.75)
    assert prob_at_least_one_above(100, 100, 10, 0) == 0


def test_week_start_respects_reset_time(settings):
    from dataclasses import replace
    s = replace(settings, week_reset_weekday=0, week_reset_hour_utc=5)
    thursday = datetime(2026, 11, 12, 17, 0, tzinfo=timezone.utc)
    assert week_start(thursday, s) == datetime(2026, 11, 9, 5, 0, tzinfo=timezone.utc)
    monday_early = datetime(2026, 11, 9, 4, 0, tzinfo=timezone.utc)
    assert week_start(monday_early, s) == datetime(2026, 11, 2, 5, 0, tzinfo=timezone.utc)


def test_shares_add_up_to_projected_best(settings):
    now = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
    rows = []
    import random
    rng = random.Random(1)
    for i in range(20):
        t = now - timedelta(hours=i)
        rows.append((i + 1, _local(t), {"A": rng.randint(60_000, 90_000), "B": rng.randint(50_000, 70_000),
                                         "C": 70_000 + (i % 2) * 15_000}))
    r = build_report(_scores(rows), settings, now=now)
    assert sum(s.contribution for s in r.characters) == pytest.approx(r.projected_best, rel=1e-6)
    assert r.projected_best > r.mean_total  # spread raises the expected weekly best
    sprint = next(t for t in r.teams if t.distance == "Sprint")
    assert sprint.weakest.name == "B"
    assert r.week_matches == 20 and r.remaining == 15


def test_partial_matches_dont_count_for_weekly_best(settings):
    now = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
    rows = [
        (1, _local(now - timedelta(hours=2)), {"A": 10_000, "B": 20_000, "C": 30_000}),
        (2, _local(now - timedelta(hours=1)), {"A": 90_000, "B": 90_000}),  # partial
    ]
    r = build_report(_scores(rows), settings, now=now)
    assert r.week_best == 60_000
    assert r.week_matches == 2
    assert r.model_matches == 1 and r.rough


def test_last_week_best(settings):
    now = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
    rows = [
        (1, _local(now - timedelta(days=7)), {"A": 10_000, "B": 20_000, "C": 30_000}),
        (2, _local(now), {"A": 11_000, "B": 20_000, "C": 30_000}),
    ]
    r = build_report(_scores(rows), settings, now=now)
    assert (r.previous_week_best, r.week_best) == (60_000, 61_000)


def test_mixed_timestamp_formats(settings):
    rows = [(1, "2026-11-02 22:33", {"A": 1, "B": 2, "C": 3}),
            (2, "2026-11-12 14:00:21", {"A": 1, "B": 2, "C": 3})]
    r = build_report(_scores(rows), settings)
    assert len(r.matches) == 2


def test_text_report(settings):
    rows = [(1, "2026-11-12 14:00:21", {"A": 70_000, "B": 60_000, "C": 80_000})]
    text = format_report(_scores(rows), settings)
    assert "WEEKLY TOP SCORE REPORT" in text
    assert "Sprint" in text
    assert format_report(pd.DataFrame(), settings) == "No match data found."
