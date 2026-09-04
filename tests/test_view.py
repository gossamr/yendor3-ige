"""The first-person view's geometry, read from the game's own files.

What these hold is that the view needs no projection: which cells it shows is
arithmetic on the party's position, and where each one lands is a table in
`WORLD.DAT`. The last two hold the stored table to a rule of four numbers,
which is the same geometry without the table.
"""
import json
from pathlib import Path

import pytest

import view as V

ROOT = Path(__file__).resolve().parent.parent
PROBE = ROOT / "tmp" / "view-north.json"


def centers() -> list[int]:
    """The middle cell of each row, which is the one nothing clips."""
    out, cell = [], 0
    for width in V.RUNS:
        out.append(cell + (width - 1) // 2)
        cell += width
    return out


def test_the_view_is_seven_rows_of_51_cells():
    assert V.CELLS == 51
    assert V.RUNS == (17, 17, 5, 3, 3, 3, 3)
    assert V.DEPTHS == (6, 5, 4, 3, 2, 1, 0), "the far row is drawn first"


def test_right_is_forward_turned_clockwise_for_every_facing():
    """y counts south, so a clockwise turn takes (x, y) to (-y, x). A facing
    that broke this would draw the view mirrored and nothing else."""
    for facing, (forward, right) in V.FACINGS.items():
        fx, fy = forward
        assert right == (-fy, fx), f"{facing:#06x}"


def test_the_frustum_is_the_party_plus_a_depth_and_a_lateral():
    cells = V.frustum(100, 100, V.NORTH)
    assert cells[0] == (92, 94), "the far row starts eight cells left, six ahead"
    assert cells[-2] == (100, 100), "the last row's middle cell is the party's own"
    assert len(set(cells)) == len(cells), "no cell is in the view twice"


@pytest.mark.parametrize("facing", sorted(V.FACINGS))
def test_a_facing_turns_the_frustum_without_changing_its_shape(facing):
    """The 51 offsets are one shape in four orientations. Sorting each pair
    drops the orientation and leaves the shape, which must not move."""
    def shape(which):
        return sorted(tuple(sorted((abs(x - 100), abs(y - 100))))
                      for x, y in V.frustum(100, 100, which))

    assert len(set(V.frustum(100, 100, facing))) == 51
    assert shape(facing) == shape(V.NORTH)


def test_every_slot_list_is_inside_the_section(directory):
    """A run list that ran off the end would still decode, into a slot with a
    plausible shape, so the bound is asserted rather than trusted."""
    section = directory.sections[V.GEOMETRY]
    assert section.size == 18844
    for mode in (V.FLOOR, V.CEILING):
        drawn = [s for s in V.slots(directory.world, mode, directory) if s]
        assert len(drawn) == 43, mode
        for slot in drawn:
            assert 0 < slot.height <= 21
            assert all(0 < length <= V.VIEW_W for _, _, length in slot.spans())


def test_the_two_halves_tile_their_own_pictures_exactly(directory):
    """The floor's seven bands fill its 74 rows and the ceiling's its 62, with
    nothing over: that is what makes the join a horizon rather than a seam."""
    for mode, height in ((V.FLOOR, 74), (V.CEILING, 62)):
        slots = V.slots(directory.world, mode, directory)
        bands = sorted((slots[cell].y, slots[cell].y + slots[cell].height)
                       for cell in centers())
        assert bands[0][0] == 0 and bands[-1][1] == height
        for (_, ends), (starts, _) in zip(bands, bands[1:]):
            assert ends == starts, f"{mode}: the bands leave a gap or overlap"


def test_a_cell_is_four_pixels_wider_for_every_row_from_the_horizon(directory):
    """Held on the middle cell of each row, which is the one nothing clips."""
    for mode, rows_away in (
            (V.FLOOR, lambda y: y + 0.5),
            (V.CEILING, lambda y: V.HORIZON + 0.5 - y)):
        slots = V.slots(directory.world, mode, directory)
        for cell in centers():
            for y, _, length in slots[cell].spans():
                assert length == V.width(rows_away(y)), (mode, cell, y, length)


def test_the_band_table_is_where_the_rows_meet(directory):
    """`FLOOR_BAND` and `CEILING_BAND` are the far face of each row, counted
    from the horizon, which is those seven boundaries without the table."""
    near_to_far = list(reversed(centers()))
    floor = V.slots(directory.world, V.FLOOR, directory)
    assert [floor[cell].y for cell in near_to_far] == list(V.FLOOR_BAND)
    ceiling = V.slots(directory.world, V.CEILING, directory)
    assert [int(V.HORIZON) - (ceiling[cell].y + ceiling[cell].height)
            for cell in near_to_far] == list(V.CEILING_BAND)


def test_the_front_lists_draw_the_widths_the_rule_gives(directory):
    """Each list's runs sum to the face the band rule places: 210 by 105 one
    cell ahead down to 14 by 7 six ahead."""
    front = V.faces(directory.world, "front", directory)
    total = lambda rows: sum(r * d for r, d, _ in rows)
    near_to_far = list(reversed(centers()))[1:]
    assert [total(front[c]["cols"]) for c in near_to_far] == [210, 166, 126, 86, 50, 14]
    assert [total(front[c]["rows"]) for c in near_to_far] == [105, 83, 63, 43, 25, 7]
    assert all(total(front[c]["cols"]) <= V.VIEW_W for c in range(51) if front[c])


def test_a_side_face_is_columns_of_one_shared_row_list(directory):
    """Cell 45, one ahead on the left: 22 columns in eleven records of two,
    the first 105 rows tall and each after two rows shorter."""
    side = V.faces(directory.world, "side", directory)
    records = side[45]["records"]
    assert sum(r["count"] for r in records) == 22
    heights = [sum(a * b for a, b, _ in r["rows"]) for r in records]
    assert heights == list(range(105, 83, -2))
    assert side[46] is None, "the cell straight ahead has no side face"


def test_a_terrain_record_is_four_view_pictures_and_a_map_tile(directory):
    """All twelve bytes: floor, ceiling, wall face, strip, the strip's first
    column, and the tile tools/tiles.py reads at +0x0A."""
    exe = directory.exe
    assert V.picture(exe, 2, V.STRIP, 0) == 22, "id 2 is a wall"
    assert (V.column(exe, 2), V.column(exe, 2, True)) == (0, 7)
    assert V.picture(exe, 306, V.STRIP, 0) is None, "a floor names no strip"
    named = {V.picture(exe, t, V.STRIP, 0) for t in range(341)} - {None}
    assert named == {22, 23}


@pytest.mark.skipif(not PROBE.exists(), reason="no tmp/view-north.json; "
                                                "run tools/view_probe.js")
def test_the_frustum_is_the_table_the_game_built(directory):
    """The probe reads the game's own 51 entries out of memory. Every one of
    them names the cell this arithmetic names."""
    import view_check

    probe = json.loads(PROBE.read_text())
    party = probe["party"]
    cells = V.frustum(party["x"], party["y"], party["facing"])
    for row, (x, y) in zip(probe["rows"], cells):
        assert row["draws"] == view_check.terrain(directory.world, x, y), row["cell"]
