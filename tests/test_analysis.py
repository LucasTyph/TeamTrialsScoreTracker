from score_tracker.analysis import format_report
from score_tracker.storage import append_match, load_scores

ROSTER = ["Alpha", "Beta", "Gamma"]


def test_team_totals_ignore_partial_matches(settings):
    append_match({"Alpha": 10000, "Beta": 20000, "Gamma": 30000}, settings)
    append_match({"Alpha": 12000, "Beta": 22000, "Gamma": 32000}, settings)
    append_match({"Alpha": 50000}, settings)  # partial

    report = format_report(load_scores(settings), ROSTER)
    assert "3 matches, 2 complete" in report
    assert "Team avg total: 63,000" in report
    assert "Worst: 60,000" in report


def test_report_with_no_complete_matches(settings):
    append_match({"Alpha": 10000, "Beta": 20000}, settings)
    append_match({"Alpha": 11000, "Gamma": 30000}, settings)
    report = format_report(load_scores(settings), ROSTER)
    assert "no complete matches yet" in report


def test_report_for_roster_without_data(settings):
    append_match({"Alpha": 10000}, settings)
    assert "No match data" in format_report(load_scores(settings), ["Zeta"])
