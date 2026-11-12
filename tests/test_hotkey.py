import pytest

pytest.importorskip("PySide6")

from score_tracker.gui.app import parse_hotkey  # noqa: E402


@pytest.mark.parametrize("text, expected", [
    ("ctrl+alt+s", (0x2 | 0x1, ord("S"))),
    ("F9", (0, 0x78)),
    ("shift+win+1", (0x4 | 0x8, ord("1"))),
    ("ctrl+pause", (0x2, 0x13)),
])
def test_valid(text, expected):
    assert parse_hotkey(text) == expected


@pytest.mark.parametrize("text", ["", "ctrl+", "hyper+s", "ctrl+alt+enterr"])
def test_invalid(text):
    assert parse_hotkey(text) is None
