"""Reading the game's own screens.

These tests close the loop: the decoder's output is checked against numbers
lifted from frames the game itself drew, rather than against anything we wrote
down. The three fixture frames were captured from the running game and their
values confirmed by hand.
"""
from pathlib import Path

import pytest

import ocr
import read_stats
from labels import EFFECTS

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "tmp" / "monsters"


def frame(name: str) -> Path:
    """The frame for one bootstrap monster, or a skip if there is none.

    The frames are the game's own screens and do not ship. Without them a
    capture run into tmp/monsters is the only source.
    """
    shot = next(s for s, n in ocr.FIXTURE_NAMES.items() if n == name)
    try:
        return ocr.bootstrap_frame(shot, SHOTS)
    except FileNotFoundError as e:
        pytest.skip(str(e))


def test_alphabet_covers_every_digit():
    alpha = ocr.standard_alphabet(frame("acoknight").parent)
    assert set(alpha.by_bits.values()) == set("0123456789,")


def test_reads_the_values_the_game_displays():
    alpha = ocr.standard_alphabet(frame("blazios").parent)
    blazios = ocr.read_screen(ocr.Frame(frame("blazios")), alpha)
    assert blazios["health"] == 2900
    assert blazios["damage"] == 390
    assert blazios["experience"] == 500_000
    assert blazios["gold"] == 3_000_000
    assert blazios["food"] == 8
    assert blazios["nuore"] == 100
    # Melee-only monster: the ranged rows are blank, not zero.
    assert blazios["ranged_accuracy"] is None


def test_screen_values_match_the_decoded_record(data):
    """The real check: what the game prints equals what we decode."""
    alpha = ocr.standard_alphabet(frame("acoknight").parent)
    by = {e["name"]: e for e in data["enemies"]}
    for fixture, name in (("acoknight", "ACOKNIGHT"),
                          ("alligator", "ALLIGATOR"),
                          ("blazios", "BLAZIOS")):
        seen = ocr.read_screen(ocr.Frame(frame(fixture)), alpha)
        rec = by[name]
        for field in ("health", "accuracy", "dexterity", "absorption", "damage",
                      "experience", "gold", "nuore"):
            assert (seen[field] or 0) == rec[field], f"{name}.{field}"
        assert (seen["food"] or 0) == rec["food"], f"{name}.food"


def test_effect_rows_match_the_decoded_masks(data):
    by = {e["name"]: e for e in data["enemies"]}
    for fixture, name in (("acoknight", "ACOKNIGHT"),
                          ("alligator", "ALLIGATOR"),
                          ("blazios", "BLAZIOS")):
        seen = read_stats.read_effects(frame(fixture))
        rec = by[name]
        for effect, value in zip(EFFECTS, seen):
            if effect == "MAGIC DAMAGE":
                assert (value == read_stats.RESISTANT) == rec["resist_magic"], name
            elif effect == "PHYSICAL DAMAGE":
                assert (value == read_stats.RESISTANT) == bool(rec["resist_physical"]), name
            else:
                assert (value == read_stats.IMMUNE) == (effect in rec["immune"]), \
                    f"{name}: {effect}"


def test_acoknight_is_the_undead_style_immunity_set():
    seen = read_stats.read_effects(frame("acoknight"))
    immune = [e for e, v in zip(EFFECTS, seen) if v == read_stats.IMMUNE]
    assert immune == ["POISON", "DISEASE", "PARALYSIS",
                      "FREEZING", "HEXING", "CURSING"]


def test_every_effect_row_of_every_monster_matches(directory):
    """The three fixtures above cover 36 rows; a capture run covers all 852.

    Skipped where there is no capture, the way the artwork check is, since the
    frames live in tmp/ and are not kept.
    """
    import re

    import verify_effects as V

    shots = sorted(p for p in SHOTS.glob("m*.png")
                   if re.fullmatch(r"m\d+\.png", p.name))
    if not shots:
        pytest.skip(f"no monster captures in {SHOTS.relative_to(ROOT)}; "
                    "run tools/capture_monsters.js")

    listed = V.monsters(directory)
    assert len(shots) >= len(listed)
    wrong, rows, filled = [], 0, set()
    for monster, shot in zip(listed, shots):
        seen = read_stats.read_effects(shot)
        want = V.expected(monster["immunity"], monster["resistance"])
        for effect, got, expect in zip(EFFECTS, seen, want):
            rows += 1
            if got != read_stats.NONE:
                filled.add(effect)
            if got != expect:
                wrong.append((monster["name"], effect, got, expect))
    assert wrong == []
    assert rows == len(EFFECTS) * len(listed)
    # Not vacuous: each of the twelve rows carries a word on some monster.
    assert filled == set(EFFECTS)
