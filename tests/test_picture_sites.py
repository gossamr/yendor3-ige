"""The draw sites, against what the other decoders already name."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import picture_sites as PS  # noqa: E402
import pictures as P  # noqa: E402
from disasm import Exe  # noqa: E402

GAME = ROOT / "game"
pytestmark = pytest.mark.skipif(not (GAME / "REGISTER.EXE").exists(),
                                reason="needs a copy of the game in game/")


@pytest.fixture(scope="module")
def exe():
    return Exe(GAME / "REGISTER.EXE")


def test_every_site_names_a_run_the_file_holds(exe):
    found = PS.sites(exe)
    assert set(found) <= set(range(10)), sorted(found)
    assert len(found) == 10, "every run is drawn somewhere"


def test_every_literal_is_inside_its_own_run(exe):
    """A picture named at a call site has to exist in the run selected there."""
    pics = (GAME / "PICTURES.VGA").read_bytes()
    runs = P.read_runs((GAME / "REGISTER.EXE").read_bytes(), len(pics))
    for run, numbers in PS.literals(exe).items():
        for n in numbers:
            assert 0 <= n < runs[run].count, f"run {run} has no picture {n}"


def test_the_three_struck_monster_effects_are_not_literals(exe):
    """They come from `DS:0x5480` and up, so run 6 has sites with no number."""
    found = PS.sites(exe)
    assert any(s["picture"] is None for s in found[6])


def test_the_item_icon_loader_names_no_picture(exe):
    """Image `0x13410` selects run 8 for whatever the caller asked for."""
    at = [s for s in PS.sites(exe)[8] if s["at"] == 0x13410]
    assert at and at[0]["picture"] is None

def test_pairing_drops_a_picture_its_run_does_not_hold(exe):
    """Pairing across a routine boundary is what the range check catches: run 0
    holds 23 pictures and a fixed window pairs one literal of 29 with it."""
    pics = (GAME / "PICTURES.VGA").read_bytes()
    runs = P.read_runs((GAME / "REGISTER.EXE").read_bytes(), len(pics))
    for run, numbers in PS.paired(exe, runs).items():
        for n in numbers:
            assert 0 <= n < runs[run].count, (run, n)


def test_pairing_corrects_the_window_where_a_selection_intervenes(exe):
    """The forward window reads past a second selection and misattributes.

    Image `0x11C1B` selects run 6, image `0x11C3F` selects run 9 twenty bytes
    later, and the literal 7 at `0x11C45` belongs to the second. The window
    hands it to run 6 because it is inside 64 bytes of that one; pairing hands
    it to run 9 because that is the nearest selection before it."""
    pics = (GAME / "PICTURES.VGA").read_bytes()
    runs = P.read_runs((GAME / "REGISTER.EXE").read_bytes(), len(pics))
    wide = PS.paired(exe, runs)
    assert 7 in wide[9]
    assert 7 not in wide[6]
    assert 7 in PS.literals(exe)[6], "the window still gets it wrong"
