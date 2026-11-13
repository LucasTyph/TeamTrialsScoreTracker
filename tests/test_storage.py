import pandas as pd

from score_tracker.storage import append_match, last_match, load_scores, migrate_legacy, to_wide

WIDE_CSV = """timestamp,Alpha,Beta,Gamma
2026-01-01 10:00,10000,20000.0,30000
2026-01-02 10:00,11000,,31000
"""


def test_append_and_load(settings):
    assert load_scores(settings).empty
    id1, _ = append_match({"Alpha": 10000, "Beta": 20000}, settings)
    id2, _ = append_match({"Alpha": 12000, "Beta": None}, settings)
    df = load_scores(settings)
    assert (id1, id2) == (1, 2)
    assert len(df) == 3  # None scores are not stored
    assert last_match(df).set_index("character")["score"].to_dict() == {"Alpha": 12000}


def test_migrates_wide_csv_and_keeps_backup(settings):
    settings.legacy_csv_path.write_text(WIDE_CSV)
    assert migrate_legacy(settings) == 2
    assert not settings.legacy_csv_path.exists()
    assert (settings.data_dir / "dataset.wide-backup.csv").exists()

    df = load_scores(settings)
    assert len(df) == 5  # the blank Beta score is dropped
    assert df["score"].dtype == "int64"
    assert df[(df.match_id == 1) & (df.character == "Beta")]["score"].item() == 20000
    # Running again is a no-op
    assert migrate_legacy(settings) == 0


def test_roster_change_does_not_corrupt_data(settings):
    settings.legacy_csv_path.write_text(WIDE_CSV)
    append_match({"Gamma": 32000, "Delta": 40000, "Omega": 50000}, settings)

    df = load_scores(settings)
    assert set(df.columns) == {"match_id", "timestamp", "character", "score", "distance", "lineup"}
    wide = to_wide(df, ["Gamma", "Delta", "Omega"])
    assert list(wide.columns) == ["timestamp", "Gamma", "Delta", "Omega"]
    assert wide.loc[3].drop("timestamp").tolist() == [32000, 40000, 50000]
    # Old matches keep their Gamma scores; new characters are simply absent there
    assert wide["Gamma"].tolist() == [30000, 31000, 32000]
    assert wide.loc[1, ["Delta", "Omega"]].isna().all()


def test_to_wide_drops_matches_without_roster_characters(settings):
    append_match({"Alpha": 10000}, settings)
    append_match({"Beta": 20000}, settings)
    wide = to_wide(load_scores(settings), ["Beta"])
    assert wide.index.tolist() == [2]
    assert isinstance(wide, pd.DataFrame)


def test_distances_are_saved_with_roster_fallback(settings):
    from dataclasses import replace
    s = replace(settings, teams={"Alpha": "Sprint", "Beta": "Mile"})
    append_match({"Alpha": 10000, "Beta": 20000}, s, distances={"Beta": "Dirt"})
    df = load_scores(s).set_index("character")
    assert df.loc["Alpha", "distance"] == "Sprint"  # from the roster
    assert df.loc["Beta", "distance"] == "Dirt"  # as read from the screenshot


def test_old_files_get_a_distance_column(settings):
    from dataclasses import replace
    settings.scores_path.write_text("match_id,timestamp,character,score\n1,2026-01-01 10:00,Alpha,10000\n")
    s = replace(settings, teams={"Alpha": "Long"})
    assert load_scores(s).loc[0, "distance"] == "Long"


def test_delete_match(settings):
    from score_tracker.storage import delete_match
    append_match({"Alpha": 1}, settings)
    append_match({"Alpha": 2}, settings)
    assert delete_match(1, settings) == 1
    assert load_scores(settings)["match_id"].tolist() == [2]


def test_legacy_header_with_newer_rows_appended(settings):
    """A 4-column file that later got 5-column rows appended still loads."""
    from dataclasses import replace
    s = replace(settings, teams={"Alpha": "Sprint"})
    s.scores_path.write_text(
        "match_id,timestamp,character,score\n"
        "1,2026-01-01 10:00,Alpha,10000\n"
        "2,2026-01-02 10:00,Alpha,11000,Mile\n"
    )
    df = load_scores(s)
    assert df["distance"].tolist() == ["Sprint", "Mile"]
    assert s.scores_path.read_text().splitlines()[0] == "match_id,timestamp,character,score,distance,lineup"
    append_match({"Alpha": 12000}, s)
    assert len(load_scores(s)) == 3


def test_lineup_column_added_to_old_files(settings):
    settings.scores_path.write_text("match_id,timestamp,character,score,distance\n"
                                    "1,2026-01-01 10:00,Alpha,10000,Mile\n")
    df = load_scores(settings)
    assert df["lineup"].tolist() == [""]
    assert settings.scores_path.read_text().splitlines()[0].endswith(",lineup")
    append_match({"Alpha": 11000}, settings, lineup="l2")
    assert load_scores(settings)["lineup"].tolist() == ["", "l2"]


def test_move_match(settings):
    from score_tracker.storage import move_match
    append_match({"Alpha": 1, "Beta": 2}, settings, lineup="l1")
    append_match({"Alpha": 3}, settings, lineup="l1")
    assert move_match(1, "l2", settings) == 2
    df = load_scores(settings)
    assert df.groupby("match_id")["lineup"].first().to_dict() == {1: "l2", 2: "l1"}
