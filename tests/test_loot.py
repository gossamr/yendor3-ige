"""What a cell holds: the 380 containers and the 71 locks.

What makes this more than a plausible reading of two byte ranges is the way the
two tables meet. The container argument runs to 403 over a section of exactly
1,000 records of 26 bytes, and the lock argument runs to 71 over a table the
code places at `26 x 1000` past the same buffer's start, which is 284 bytes
into the next section. The six states the lock word takes partition all 451
records with nothing left over, and the seven key bits fall one each on the
Athaneum's six gates and Yendor's seventh.
"""
import loot as LO
import sections as S


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
