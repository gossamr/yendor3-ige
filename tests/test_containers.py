"""Container records, and the two bags that end up sharing one.

The offsets are held to `REGISTER.EXE` rather than restated: the allocator's
two words are found by disassembling the instructions that read them, and the
roster's base by the one the save routine writes from. What follows from that
-- that the counter is part of the saved roster, so a restore can put it behind
the world -- is the bug these tests pin.
"""
import struct

import pytest

import containers as C
import keep_characters as K
import saves as S
from mz import HEADER, Image

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
WORLD = (ROOT / "game" / "WORLD.DAT").read_bytes()
EXE = Image(ROOT / "game" / "REGISTER.EXE")

# Where the roster sits in the data segment: the save routine at image 0x0E3FA
# points the file handle's buffer at it before writing section 0.
ROSTER_BUFFER = 0xCEDD


def at_image(image: int, length: int) -> bytes:
    return EXE.data[HEADER + image:HEADER + image + length]


@pytest.fixture(scope="module")
def ids():
    return C.container_ids(ROOT / "game")


# -- the offsets, against the executable -------------------------------------

def test_the_save_writes_the_roster_from_ds_cedd():
    # mov ax, 0xcedd / mov bx, 0x967a (CURGAME) / lcall the section 0 stub
    assert at_image(0x0E3FA, 6) == bytes([0xB8, 0xDD, 0xCE, 0xBB, 0x7A, 0x96])


def test_the_allocator_counts_in_the_roster_header():
    # mov ax, [0xd08b] / inc word [0xd08b], the only two instructions that
    # touch the counter, in the bump path of the allocator at image 0x1600E.
    assert at_image(0x16044, 3) == bytes([0xA1, 0x8B, 0xD0])
    assert at_image(0x16047, 4) == bytes([0xFF, 0x06, 0x8B, 0xD0])
    assert 0xD08B - ROSTER_BUFFER == C.NEXT_RECORD


def test_the_free_list_head_is_in_the_roster_header_too():
    # cmp word [0xd08d], 0, the allocator's first test.
    assert at_image(0x1600F, 5) == bytes([0x83, 0x3E, 0x8D, 0xD0, 0x00])
    assert 0xD08D - ROSTER_BUFFER == C.FREE_HEAD


def test_the_slots_walked_are_the_eleven_delete_character_frees():
    # mov ax, [si+0x11a] / mov bx, [si+0x11c], then `add si, 4` eleven times.
    assert at_image(0x13AA8, 3) == bytes([0xB9, C.SLOT_COUNT, 0x00])
    assert at_image(0x13AAB, 4) == bytes([0x8B, 0x84, 0x1A, 0x01])
    assert C.SLOT_OFFSETS[0] == 0x11A


def test_the_container_items_are_the_three_that_carry_the_bit(ids):
    assert ids == (28, 29, 30)      # BAG, BOX, BACKPACK, as cabinet/roster.js has them


# -- the shipped template is consistent, which is the control ----------------

def test_the_template_hands_out_records_from_three(ids):
    roster = WORLD[K.ROSTER:K.ROSTER + C.ROSTER_BYTES]
    assert C.allocator(roster) == (3, 0)
    held = {r.where: r.record for r in C.roster_references(roster, ids)}
    assert held == {"slot 6": 1, "slot 9": 2}      # SQUIRE and JOSEPHINE
    assert C.audit(roster, ids).ok


# -- a roster whose counter is behind ----------------------------------------

def roster_with_bag(record: int, slot: int = 1, item: int = 28) -> bytes:
    """The template's roster with one more character, holding a container."""
    out = bytearray(WORLD[K.ROSTER:K.ROSTER + C.ROSTER_BYTES])
    base = slot * C.ROSTER_SLOT
    out[base:base + C.ROSTER_SLOT] = bytearray(C.ROSTER_SLOT)
    out[base:base + 6] = b"ZORBAX"
    at = base + C.SLOT_OFFSETS[9]       # the container slot, +318
    struct.pack_into("<HH", out, at, item, record)
    return bytes(out)


def test_a_character_with_no_container_writes_nothing_down(ids):
    # DIANA and YENDOR ship without a bag: their container slot holds item 0.
    roster = WORLD[K.ROSTER:K.ROSTER + C.ROSTER_BYTES]
    for slot in (7, 8):
        at = slot * C.ROSTER_SLOT + C.SLOT_OFFSETS[9]
        assert struct.unpack_from("<HH", roster, at) == (0, 0)
    assert [r.where for r in C.roster_references(roster, ids)] == ["slot 6", "slot 9"]


def test_the_header_slot_is_not_walked_for_containers(ids):
    # Slot 0 is the party header. The sky ramp starts at +310 and runs through
    # the offsets a character keeps items at, so a ramp byte of 28 beside a
    # zero would read as a BAG on a record.
    roster = bytearray(WORLD[K.ROSTER:K.ROSTER + C.ROSTER_BYTES])
    struct.pack_into("<HH", roster, C.SLOT_OFFSETS[9], 28, 1)
    before = C.roster_references(bytes(roster), ids)

    fixed, notes = C.repair(bytes(roster), ids)
    assert [r.where for r in before] == ["slot 6", "slot 9"]
    assert notes == []
    assert fixed == bytes(roster)


def test_a_record_two_characters_point_at_is_a_shared_one(ids):
    a = C.audit(roster_with_bag(1), ids)      # 1 is SQUIRE's
    assert list(a.shared) == [1]
    assert [r.where for r in a.shared[1]] == ["slot 6", "slot 1"]


def test_a_record_at_the_counter_is_one_the_allocator_will_reissue(ids):
    a = C.audit(roster_with_bag(3), ids)      # the counter reads 3
    assert not a.shared
    assert [r.where for r in a.reissued] == ["slot 1"]
    assert not a.ok


