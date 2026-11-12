from score_tracker.parser import _part_matches, find_score, parse_scores, parse_single_match

from conftest import DATASET_ROSTER, make_ocr, row

ROSTER = DATASET_ROSTER


def parse(words, roster=ROSTER, claimed=None):
    return parse_single_match(make_ocr(words), roster, 20, 0.6, claimed)


def test_name_and_score():
    assert parse(row("Curren", "Chan", "60,016", "pts")) == {"Curren Chan": 60016}


def test_name_without_space_matches():
    assert parse(row("GoldShip", "50,116", "pts")) == {"Gold Ship": 50116}


def test_crop_with_only_numbers_does_not_crash():
    assert parse(row("50,116", "4")) == {}


def test_single_letter_part_needs_exact_word():
    words = row("Sakura", "Chiyono", "O", "52,798", "pts")
    assert parse(words) == {"Sakura Chiyono O": 52798}


def test_short_part_does_not_match_inside_longer_word():
    assert not _part_matches("o", "oguri")
    assert _part_matches("o", "o")
    # Only 'Sakura' (1/3 parts) matches Sakura Bakushin O; 'Oguri' is 1/2 of Oguri Cap.
    assert parse(row("Sakura", "Oguri", "41,076")) == {}


def test_claimed_names_are_skipped():
    assert parse(row("Curren", "Chan", "60,016"), claimed={"Curren Chan"}) == {}


def test_score_split_into_fragments_is_merged():
    assert parse(row("Oguri", "Cap", "52", "426")) == {"Oguri Cap": 52426}


def test_out_of_range_numbers_are_ignored():
    assert parse(row("Curren", "Chan", "999", "pts")) == {}


def test_find_score_without_name():
    assert find_score(make_ocr(row("50,116", "pts", "G)")), 20) == 50116
    assert find_score(make_ocr(row("pts")), 20) is None


def test_parse_scores_full_image():
    words = row("Curren", "Chan", "60,016", y=10) + row("King", "Halo", "41,778", y=80)
    assert parse_scores(make_ocr(words), ROSTER, 20, 0.6) == {
        "Curren Chan": 60016,
        "King Halo": 41778,
    }
