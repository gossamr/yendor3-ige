"""Shared fixtures. The game files are the fixture: every test reads the real
REGISTER.EXE / WORLD.DAT, so a regression in the decoders shows up as a failed
assertion against ground truth rather than against a snapshot we wrote.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import pytest  # noqa: E402

import sections as S  # noqa: E402

GAME = ROOT / "game"


@pytest.fixture(scope="session")
def directory():
    return S.load(GAME)
