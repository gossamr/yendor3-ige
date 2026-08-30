"""The character roster, and grafting kept characters into it.

Established by watching the filesystem while a session was played (see
docs/saves.md): the roster is ten 500-byte slots, KEEP
CHARACTER writes them to CURGAME, and both a launch and NEW GAME rewrite the
whole of CURGAME from the template in WORLD.DAT. These tests hold the roster
geometry against the real game files, and the graft to changing nothing else.
"""
import pytest

import keep_characters as K

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
WORLD = (ROOT / "game" / "WORLD.DAT").read_bytes()


def test_the_roster_is_where_the_template_says_it_is():
    assert WORLD[K.ROSTER:K.ROSTER + 17] == b"PRE-CREATED PARTY"


def test_the_four_stock_characters_sit_on_the_500_byte_grid():
    found = dict(K.slots(WORLD, K.ROSTER))
    assert found[6] == "SQUIRE"
    assert found[7] == "DIANA"
    assert found[8] == "YENDOR"
    assert found[9] == "JOSEPHINE"


def test_the_created_slots_ship_empty():
    found = dict(K.slots(WORLD, K.ROSTER))
    assert [i for i in K.CREATED if i in found] == []


def make_roster(name: bytes, slot: int = 1) -> bytes:
    """A roster blob with one character in it, laid out like the game's."""
    roster = bytearray(WORLD[K.ROSTER:K.ROSTER + K.SLOTS * K.SLOT])
    rec = bytearray(K.SLOT)
    rec[:len(name)] = name
    roster[slot * K.SLOT:(slot + 1) * K.SLOT] = rec
    return bytes(roster)


def test_graft_writes_the_record_into_the_template():
    out, moved, _ = K.graft(WORLD, make_roster(b"ZORBAX\0"))
    assert moved == ["slot 1: ZORBAX"]
    assert dict(K.slots(out, K.ROSTER))[1] == "ZORBAX"


def test_graft_changes_only_that_slot():
    out, _, _ = K.graft(WORLD, make_roster(b"ZORBAX\0"))
    assert len(out) == len(WORLD)
    at = K.ROSTER + K.SLOT
    differing = {i for i in range(len(WORLD)) if WORLD[i] != out[i]}
    assert differing and all(at <= i < at + K.SLOT for i in differing)


def test_graft_leaves_the_header_and_the_stock_four_alone():
    # A source whose every slot is filled must still only move slots 1-5:
    # slot 0 is a header and 6-9 are the characters the game ships.
    roster = bytearray(K.SLOTS * K.SLOT)
    for i in range(K.SLOTS):
        roster[i * K.SLOT:i * K.SLOT + 7] = b"INTRUDE"
    out, moved, _ = K.graft(WORLD, bytes(roster))

    assert len(moved) == len(K.CREATED)
    found = dict(K.slots(out, K.ROSTER))
    assert found[0] == "PRE-CREATED PARTY"
    assert [found[i] for i in (6, 7, 8, 9)] == ["SQUIRE", "DIANA", "YENDOR", "JOSEPHINE"]


def test_grafting_twice_accumulates_rather_than_replaces():
    first, _, _ = K.graft(WORLD, make_roster(b"ZORBAX\0", slot=1))
    second, moved, _ = K.graft(first, make_roster(b"MIRABEL\0", slot=2))

    assert moved == ["slot 2: MIRABEL"]
    found = dict(K.slots(second, K.ROSTER))
    assert found[1] == "ZORBAX" and found[2] == "MIRABEL"


def test_an_empty_source_slot_clears_nothing():
    grafted, _, _ = K.graft(WORLD, make_roster(b"ZORBAX\0"))
    again, moved, _ = K.graft(grafted, bytes(K.SLOTS * K.SLOT))

    assert moved == []
    assert again == grafted


def test_read_roster_rejects_a_file_that_is_not_a_saved_game(tmp_path):
    bad = tmp_path / "CURGAME"
    bad.write_bytes(b"\0" * 100)
    with pytest.raises(SystemExit):
        K.read_roster(bad)


def test_read_roster_takes_the_first_five_thousand_bytes(tmp_path):
    blob = bytearray(K.SAVE_SIZE)
    blob[:K.SLOTS * K.SLOT] = make_roster(b"ZORBAX\0")
    f = tmp_path / "CURGAME"
    f.write_bytes(bytes(blob))

    assert dict(K.slots(K.read_roster(f)))[1] == "ZORBAX"
