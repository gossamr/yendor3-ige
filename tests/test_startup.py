"""The logo, the exit screen and the abort messages, against the bytes."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import sections as S  # noqa: E402
import startup as ST  # noqa: E402

GAME = ROOT / "game"
pytestmark = pytest.mark.skipif(not (GAME / "WORLD.DAT").exists(),
                                reason="needs a copy of the game in game/")


@pytest.fixture(scope="module")
def directory():
    return S.load(GAME)


def test_the_logo_is_a_640_by_480_pcx(directory):
    picture = ST.logo(directory.world, directory)
    assert (picture["width"], picture["height"]) == (640, 480)
    assert picture["stride"] == 640
    assert len(picture["pixels"]) == 640 * 480
    assert len(picture["palette"]) == 256


def test_the_logo_is_the_shipped_LOGO_PCX(directory):
    """Section 33 and `LOGO.PCX` are the same bytes, where the file is here."""
    beside = GAME / "LOGO.PCX"
    if not beside.exists():
        pytest.skip("LOGO.PCX is not in game/")
    assert directory.sections[ST.LOGO].slice(directory.world) == beside.read_bytes()


def test_the_exit_screen_is_eighty_by_eleven(directory):
    rows = ST.exit_screen(directory.world, directory)
    assert len(rows) == 11
    assert all(len(r["text"]) == 80 for r in rows)
    assert "Thank you for playing The Tyrants of Thaine" in rows[1]["text"]
    assert "Copyright (C) 1997 SW Games" in rows[9]["text"]


def test_the_exit_screen_is_boxed(directory):
    """The first and last rows are the border, and every row ends in one."""
    rows = ST.exit_screen(directory.world, directory)
    assert set(rows[0]["text"]) == {"█", "▀"}
    assert set(rows[-1]["text"]) == {"█", "▄"}
    assert all(r["text"][0] == "█" and r["text"][-1] == "█" for r in rows)


def test_the_twenty_abort_messages(directory):
    messages = ST.abort_messages(directory.exe)
    assert len(messages) == ST.ABORT_CODES
    assert messages[9] == "Problem with WORLD.DAT."
    assert messages[18] == "Please run Tyrants of Thaine from SW.BAT"
    # Code 2 names a file the game does not ship; the message is the typo.
    assert messages[2] == "Problem with PICTURE.VGA."
    # Nineteen carry text and the twentieth is a bare full stop.
    assert messages[19] == "."
    assert all(m for m in messages)
