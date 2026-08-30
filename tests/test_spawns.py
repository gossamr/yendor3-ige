"""The monster census: 1,862 placements, and what checks them.

Nothing here reads a screen. What makes the decode trustworthy is that three
independent counts have to agree: the cell events number 1 to 1,862 with no
gap, every one of them resolves through section 30 to a monster the game
lists, and every monster the game lists is placed somewhere.
"""

import pytest

import spawns as SP

PLACEMENTS = 1862


@pytest.fixture(scope="module")
def enemies(data):
    """Out of the conftest fixture, which decodes the records, rather than out
    of data/enemies.json. That file is generated and gitignored, so a test
    reading it fails on a tree where `make data` has not been run."""
    return data["enemies"]


def test_spawn_ids_are_a_dense_run(directory):
    """A spawn id is a record number in section 30 and a bit in save section
    5, so a gap would mean the kind bit had been read wrong."""
    place = SP.placements(directory)
    assert len(place) == PLACEMENTS
    assert sorted(p["id"] for p in place) == list(range(1, PLACEMENTS + 1))


def test_every_placement_names_a_monster_the_game_lists(directory, enemies):
    listed = {e["index"] for e in enemies}
    for p in SP.placements(directory):
        assert p["enemy"] in listed, p


def test_every_listed_monster_is_placed(directory, enemies):
    """Record 62 is the `NOT USED` placeholder and record 0 the sentinel. All
    71 the clue book lists stand somewhere on the world grid, and the
    placeholder stands nowhere."""
    placed = {p["enemy"] for p in SP.placements(directory)}
    listed = {e["index"] for e in enemies if e["listed"]}
    assert listed - placed == set()
    assert placed == listed
    assert len(placed) == 71


def test_a_placement_falls_on_a_map_that_exists(directory, enemies):
    """Every monster stands inside one of the 54 slots the registry names,
    and the seven with none are the towns and the hubs."""
    from registry import map_registry

    titles = map_registry(directory.world)
    pages = SP.census(directory, enemies)
    assert set(pages) <= set(titles.values())
    assert len(pages) == 47


def test_the_census_totals(directory, enemies):
    """What the whole game pays out, which is what a level plan is bounded
    by. Every monster is a one-time encounter, so these are the totals."""
    by_index = {e["index"]: e for e in enemies}
    place = SP.placements(directory)
    experience = sum(by_index[p["enemy"]]["experience"] for p in place)
    gold = sum(by_index[p["enemy"]]["gold"] for p in place)
    assert experience == 13_322_378
    assert gold == 10_989_385


def test_the_athaneum_gate_flags_are_the_two_yendor_centipedes(directory):
    """Opening the Athaneum's south gate sets save section 5 flags 37 and 36
    (`docs/saves.md`). Those two ids are the pair of centipedes standing on
    adjacent cells of Yendor, which is where that gate leads: the flags are
    monsters being taken off the map, not gate state."""
    by_id = {p["id"]: p for p in SP.placements(directory)}
    a, b = by_id[36], by_id[37]
    assert (a["area"], a["level"]) == (2, 1)
    assert (a["x"], a["y"]) == (63, 60) and (b["x"], b["y"]) == (63, 61)
    assert a["enemy"] == b["enemy"] == 2      # CENTIPEDE
