"""The save file's layout, against the executable that defines it.

`tools/saves.py` reads the section offsets out of `REGISTER.EXE` rather than
restating them, so these tests hold the two ends together: that the table is
where it is thought to be and says what it is thought to say, and that the
record lengths written down beside each section are the ones the game's own
stubs write into the file handle.

The rest is checked against `WORLD.DAT`'s roster template, which is the header
and ten slots a new game starts from, so a save's fields can be tested
without a save file.
"""
from __future__ import annotations

import struct
from pathlib import Path

import pytest

import saves as S
from registry import map_registry
from mz import HEADER, Image

ROOT = Path(__file__).resolve().parent.parent
WORLD = (ROOT / "game" / "WORLD.DAT").read_bytes()
ROSTER = 0x41D72F      # "PRE-CREATED PARTY", the template CURGAME is built from


@pytest.fixture(scope="module")
def exe():
    return Image(ROOT / "game" / "REGISTER.EXE")


# --- where the layout comes from -------------------------------------------

def test_the_data_segment_is_where_the_filenames_say(exe):
    assert S.dgroup(exe) == S.DGROUP


def test_the_four_filenames_sit_in_their_handles(exe):
    at = HEADER + S.dgroup(exe)
    for handle, name in ((0x967A, b"CURGAME"), (0x9690, b"PICTURES.VGA"),
                         (0x96AB, b"SAVGAMEX"), (0x96C2, b"WORLD.DAT")):
        start = at + handle
        assert struct.unpack_from("<H", exe.data, start)[0] == 0xFFFF
        assert exe.data[start + 14:start + 14 + len(name)] == name


def test_the_section_table_is_seven_offsets_and_a_terminator(exe):
    got = [s.base for s in S.sections(exe)]
    assert got == [0, 5000, 21800, 65864, 66923, 67931, 68557]
    at = HEADER + S.dgroup(exe) + S.FILE_TABLE + 4 * S.SECTION_COUNT
    assert struct.unpack_from("<I", exe.data, at)[0] == 0


def test_curgames_table_ends_where_world_dats_begins(exe):
    """The two directories abut, which is what lets one address the other."""
    from sections import MASTER_TABLE
    assert S.table_at() + 4 * (S.SECTION_COUNT + 1) == MASTER_TABLE
    first = struct.unpack_from("<I", exe.data, MASTER_TABLE)[0]
    assert first == 0x83400


def test_each_record_length_is_the_one_its_stub_writes(exe):
    for section in S.sections(exe):
        got = S.stub_record_length(exe, section.index)
        if section.index == 1:
            # Section 1's stub takes its length from DS:0x5492 instead of an
            # immediate, so there is nothing to read back.
            assert got is None
        else:
            assert got == section.record, f"section {section.index}"


def test_the_file_ends_where_the_last_section_does(exe):
    assert S.sections(exe)[-1].end == S.SAVE_SIZE


# --- the geometry each section implies --------------------------------------

def test_the_seen_grid_is_the_whole_world_one_bit_a_cell(exe):
    grid = S.sections(exe)[1]
    assert grid.record == S.BAND_BYTES
    assert grid.records == S.AREAS * S.BANDS
    assert grid.size * 8 == S.AREAS * S.BANDS * S.LEVELS * S.CELLS


def test_the_last_section_is_the_eighty_creature_structs(exe):
    creatures = S.sections(exe)[6]
    assert creatures.records == 1
    assert creatures.size == S.SPAWN_SLOTS * S.CREATURE


def test_the_container_section_divides_into_whole_records(exe):
    containers = S.sections(exe)[2]
    assert containers.size % containers.record == 0
    assert containers.records == 1296


def test_the_seek_puts_a_row_where_the_writes_were_seen(exe):
    # Watching the game play, the row the party stood on was written back at
    # file offset 9,500: section 1, record 45.
    assert S.offset(S.sections(exe)[1], 45) == 9500


# --- the template, read as a save -------------------------------------------

def template() -> S.Save:
    """A save whose roster is the template a new game starts from.

    Everything past the roster is zero, which is what a fresh CURGAME holds
    anyway, since nothing has happened in it yet.
    """
    blob = bytearray(S.SAVE_SIZE)
    blob[:S.ROSTER_SLOTS * S.ROSTER_SLOT] = WORLD[ROSTER:ROSTER + S.ROSTER_SLOTS * S.ROSTER_SLOT]
    return S.Save(bytes(blob))


