"""The party's own inventory, and what using an item does.

Three readings meet here. The roster header's own six inventory slots, which
the item search walks before it walks anyone's pack. The thirteen quest flag words a
gated door and a traveling item both point at. And the properties bit that
makes an item a way home, which is how the athaneum key and the ankh of
portals were read at all: neither item id is compared anywhere in the load
image, so nothing named for either one exists to find.

The saves under `tmp/saves/mine` are one player's six slots. Where they are
absent the tests that need them are skipped, and the rest still run.
"""
import struct
from pathlib import Path

import pytest

import items as I
import links as L
import sections as S

ROOT = Path(__file__).resolve().parent.parent
PLAYED = sorted((ROOT / "tmp" / "saves" / "mine").glob("SAVGAME?"))

# Roster header offsets, as docs/saves.md records them.
SLOTS_AT, SLOTS, SLOT_BYTES = 282, 6, 4
FLAGS_AT, FLAG_WORDS = 212, 13
ROSTER_SLOT = 500

GATES = 0xC45B
GATE_RECORD = 22
GATE_END = 0xFFFF
# DS:0xCEDD is the roster, so the flag words the gate table points at are the
# header's own thirteen.
ROSTER = 0xCEDD


def test_only_two_items_travel(directory):
    """The bit is the whole reading, so its rarity is what makes it one: two
    items in 631 carry it, and they are the two the question was about."""
    it = I.Items(directory)
    travel = {n: it.travels_to(rec)
              for n, rec in enumerate(it.records, start=1)
              if it.travels_to(rec)}
    assert travel == {33: 2, 84: 3}
    assert it.names[32] == "ATHANEUM KEY"
    assert it.names[83] == "ANKH OF PORTALS"


def test_where_each_traveling_item_lands(directory):
    """The number is 1-based into the destination table, and what it names is
    what the game's own walkthrough says: back to Flagell in the Athaneum, and
    the Room of Portals on Thaine Map 10."""
    dest = L.destinations(directory.exe)
    assert len(dest) == L.DESTINATION_COUNT
    key, ankh = dest[2 - 1], dest[3 - 1]
    assert (key["x"], key["y"], key["facing"]) == (460, 46, "north")
    assert (ankh["x"], ankh["y"], ankh["facing"]) == (365, 76, "west")
    # The Athaneum's cell is where a new game starts, which the template says.
    template = directory.world[directory.sections[32].offset:][:ROSTER_SLOT]
    assert struct.unpack_from("<HH", template, 152) == (key["x"], key["y"])


def gates(directory) -> list[tuple[int, ...]]:
    at = L.DGROUP + GATES
    out = []
    while True:
        r = struct.unpack_from("<11H", directory.exe, at)
        if r[0] == GATE_END:
            return out
        out.append(r)
        at += GATE_RECORD


def test_the_gate_table_is_35_records_and_gates_neither_travel(directory):
    rows = gates(directory)
    assert len(rows) == 35
    assert {r[0] for r in rows}.isdisjoint({2, 3})


def test_a_gate_points_at_a_quest_flag_word_in_the_roster_header(directory):
    """Every flag word the table names falls inside the thirteen at header 212,
    and every bit is a single bit."""
    for r in gates(directory):
        offset = r[1] - ROSTER
        assert FLAGS_AT <= offset < FLAGS_AT + FLAG_WORDS * 2
        assert offset % 2 == 0
        assert bin(r[2]).count("1") == 1


def test_a_gate_asks_a_password_or_an_item_but_not_both(directory):
    rows = gates(directory)
    passworded = [r for r in rows if r[3]]
    with_item = [r for r in rows if r[4]]
    assert len(passworded) == 13
    assert all(r[3] == 26 for r in passworded)
    assert [(r[0], r[4]) for r in with_item] == [(58, 374)]
    assert not [r for r in rows if r[3] and r[4]]


def test_the_template_starts_with_every_slot_empty_and_every_flag_clear(directory):
    template = directory.world[directory.sections[32].offset:][:ROSTER_SLOT]
    assert set(template[SLOTS_AT:SLOTS_AT + SLOTS * SLOT_BYTES]) == {0}
    assert set(template[FLAGS_AT:FLAGS_AT + FLAG_WORDS * 2]) == {0}


@pytest.mark.skipif(not PLAYED, reason="no played saves under tmp/saves/mine")
def test_a_played_save_fills_the_six_slots_with_real_items(directory):
    """The shape is what a save shows, not the contents.

    Nothing binds a slot to an item: the six are a store, and what a player
    keeps in them is a habit. What the assertion can carry is that a filled
    slot names an item the table has, that the slots fill as a game is
    played, and that a second word rides beside the id.
    """
    names = {n: name for n, name in enumerate(I.Items(directory).names, start=1)}
    filled = []
    for path in PLAYED:
        words = struct.unpack_from("<%dH" % (SLOTS * 2), path.read_bytes(), SLOTS_AT)
        here = [(words[i * 2], words[i * 2 + 1]) for i in range(SLOTS)]
        for item, _state in here:
            assert item in names or item == 0
        filled.append(sum(1 for item, _ in here if item))
    assert max(filled) > min(filled)
    assert max(filled) <= SLOTS


@pytest.mark.skipif(len(PLAYED) < 2, reason="no played saves under tmp/saves/mine")
def test_the_quest_flags_fill_as_a_game_is_played():
    counts = []
    for path in PLAYED:
        words = struct.unpack_from("<%dH" % FLAG_WORDS, path.read_bytes(), FLAGS_AT)
        counts.append(sum(bin(w).count("1") for w in words))
    assert max(counts) > min(counts)
    assert min(counts) > 0
