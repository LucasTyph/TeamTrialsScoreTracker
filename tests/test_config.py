import pytest

from score_tracker.config import SettingsError, load_settings


def test_creates_template_seeded_from_legacy_csv(tmp_path):
    (tmp_path / "dataset.csv").write_text("timestamp,Gold Ship,King Halo\n")
    settings = load_settings(tmp_path)
    assert settings.roster == ("Gold Ship", "King Halo")
    assert (tmp_path / "settings.toml").exists()
    assert settings.adjusted_score_k == 0.5


def test_empty_template_without_legacy_data(tmp_path):
    assert load_settings(tmp_path).roster == ()


def test_overrides(tmp_path):
    (tmp_path / "settings.toml").write_text(
        'roster = ["A", "B"]\nadjusted_score_k = 1\nrow_tolerance = 25\n'
        r"tesseract_cmd = 'D:\Tools\tesseract.exe'"
    )
    s = load_settings(tmp_path)
    assert s.roster == ("A", "B")
    assert s.adjusted_score_k == 1.0
    assert s.row_tolerance == 25
    assert s.tesseract_cmd == r"D:\Tools\tesseract.exe"
    assert s.scores_path == tmp_path / "scores.csv"


@pytest.mark.parametrize(
    "content, message",
    [
        ('roster = ["A", "A"]', "duplicate"),
        ('roster = ["A"]\nrow_tolerence = 3', "unknown"),
        ('roster = ["A"]\nrow_tolerance = "x"', "must be of type int"),
        ("roster = [", "settings.toml"),
    ],
)
def test_invalid_settings(tmp_path, content, message):
    (tmp_path / "settings.toml").write_text(content)
    with pytest.raises(SettingsError, match=message):
        load_settings(tmp_path)