def test_the_template_names_itself():
    assert template().title == "PRE-CREATED PARTY"


def test_the_stock_four_are_the_starting_party():
    save = template()
    assert save.party == [6, 7, 8, 9]
    assert dict(save.roster())[6] == "SQUIRE"


def test_an_empty_place_in_the_party_reads_as_no_slot():
    """Assembling SQUIRE and JOSEPHINE alone writes 6, 9, 0, 0."""
    blob = bytearray(template().blob)
    struct.pack_into("<4H", blob, S.PARTY_AT, 6, 9, 0, 0)
    assert S.Save(bytes(blob)).party == [6, 9]


def test_a_new_game_starts_in_the_athaneum_facing_north():
    where = template().where
    assert (where["x"], where["y"]) == (460, 46)
    assert (where["area"], where["level"]) == (1, 11)
    assert where["facing"] == "north"
    assert where["clock"] == 540 and where["time"] == "09:00"


def test_the_starting_area_and_level_are_the_athaneum():
    """The position decodes to the map the registry names independently.

    Read straight out of `WORLD.DAT 0x83400` rather than from a built file, so
    the check holds in a tree that has not run `make data`.
    """
    where = template().where
    assert map_registry(WORLD)[(where["area"], where["level"])] == "ATHANEUM"


def test_the_stock_party_carries_two_containers():
    save = template()
    packs = []
    for slot, _ in save.roster():
        if slot == 0:
            continue
        rec = save.blob[slot * S.ROSTER_SLOT:(slot + 1) * S.ROSTER_SLOT]
        item, number = struct.unpack_from("<HH", rec, 318)
        if item:
            packs.append((slot, item, number))
    assert packs == [(6, 28, 1), (9, 28, 2)]


def test_a_fresh_file_has_nothing_recorded_in_it():
    save = template()
    assert save.seen_cells() == []
    assert save.creatures() == []
    assert all(save.bits_set(i) == [] for i in (3, 4, 5))
    assert all(save.container(n) == [] for n in range(save.sections[2].records))