def test_a_state_word_that_is_not_a_container_is_not_a_record(ids):
    # Item 34 is the TORCH, whose second word is how much is left to burn.
    assert C.audit(roster_with_bag(1, item=34), ids).ok


def test_the_repair_moves_the_newcomer_and_leaves_the_stock_four(ids):
    fixed, notes = C.repair(roster_with_bag(1), ids)
    held = {r.where: r.record for r in C.roster_references(fixed, ids)}

    assert held == {"slot 6": 1, "slot 9": 2, "slot 1": 3}
    assert C.allocator(fixed) == (4, 0)
    assert C.audit(fixed, ids).ok
    assert notes == ["slot 1: record 1 -> 3", "next record 3 -> 4"]


def test_the_repair_moves_the_counter_past_a_record_it_left_alone(ids):
    fixed, _ = C.repair(roster_with_bag(40), ids)
    assert C.allocator(fixed) == (41, 0)


def test_the_repair_drops_a_free_list_built_while_the_counter_was_behind(ids):
    roster = bytearray(roster_with_bag(1))
    struct.pack_into("<H", roster, C.FREE_HEAD, 7)
    fixed, notes = C.repair(bytes(roster), ids)

    assert C.allocator(fixed)[1] == 0
    assert "free list head 7 -> empty" in notes


# -- grafting, which is where the counter was being left behind --------------

def test_grafting_a_bag_never_lands_it_on_a_record_in_use(ids):
    kept = roster_with_bag(1)                 # kept while the counter read 3
    out, moved, renumbered = K.graft(WORLD, kept, ids=ids)
    roster = out[K.ROSTER:K.ROSTER + C.ROSTER_BYTES]

    assert moved == ["slot 1: ZORBAX"]
    assert renumbered == ["slot 1: record 1 -> 3", "next record 3 -> 4"]
    assert C.audit(roster, ids).ok


def test_two_sessions_handed_the_same_record_keep_one_each(ids):
    first, _, _ = K.graft(WORLD, roster_with_bag(3, slot=1), ids=ids)
    second, _, _ = K.graft(first, roster_with_bag(3, slot=2), ids=ids)
    roster = second[K.ROSTER:K.ROSTER + C.ROSTER_BYTES]
    held = {r.where: r.record for r in C.roster_references(roster, ids)}

    assert held == {"slot 6": 1, "slot 9": 2, "slot 1": 3, "slot 2": 4}
    assert C.allocator(roster) == (5, 0)


def test_grafting_the_stock_template_changes_nothing(ids):
    out, moved, renumbered = K.graft(WORLD, bytes(C.ROSTER_BYTES), ids=ids)
    assert (moved, renumbered) == ([], [])
    assert out == WORLD


# -- a save, where the shared record has contents to move --------------------

def save_with(roster: bytes, contents: dict[int, list[int]]) -> bytes:
    """A save-shaped blob: this roster, and these containers holding these ids."""
    blob = bytearray(S.SAVE_SIZE)
    blob[:C.ROSTER_BYTES] = roster
    section = S.sections()[C.CONTAINERS]
    for n, items in contents.items():
        at = section.base + n * section.record
        struct.pack_into("<H", blob, at, 10 * len(items))     # the content weight
        for i, item in enumerate(items):
            struct.pack_into("<H", blob, at + 2 + 4 * i, item)
    return bytes(blob)


def test_a_shared_record_is_split_and_its_contents_copied(ids):
    section = S.sections()[C.CONTAINERS]
    blob = save_with(roster_with_bag(1), {1: [31, 51, 155]})
    assert C.audit(blob, ids, section).shared

    fixed, notes = C.repair(blob, ids, section)
    save = S.Save(fixed)

    assert C.audit(fixed, ids, section).ok
    assert save.container(1) == save.container(3) == [(31, 0), (51, 0), (155, 0)]
    assert notes[0] == "slot 1: record 1 -> 3 with a copy of its contents"


def test_the_repair_touches_nothing_but_the_records_it_moved(ids):
    section = S.sections()[C.CONTAINERS]
    blob = save_with(roster_with_bag(1), {1: [31]})
    fixed, _ = C.repair(blob, ids, section)
    differing = {i for i in range(len(blob)) if blob[i] != fixed[i]}
    moved = set(range(section.base + 3 * section.record,
                      section.base + 4 * section.record))
    header = {C.NEXT_RECORD, C.NEXT_RECORD + 1}
    slot = C.ROSTER_SLOT + C.SLOT_OFFSETS[9] + 2

    assert differing <= moved | header | {slot, slot + 1}


def test_a_bag_inside_a_box_is_a_reference_too(ids):
    section = S.sections()[C.CONTAINERS]
    # Slot 1 holds a BOX on record 5, and that box holds a BAG which was handed
    # record 5 as well, so the box contains itself.
    blob = bytearray(save_with(roster_with_bag(5, item=29), {5: [28]}))
    struct.pack_into("<H", blob, section.base + 5 * section.record + 4, 5)

    a = C.audit(bytes(blob), ids, section)
    assert [r.where for r in a.shared[5]] == ["slot 1", "record 5"]
    fixed, _ = C.repair(bytes(blob), ids, section)
    assert C.audit(fixed, ids, section).ok


def test_a_clean_save_is_left_as_it_is(ids):
    section = S.sections()[C.CONTAINERS]
    blob = save_with(WORLD[K.ROSTER:K.ROSTER + C.ROSTER_BYTES], {1: [31], 2: [51]})
    fixed, notes = C.repair(blob, ids, section)

    assert notes == []
    assert fixed == blob
