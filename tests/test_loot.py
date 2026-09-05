"""What a cell holds: the 380 containers and the 71 locks.

What makes this more than a plausible reading of two byte ranges is the way the
two tables meet. The container argument runs to 403 over a section of exactly
1,000 records of 26 bytes, and the lock argument runs to 71 over a table the
code places at `26 x 1000` past the same buffer's start, which is 284 bytes
into the next section. The six states the lock word takes partition all 451
records with nothing left over, and the seven key bits fall one each on the
Athaneum's six gates and Yendor's seventh.
"""
import collections
import struct

import labels as L
import loot as LO
import sections as S

# The table of panels the WHO WILL prompts are numbered into (docs/party.md).
PROMPTS = 0xE265


def test_the_bundle_table_divides_exactly(directory):
    """1,000 records of 26 bytes, which is what DS:0x545E is written with."""
    section = directory.sections[LO.BUNDLES]
    assert section.size == LO.BUNDLE_COUNT * LO.BUNDLE_RECORD


def test_the_lock_table_begins_where_the_bundles_end(directory):
    """Image 0x025CB reads at 26 x [DS:0x545E] past the buffer the bundles are
    in, and the two sections are adjacent in the file, so the lock table is the
    head of the next one."""
    bundles, locks = directory.sections[LO.BUNDLES], directory.sections[LO.LOCKS]
    assert bundles.offset + LO.BUNDLE_COUNT * LO.BUNDLE_RECORD == locks.offset
    assert LO.LOCK_COUNT * LO.LOCK_RECORD <= locks.size


def test_the_cell_events_name_380_containers_and_71_locks(directory):
    chests, locks = LO.containers(directory), LO.passages(directory)
    assert len(chests) == 380
    assert len(locks) == LO.LOCK_COUNT
    # Every argument is its own: no two cells share a bundle or a lock.
    assert len({c["bundle"] for c in chests}) == len(chests)
    assert len({l["number"] for l in locks}) == len(locks)
    assert sorted(l["number"] for l in locks) == list(range(LO.LOCK_COUNT))


def test_the_lock_word_partitions_every_record(directory):
    """One state bit at most, and a kind of 1 or 2 under it. The six
    combinations below are every low byte the 451 records take."""
    rows = LO.containers(directory) + LO.passages(directory)
    seen = {}
    for r in rows:
        seen[r["lock"] & 0xFF] = seen.get(r["lock"] & 0xFF, 0) + 1
    assert seen == {0x01: 45, 0x09: 25, 0x21: 30, 0x41: 55, 0x81: 119, 0x82: 177}
    for r in rows:
        assert r["kind"] in (1, 2)
        assert bin(r["lock"] & LO.STATES).count("1") <= 1


def test_a_key_bit_and_a_state_bit_never_share_a_record(directory):
    """45 records name a key, one bit each, and none of them carries a state
    bit as well, so `state` is a single answer rather than a precedence."""
    rows = LO.containers(directory) + LO.passages(directory)
    keyed = [r for r in rows if r["lock"] & LO.KEYED]
    assert len(keyed) == 45
    for r in keyed:
        assert bin(r["lock"] & LO.KEYED).count("1") == 1
        assert r["lock"] & LO.STATES == 0
        assert r["state"] == "key"
        assert r["key"] in LO.METALS


def test_the_athaneum_holds_six_of_the_seven_metals(directory):
    """The six gates of one building carry six different door keys, and the
    seventh metal is Yendor's gate. That is what ties the key bits to the seven
    key items rather than to seven unknowns."""
    locks = LO.passages(directory)
    athaneum = sorted(l["key"] for l in locks if l["number"] < 6)
    assert athaneum == ["brass", "bronze", "copper", "iron", "silver", "steel"]
    assert [l["key"] for l in locks if l["number"] == 14] == ["gold"]


def test_the_difficulty_serves_the_lock_and_the_trap(directory):
    """Bit 0x40 is set on exactly the records with a difficulty they are picked
    against, and a trap is rolled against the same number whether the thing is
    locked or not."""
    rows = LO.containers(directory) + LO.passages(directory)
    for r in rows:
        if r["lock"] & LO.PICKABLE:
            assert r["pick"] > 0
        if r["lock"] & LO.TRAP_ONLY:
            assert r["pick"] == 0 and r["trap"] > 0
    trapped = [r for r in rows if r["trap"]]
    assert len(trapped) == 145
    assert sum(1 for r in trapped if r["state"] == "open") == 71