def test_a_seen_bit_reads_back_where_the_marker_wrote_it():
    """The marker at image 0x11268: byte x//8 of row y, bit 0x80 >> (x%8)."""
    blob = bytearray(S.SAVE_SIZE)
    blob[:S.ROSTER_SLOTS * S.ROSTER_SLOT] = WORLD[ROSTER:ROSTER + S.ROSTER_SLOTS * S.ROSTER_SLOT]
    x, y = 460, 46
    blob[5000 + y * S.BAND_BYTES + x // 8] |= 0x80 >> (x % 8)
    save = S.Save(bytes(blob))
    assert save.seen(x, y)
    assert not save.seen(x + 1, y)
    assert save.seen_cells() == [(x, y)]


def test_a_save_has_to_be_the_right_length():
    with pytest.raises(ValueError):
        S.Save(bytes(S.SAVE_SIZE - 1))


# --- the packed-BCD counters ------------------------------------------------

def test_bcd_reads_two_decimal_digits_a_byte_most_significant_first():
    assert S.bcd(bytes([0x00, 0x00, 0x35, 0x57]), 0) == 3557
    assert S.bcd(bytes([0x00, 0x00, 0x00, 0x61]), 0) == 61
    assert S.bcd(bytes([0x00, 0x00, 0x03, 0x20]), 0) == 320


def test_bcd_refuses_a_byte_that_is_not_two_decimal_digits():
    with pytest.raises(ValueError):
        S.bcd(bytes([0x00, 0x00, 0x00, 0x1A]), 0)


def test_a_new_game_starts_with_an_empty_purse():
    save = template()
    assert save.purse == {"gold": 0, "food": 0, "nuore": 0}
    assert all(c["experience"] == 0 for c in save.characters())


# --- the character block ----------------------------------------------------

def test_the_live_block_is_twenty_six_words_with_nothing_overlapping():
    named = (
        [S.OFF_ATTRIBUTES + 2 * i for i in range(len(S.ATTRIBUTES))]
        + [S.OFF_COMBAT + 2 * i for i in range(len(S.COMBAT))]
        + [S.OFF_SKILLS + 2 * i for i in range(len(S.SKILLS))]
        + [S.OFF_HEALTH, S.OFF_MAGIC, S.OFF_CAPACITY]
    )
    assert len(named) == 26
    assert sorted(named) == list(range(0, 52, 2))
    assert S.MAXIMUM - S.LIVE == 64


def test_the_equipment_offsets_are_the_slot_words_the_item_dispatch_writes():
    # docs/items.md, "Equip slots": 0x13a missile, 0x13e ammunition (which is
    # where the container sits), 0x142 hand, 0x146 shield, 0x14a and 0x14e
    # rings, 0x152 worn.
    assert list(S.EQUIPMENT.values()) == [0x13A, 0x13E, 0x142, 0x146,
                                          0x14A, 0x14E, 0x152]
    assert S.PANEL_AT + 4 * S.PANEL_SLOTS == S.EQUIPMENT["missile"]


def test_the_stock_four_parse_as_level_one_and_undamaged():
    for c in template().characters():
        assert c["level"] == 1
        assert c["now"]["health"] == c["most"]["health"]
        assert c["now"]["magic"] == c["most"]["magic"]
        assert c["now"]["casting"] == c["most"]["casting"]


# --- the treasure table sections 3 and 4 index ------------------------------

def test_the_treasure_table_is_a_thousand_records_of_twenty_six():
    table = S.treasure_table(ROOT / "game" / "WORLD.DAT")
    assert len(table) == 1000
    assert all(len(r) == 13 for r in table)


def test_a_treasure_holds_item_ids_and_the_save_has_a_byte_for_each():
    table = S.treasure_table(ROOT / "game" / "WORLD.DAT")
    # Only the low part of the section is treasure; past about record 400 it
    # holds something else, text among it. What matters here is that the
    # treasures are well formed and that the save has room for every record.
    treasures = [r for r in table[:400] if any(r[S.TREASURE_ITEMS])]
    assert len(treasures) > 250
    ids = [i for r in treasures for i in r[S.TREASURE_ITEMS] if i]
    # The item table is 631 records, so ids run 0-630. Record 394 holds 631,
    # one past the end, and is the only one that does.
    assert max(ids) == 631
    assert sum(1 for i in ids if i > 630) == 1
    assert S.sections()[4].size >= len(table)
    assert S.sections()[3].size * 8 >= len(table)


def test_the_bank_stride_is_the_constant_the_startup_writes(exe):
    """Section 3 is banked: the second entry point adds DS:0xF48 to the record
    number, and that word is written once with 1,008."""
    assert S.bank_size(exe) == S.BANK
    # A bank is exactly section 4's size: one entry per record of the table
    # both sections index. Section 3 has room for both banks the code uses.
    assert S.BANK == S.sections(exe)[4].size
    assert S.sections(exe)[3].size * 8 >= 2 * S.BANK


def test_a_bit_in_the_second_bank_is_not_a_treasure_in_the_first():
    blob = bytearray(template().blob)
    base = S.sections()[3].base
    blob[base + S.BANK // 8] = 0x80          # bit 1008, the first of bank 1
    save = S.Save(bytes(blob))
    assert save.banks() == {0: [], 1: [0]}
    assert save.treasures(S.treasure_table(ROOT / "game" / "WORLD.DAT")) == []


def test_looting_a_treasure_reads_back_as_what_is_gone():
    table = S.treasure_table(ROOT / "game" / "WORLD.DAT")
    n = next(i for i, r in enumerate(table)
             if sum(1 for x in r[S.TREASURE_ITEMS] if x) >= 2)
    slots = table[n][S.TREASURE_ITEMS]
    blob = bytearray(template().blob)
    secs = S.sections()
    blob[secs[4].base + n] = 0x80                  # the first item taken
    blob[secs[3].base + n // 8] |= 0x80 >> (n % 8)  # and the treasure opened
    got = S.Save(bytes(blob)).treasures(table)
    assert len(got) == 1
    assert got[0]["treasure"] == n and got[0]["chest"]
    assert got[0]["taken"] == [slots[0]]
    assert got[0]["left"] == [x for x in slots[1:] if x]
