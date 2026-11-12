from pathlib import Path

import pytest

from score_tracker.config import Settings, SettingsError, load_settings, save_settings


def test_creates_template_seeded_from_legacy_csv(tmp_path):
    (tmp_path / "dataset.csv").write_text("timestamp,Gold Ship,King Halo\n")
    settings = load_settings(tmp_path)
    assert settings.roster == ("Gold Ship", "King Halo")
    assert settings.teams == {}
    assert (tmp_path / "settings.toml").exists()


def test_empty_template_without_legacy_data(tmp_path):
    assert load_settings(tmp_path).roster == ()


def test_overrides(tmp_path):
    (tmp_path / "settings.toml").write_text(
        'roster = ["A", "B"]\npending_timeout_minutes = 5\nrow_tolerance = 25\n'
        r"tesseract_cmd = 'D:\Tools\tesseract.exe'" "\n"
    )
    s = load_settings(tmp_path)
    assert s.roster == ("A", "B")
    assert s.pending_timeout_minutes == 5.0
    assert s.row_tolerance == 25
    assert s.tesseract_cmd == r"D:\Tools\tesseract.exe"
    assert s.scores_path == tmp_path / "scores.csv"


def test_teams(tmp_path):
    (tmp_path / "settings.toml").write_text(
        'roster = ["Old"]\n[teams]\nSprint = ["A", "B"]\nDirt = ["C"]\n'
    )
    s = load_settings(tmp_path)
    assert s.roster == ("A", "B", "C", "Old")
    assert s.teams == {"A": "Sprint", "B": "Sprint", "C": "Dirt"}
    assert s.team_members("Sprint") == ["A", "B"]


def test_retired_settings_are_ignored(tmp_path):
    (tmp_path / "settings.toml").write_text('roster = ["A"]\nadjusted_score_k = 0.5\ncrop_above_bar = 55\n')
    assert load_settings(tmp_path).roster == ("A",)


def test_save_round_trip(tmp_path):
    teams = {"Air Groove": "Sprint", "Oguri Cap": "Dirt"}
    s = Settings(roster=("Air Groove", "Oguri Cap", "Old Friend"), teams=teams, data_dir=tmp_path,
                 capture_hotkey="f9", tesseract_cmd=r"E:\ocr\tesseract.exe")
    save_settings(s)
    loaded = load_settings(tmp_path)
    assert loaded == s


@pytest.mark.parametrize(
    "content, message",
    [
        ('roster = ["A", "A"]', "duplicate"),
        ('roster = ["A"]\n[teams]\nSprint = ["A"]', "duplicate"),
        ('roster = ["A"]\nrow_tolerence = 3', "unknown"),
        ('roster = ["A"]\nrow_tolerance = "x"', "must be of type int"),
        ('[teams]\nTurf = ["A"]', "unknown team"),
        ("roster = [", "settings.toml"),
    ],
)
def test_invalid_settings(tmp_path, content, message):
    (tmp_path / "settings.toml").write_text(content)
    with pytest.raises(SettingsError, match=message):
        load_settings(tmp_path)


def test_settings_path_default_is_project_data():
    assert Settings().data_dir.name in ("data", "TeamTrialsScoreTracker") or Path(Settings().data_dir).is_absolute()