def test_a_trap_number_is_one_to_thirteen_either_way(directory):
    """A trap at or over 50 hits the party and is indexed by what is left after
    subtracting it, so both roads land in the same range."""
    rows = LO.containers(directory) + LO.passages(directory)
    for r in rows:
        if not r["trap"]:
            continue
        n = r["trap"] - LO.TRAP_PARTY if r["party_trap"] else r["trap"]
        assert 1 <= n <= 13


def test_the_three_counts_belong_to_the_three_items_that_stack(directory, data):
    """Words 10, 11 and 12 are GOLD COINS, FOOD and NUORE in that order, and a
    count is nonzero only where its own item stands in one of the eight
    places."""
    names = {i["id"]: i["name"] for i in data["items"]}
    assert [names[i] for i in LO.STACKED] == ["GOLD COINS", "FOOD", "NUORE"]
    for c in LO.containers(directory):
        for item, word in LO.STACKED.items():
            if c["counts"][LO.STACKED_NAME[item]]:
                assert item in c["items"], c


def test_every_container_holds_something(directory):
    """No bundle a cell names is empty: all 380 carry an item or a count."""
    for c in LO.containers(directory):
        assert any(c["items"]) or any(c["counts"].values())


def test_the_pick_chance_is_the_roll_the_code_makes():
    """Image 0x17882: five per level over the difficulty, plus thievery, with a
    floor of five."""
    assert LO.chance(10, 4, 25) == 55
    assert LO.chance(1, 60, 0) == 5
    assert LO.chance(40, 40, 88) == 88


def test_every_container_cell_draws_something_named(directory):
    """All 380 stand on one of 27 object ids, and the table names each."""
    drawn = {c["object"] for c in LO.containers(directory)}
    assert len(drawn) == 27
    assert drawn <= set(LO.DRAWN_AS)


def test_the_kind_bit_is_the_lid(directory):
    """Kind 1 is the barrel, the chest and the dresser, the three drawings with
    a lid to lift, which is why image 0x02978 steps a picture for that kind
    alone. Every other drawing is kind 2."""
    kinds = collections.defaultdict(set)
    for c in LO.containers(directory):
        kinds[c["drawn"]].add(c["kind"])
    assert all(len(k) == 1 for k in kinds.values())
    assert {name for name, k in kinds.items() if k == {1}} == {"barrel", "chest", "dresser"}


def test_a_drawing_is_one_object_turned_four_ways(directory):
    """The ids of a group name the same pictures in another order, since an
    object's record holds one picture per facing (docs/map.md)."""
    from view_art import OBJECT_FACES, object_record
    from tiles import _word
    for name, ids in LO.DRAWINGS.items():
        pictures = {frozenset(_word(directory.exe, object_record(directory.exe, o) + off)
                              for off in OBJECT_FACES) for o in ids}
        assert len(pictures) == 1, name


def test_the_two_kinds_raise_open_and_search(directory):
    """Image 0x027AD passes 5 for kind 1 and 6 for kind 2 to the prompt at
    0x058F0, which reads a panel out of the word table at DS:0xE265."""
    def prompt(n: int) -> str:
        at = struct.unpack_from("<H", directory.exe, L.DGROUP + PROMPTS + (n - 1) * 2)[0]
        text = struct.unpack_from("<H", directory.exe, L.DGROUP + at + 8 + 6)[0]
        said = directory.exe[L.DGROUP + text:L.DGROUP + text + 40].split(b"\x00")
        return b" ".join(said[:2]).decode()

    assert prompt(5) == "WHO WILL OPEN?"
    assert prompt(6) == "WHO WILL SEARCH?"


def test_every_trap_number_names_an_attack_entry(directory):
    """A trap indexes the same table a monster's special attack does, and one
    at or over 50 is the party's with that much taken off first (image
    0x018EA3)."""
    import extract as EX
    table = EX.attack_table(directory.exe)
    rows = LO.containers(directory) + LO.passages(directory)
    traps = {r["trap"] for r in rows if r["trap"]}
    assert len(traps) == 22
    for trap in traps:
        at = trap - LO.TRAP_PARTY if trap >= LO.TRAP_PARTY else trap
        assert 0 < at <= 13, trap
    # Both halves land on the same thirteen entries, and the two that take
    # nothing off are carried by one cell each: entry 1 routes to a handler
    # nothing has read, and entry 3 is a sound and an animation.
    inside = {t % LO.TRAP_PARTY for t in traps}
    assert inside == set(range(1, 14))
    assert sorted(t for t in inside if not table[t]["effect"]) == [1, 3]
    assert sorted(t for t in inside if table[t]["effect"] & 0xFF80) == [5, 7, 9, 11]
