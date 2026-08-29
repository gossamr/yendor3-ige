"""Shared fixtures. The game files are the fixture: every test reads the real
REGISTER.EXE / WORLD.DAT, so a regression in the decoders shows up as a failed
assertion against ground truth rather than against a snapshot we wrote.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import pytest  # noqa: E402

import extract  # noqa: E402
import items as I  # noqa: E402
import sections as S  # noqa: E402

GAME = ROOT / "game"


@pytest.fixture(scope="session")
def directory():
    return S.load(GAME)


@pytest.fixture(scope="session")
def data(directory):
    return {
        "enemies": extract.extract_enemies(directory),
        "spells": extract.extract_spells(directory),
        "walkthrough": extract.extract_walkthrough(directory),
        "maps": extract.extract_maps(directory),
        "legend": extract.extract_legend(directory),
        "items": extract.extract_items(directory),
        "enhancers": I.Items(directory).enhancers(),
        "transports": I.Items(directory).transports(),
        "map_pages": extract.MAP_PAGES,
    }
